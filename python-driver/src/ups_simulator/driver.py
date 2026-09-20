from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import socket
import warnings
from typing import Dict, Iterator, Optional, Protocol, Union


class SimulatorError(RuntimeError):
    """Base exception for simulator control failures."""


class TransportError(SimulatorError):
    """Raised when the TCP or serial transport fails."""


class ProtocolError(SimulatorError):
    """Raised when a simulator response does not match the expected protocol."""


class CommandError(SimulatorError):
    """Raised when the firmware rejects a command with an ERR response."""


class LineTransport(Protocol):
    def connect(self) -> None: ...
    def close(self) -> None: ...
    def command(self, command: str) -> str: ...


class SocketLineTransport:
    """Persistent line-oriented TCP transport for the W5500 control port."""

    def __init__(self, host: str, port: int = 5000, timeout: float = 2.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._rx = bytearray()
        self.greeting: list[str] = []

    def connect(self) -> None:
        if self._sock is not None:
            return
        try:
            self._sock = socket.create_connection((self.host, self.port), self.timeout)
            self._sock.settimeout(self.timeout)
            self._sync()
        except OSError as exc:
            self.close()
            raise TransportError(f"cannot connect to {self.host}:{self.port}: {exc}") from exc
        except SimulatorError:
            self.close()
            raise

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
                self._rx.clear()

    def _readline(self) -> str:
        if self._sock is None:
            raise TransportError("transport is not connected")

        while True:
            newline = self._rx.find(b"\n")
            if newline >= 0:
                raw = bytes(self._rx[:newline])
                del self._rx[: newline + 1]
                try:
                    return raw.rstrip(b"\r").decode("ascii", errors="strict")
                except UnicodeDecodeError as exc:
                    raise ProtocolError("simulator returned non-ASCII data") from exc
            try:
                chunk = self._sock.recv(256)
            except socket.timeout as exc:
                raise TransportError("timeout waiting for simulator response") from exc
            except OSError as exc:
                raise TransportError(f"socket receive failed: {exc}") from exc
            if not chunk:
                raise TransportError("simulator closed the TCP connection")
            self._rx.extend(chunk)

    def _sync(self, max_lines: int = 8) -> None:
        """Align the reply stream after connecting.

        Old firmware only emits its greeting after receiving the first command;
        fixed firmware greets immediately. Sending PING and reading through its
        reply handles both behaviours without relying on timing.
        """
        if self._sock is None:
            raise TransportError("transport is not connected")
        self.greeting = []
        try:
            self._sock.sendall(b"PING\n")
        except OSError as exc:
            raise TransportError(f"socket send failed: {exc}") from exc
        for _ in range(max_lines):
            line = self._readline()
            if line == "OK PONG":
                return
            self.greeting.append(line)
        raise ProtocolError("simulator did not answer PING while connecting")

    def command(self, command: str) -> str:
        self.connect()
        if self._sock is None:
            raise TransportError("transport is not connected")
        if "\n" in command or "\r" in command:
            raise ValueError("command must be a single line")
        try:
            self._sock.sendall(command.encode("ascii") + b"\n")
        except (OSError, UnicodeEncodeError) as exc:
            raise TransportError(f"socket send failed: {exc}") from exc
        return self._readline()


class SerialLineTransport:
    """Optional pyserial-based transport for Leonardo Serial1 control."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 2.0) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None

    def connect(self) -> None:
        if self._serial is not None:
            return
        try:
            import serial  # type: ignore
        except ImportError as exc:
            raise TransportError(
                "pyserial is required for UART control; install with "
                "'pip install nutups-simulator-control[serial]'"
            ) from exc
        try:
            self._serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
                write_timeout=self.timeout,
            )
            self._serial.reset_input_buffer()
            self._sync()
        except SimulatorError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise TransportError(f"cannot open serial port {self.port}: {exc}") from exc

    def _sync(self, max_lines: int = 8) -> None:
        """Skip boot/banner lines so the first command reply is aligned."""
        if self._serial is None:
            raise TransportError("serial transport is not connected")
        try:
            self._serial.write(b"PING\n")
            self._serial.flush()
            for _ in range(max_lines):
                raw = self._serial.readline()
                if not raw:
                    raise TransportError("timeout waiting for simulator response")
                if raw.rstrip(b"\r\n") == b"OK PONG":
                    return
        except SimulatorError:
            raise
        except Exception as exc:
            raise TransportError(f"serial I/O failed: {exc}") from exc
        raise ProtocolError("simulator did not answer PING while connecting")

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def command(self, command: str) -> str:
        self.connect()
        if self._serial is None:
            raise TransportError("serial transport is not connected")
        if "\n" in command or "\r" in command:
            raise ValueError("command must be a single line")
        try:
            self._serial.write(command.encode("ascii") + b"\n")
            self._serial.flush()
            raw = self._serial.readline()
        except Exception as exc:
            raise TransportError(f"serial I/O failed: {exc}") from exc
        if not raw:
            raise TransportError("timeout waiting for simulator response")
        try:
            return raw.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProtocolError("simulator returned non-ASCII data") from exc


@dataclass(frozen=True)
class SimulatorStatus:
    armed: bool
    ac_present: bool
    battery_percent: int
    runtime_seconds: int
    runtime_mode: str
    voltage_centivolts: int
    load_percent: int
    input_voltage_centivolts: int
    output_voltage_centivolts: int
    charging_mode: str
    charging_active: bool
    low_battery_mode: str
    low_battery_active: bool
    overload: bool
    need_replacement: bool
    communication_lost: bool
    shutdown_requested: bool
    shutdown_imminent: bool
    host_start_delay: int
    host_shutdown_delay: int
    host_reboot_delay: int
    ip: str

    @property
    def voltage_volts(self) -> float:
        return self.voltage_centivolts / 100.0

    @property
    def input_voltage_volts(self) -> float:
        return self.input_voltage_centivolts / 100.0

    @property
    def output_voltage_volts(self) -> float:
        return self.output_voltage_centivolts / 100.0


@dataclass(frozen=True)
class NetworkStatus:
    ip: str
    gateway: str
    subnet: str
    port: int


def _strip_ok(response: str) -> str:
    response = response.strip()
    if response.startswith("ERR"):
        detail = response[3:].lstrip(" :")
        raise CommandError(detail or response)
    if response == "OK":
        return ""
    if response.startswith("OK "):
        return response[3:]
    raise ProtocolError(f"unexpected simulator response: {response!r}")


def _parse_kv(payload: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for token in payload.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        result[key] = value
    return result


def _need(values: Dict[str, str], key: str) -> str:
    try:
        return values[key]
    except KeyError as exc:
        raise ProtocolError(f"missing {key!r} in simulator response") from exc


def _as_bool(values: Dict[str, str], key: str) -> bool:
    value = _need(values, key)
    if value == "1":
        return True
    if value == "0":
        return False
    raise ProtocolError(f"invalid boolean {key}={value!r}")


def _as_int(values: Dict[str, str], key: str) -> int:
    value = _need(values, key)
    try:
        return int(value)
    except ValueError as exc:
        raise ProtocolError(f"invalid integer {key}={value!r}") from exc


class UpsSimulator:
    """High-level control driver for the Arduino NutUPS simulator."""

    def __init__(self, transport: LineTransport) -> None:
        self.transport = transport

    @classmethod
    def tcp(cls, host: str, port: int = 5000, timeout: float = 2.0) -> "UpsSimulator":
        return cls(SocketLineTransport(host=host, port=port, timeout=timeout))

    @classmethod
    def serial(
        cls, port: str, baudrate: int = 115200, timeout: float = 2.0
    ) -> "UpsSimulator":
        return cls(SerialLineTransport(port=port, baudrate=baudrate, timeout=timeout))

    def connect(self) -> "UpsSimulator":
        self.transport.connect()
        ident = self.identify()
        if ident != "NutUPS HID Simulator v2":
            self.close()
            raise ProtocolError(f"unsupported simulator firmware: {ident!r}; expected v2")
        return self

    def close(self) -> None:
        self.transport.close()

    def __enter__(self) -> "UpsSimulator":
        return self.connect()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def raw_command(self, command: str) -> str:
        """Send one single-response protocol command and return its OK payload."""
        if command.strip().upper() in {"HELP", "?"}:
            raise ValueError("HELP is multi-line and is not supported by raw_command()")
        return _strip_ok(self.transport.command(command))

    def ping(self) -> bool:
        return self.raw_command("PING") == "PONG"

    def identify(self) -> str:
        return self.raw_command("IDENT?")

    def status(self) -> SimulatorStatus:
        values = _parse_kv(self.raw_command("STATUS?"))
        return SimulatorStatus(
            armed=_as_bool(values, "armed"),
            ac_present=_as_bool(values, "ac"),
            battery_percent=_as_int(values, "battery"),
            runtime_seconds=_as_int(values, "runtime"),
            runtime_mode=_need(values, "runtime_mode"),
            voltage_centivolts=_as_int(values, "voltage_cv"),
            load_percent=_as_int(values, "load"),
            input_voltage_centivolts=_as_int(values, "input_voltage_cv"),
            output_voltage_centivolts=_as_int(values, "output_voltage_cv"),
            charging_mode=_need(values, "charging_mode"),
            charging_active=_as_bool(values, "charging_active"),
            low_battery_mode=_need(values, "lowbat_mode"),
            low_battery_active=_as_bool(values, "lowbat_active"),
            overload=_as_bool(values, "overload"),
            need_replacement=_as_bool(values, "replace"),
            communication_lost=_as_bool(values, "commlost"),
            shutdown_requested=_as_bool(values, "shutdown"),
            shutdown_imminent=_as_bool(values, "shutdown_imminent"),
            host_start_delay=_as_int(values, "host_start_delay"),
            host_shutdown_delay=_as_int(values, "host_shutdown_delay"),
            host_reboot_delay=_as_int(values, "host_reboot_delay"),
            ip=_need(values, "ip"),
        )

    def network_status(self) -> NetworkStatus:
        values = _parse_kv(self.raw_command("NETWORK?"))
        return NetworkStatus(
            ip=_need(values, "ip"),
            gateway=_need(values, "gateway"),
            subnet=_need(values, "subnet"),
            port=_as_int(values, "port"),
        )

    def arm(self, enabled: bool = True, lease_seconds: Optional[int] = None) -> None:
        if not enabled:
            self.raw_command("ARM OFF")
            return
        if lease_seconds is None:
            self.raw_command("ARM ON")
            return
        if not 0 <= lease_seconds <= 3600:
            raise ValueError("arm lease must be in range 0..3600 seconds")
        self.raw_command(f"ARM ON {lease_seconds}")

    def disarm(self) -> None:
        self.arm(False)

    def reset(self) -> None:
        self.raw_command("RESET")

    def report(self) -> None:
        self.raw_command("REPORT")

    def set_ac(self, present: bool) -> None:
        self.raw_command(f"AC {'ON' if present else 'OFF'}")

    def set_battery(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise ValueError("battery percent must be in range 0..100")
        self.raw_command(f"BATTERY {percent}")

    def set_load(self, percent: int) -> None:
        if not 0 <= percent <= 100:
            raise ValueError("load percent must be in range 0..100")
        self.raw_command(f"LOAD {percent}")

    def set_runtime(self, seconds: Optional[int]) -> None:
        if seconds is None:
            self.raw_command("RUNTIME AUTO")
            return
        if not 0 <= seconds <= 65535:
            raise ValueError("runtime must be in range 0..65535 seconds")
        self.raw_command(f"RUNTIME {seconds}")

    @staticmethod
    def _to_centivolts(volts: float) -> int:
        centivolts = int(round(volts * 100.0))
        if not 0 <= centivolts <= 65535:
            raise ValueError("voltage must be in range 0..655.35 V")
        return centivolts

    def set_voltage_centivolts(self, centivolts: int) -> None:
        if not 0 <= centivolts <= 65535:
            raise ValueError("voltage must be in range 0..65535 centivolts")
        self.raw_command(f"VOLTAGE {centivolts}")

    def set_voltage(self, volts: float) -> None:
        self.set_voltage_centivolts(self._to_centivolts(volts))

    def set_input_voltage_centivolts(self, centivolts: int) -> None:
        if not 0 <= centivolts <= 65535:
            raise ValueError("input voltage must be in range 0..65535 centivolts")
        self.raw_command(f"INPUTVOLTAGE {centivolts}")

    def set_input_voltage(self, volts: float) -> None:
        self.set_input_voltage_centivolts(self._to_centivolts(volts))

    def set_output_voltage_centivolts(self, centivolts: int) -> None:
        if not 0 <= centivolts <= 65535:
            raise ValueError("output voltage must be in range 0..65535 centivolts")
        self.raw_command(f"OUTPUTVOLTAGE {centivolts}")

    def set_output_voltage(self, volts: float) -> None:
        self.set_output_voltage_centivolts(self._to_centivolts(volts))

    def set_start_delay(self, seconds: int) -> None:
        if not -1 <= seconds <= 32767:
            raise ValueError("start delay must be in range -1..32767 seconds")
        self.raw_command(f"STARTDELAY {seconds}")

    @staticmethod
    def _mode(value: Union[bool, str]) -> str:
        if isinstance(value, bool):
            return "ON" if value else "OFF"
        normalized = value.strip().upper()
        if normalized not in {"AUTO", "ON", "OFF"}:
            raise ValueError("mode must be AUTO, ON, OFF, True, or False")
        return normalized

    def set_charging(self, mode: Union[bool, str] = "AUTO") -> None:
        self.raw_command(f"CHARGING {self._mode(mode)}")

    def set_low_battery(self, mode: Union[bool, str] = "AUTO") -> None:
        self.raw_command(f"LOWBAT {self._mode(mode)}")

    def set_overload(self, enabled: bool) -> None:
        self.raw_command(f"OVERLOAD {'ON' if enabled else 'OFF'}")

    def set_need_replacement(self, enabled: bool) -> None:
        self.raw_command(f"REPLACE {'ON' if enabled else 'OFF'}")

    def set_communication_lost(self, enabled: bool) -> None:
        self.raw_command(f"COMMLOST {'ON' if enabled else 'OFF'}")

    def set_shutdown_requested(self, enabled: bool) -> None:
        self.raw_command(f"SHUTDOWN {'ON' if enabled else 'OFF'}")

    @contextmanager
    def armed_session(
        self, reset_on_exit: bool = True, lease_seconds: Optional[int] = None
    ) -> Iterator["UpsSimulator"]:
        """Arm for a test and restore a safe state when leaving the context.

        If the body raises and cleanup also fails, the original exception is
        preserved and the cleanup failure is emitted as a RuntimeWarning.
        """
        self.arm(True, lease_seconds=lease_seconds)
        try:
            yield self
        except BaseException:
            try:
                self._restore(reset_on_exit)
            except SimulatorError as cleanup_exc:
                warnings.warn(
                    f"could not restore simulator safe state: {cleanup_exc}",
                    RuntimeWarning,
                )
            raise
        self._restore(reset_on_exit)

    def _restore(self, reset_on_exit: bool) -> None:
        if reset_on_exit:
            self.reset()
        else:
            self.disarm()
