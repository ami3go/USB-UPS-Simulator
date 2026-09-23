from __future__ import annotations

from dataclasses import dataclass
import argparse
from typing import Dict, Optional, Sequence, Tuple

CONTROL_PORT = 5000
ARM_DEFAULT_LEASE_SEC = 120
ARM_MAX_LEASE_SEC = 3600
FULL_CHARGE_CAPACITY = 100
LOW_BATTERY_LIMIT = 5
REMAIN_TIME_LIMIT = 600
AVG_TIME_TO_EMPTY = 7200


@dataclass(frozen=True)
class HidStatus:
    charging: bool
    discharging: bool
    ac_present: bool
    battery_present: bool
    below_remaining_capacity_limit: bool
    remaining_time_limit_expired: bool
    need_replacement: bool
    fully_charged: bool
    fully_discharged: bool
    shutdown_requested: bool
    shutdown_imminent: bool
    communication_lost: bool
    overload: bool


class FirmwareSimulator:
    """Behavioral simulator for the Leonardo v2 control/state firmware.

    It models the command parser, safe state, derived UPS state, arming lease,
    TCP greeting, STATUS?/NETWORK? text, and command responses. It intentionally
    does not emulate AVR instructions, USB endpoint timing, SPI, DHCP, or W5500
    registers; those remain hardware-in-the-loop concerns.
    """

    SUPPORTED_COMMANDS = frozenset({
        "PING", "IDENT?", "HELP", "?", "STATUS?", "STATUS", "NETWORK?",
        "ARM", "RESET", "REPORT", "AC", "OVERLOAD", "REPLACE", "COMMLOST",
        "SHUTDOWN", "CHARGING", "LOWBAT", "BATTERY", "LOAD", "VOLTAGE",
        "INPUTVOLTAGE", "OUTPUTVOLTAGE", "RUNTIME", "STARTDELAY",
    })

    def __init__(self, *, ip: str = "169.254.42.42", gateway: str = "0.0.0.0",
                 subnet: str = "255.255.0.0", port: int = CONTROL_PORT) -> None:
        self.ip = ip
        self.gateway = gateway
        self.subnet = subnet
        self.port = int(port)
        self.now_ms = 0
        self._set_safe_state()
        self._update_model()

    def _set_safe_state(self) -> None:
        self.armed = False
        self.ac_present = True
        self.overload = False
        self.need_replacement = False
        self.communication_lost = False
        self.shutdown_requested = False
        self.runtime_auto = True
        self.charging_mode = "auto"
        self.low_battery_mode = "auto"
        self.arm_lease_ms = 0
        self.last_command_ms = 0
        self.battery_percent = 100
        self.battery_voltage_cv = 1300
        self.runtime_seconds = AVG_TIME_TO_EMPTY
        self.host_start_delay = -1
        self.host_shutdown_delay = -1
        self.host_reboot_delay = -1
        self.load_percent = 25
        self.input_voltage_cv = 23000
        self.output_voltage_cv = 23000

    @staticmethod
    def _parse_on_off(token: Optional[str]) -> Optional[bool]:
        if token is None:
            return None
        value = token.upper()
        if value in {"ON", "1", "TRUE"}:
            return True
        if value in {"OFF", "0", "FALSE"}:
            return False
        return None

    @classmethod
    def _parse_override(cls, token: Optional[str]) -> Optional[str]:
        if token is None:
            return None
        if token.upper() == "AUTO":
            return "auto"
        value = cls._parse_on_off(token)
        if value is None:
            return None
        return "on" if value else "off"

    @staticmethod
    def _parse_signed(token: Optional[str], minimum: int, maximum: int) -> Optional[int]:
        if token is None or token == "":
            return None
        negative = token.startswith("-")
        digits = token[1:] if negative else token
        if not digits or not digits.isdigit():
            return None
        parsed = int(digits)
        if parsed > 99999:
            return None
        if negative:
            parsed = -parsed
        if parsed < minimum or parsed > maximum:
            return None
        return parsed

    @classmethod
    def _parse_unsigned(cls, token: Optional[str], minimum: int, maximum: int) -> Optional[int]:
        return cls._parse_signed(token, minimum, maximum)

    def _update_model(self) -> None:
        if self.runtime_auto and FULL_CHARGE_CAPACITY:
            self.runtime_seconds = AVG_TIME_TO_EMPTY * self.battery_percent // FULL_CHARGE_CAPACITY
        auto_charging = self.ac_present and self.battery_percent < FULL_CHARGE_CAPACITY
        charging = auto_charging if self.charging_mode == "auto" else self.charging_mode == "on"
        discharging = (not self.ac_present) and self.battery_percent > 0
        auto_low = self.battery_percent <= LOW_BATTERY_LIMIT
        low_battery = auto_low if self.low_battery_mode == "auto" else self.low_battery_mode == "on"
        remaining_expired = discharging and self.runtime_seconds <= REMAIN_TIME_LIMIT
        shutdown_requested = self.armed and (self.shutdown_requested or self.host_shutdown_delay > 0)
        self.hid_status = HidStatus(
            charging=charging,
            discharging=discharging,
            ac_present=self.ac_present,
            battery_present=True,
            below_remaining_capacity_limit=low_battery,
            remaining_time_limit_expired=remaining_expired,
            need_replacement=self.need_replacement,
            fully_charged=self.battery_percent >= FULL_CHARGE_CAPACITY,
            fully_discharged=self.battery_percent == 0,
            shutdown_requested=shutdown_requested,
            shutdown_imminent=shutdown_requested or remaining_expired,
            communication_lost=self.communication_lost,
            overload=self.overload,
        )

    def _check_lease(self) -> None:
        if self.armed and self.arm_lease_ms:
            elapsed = (self.now_ms - self.last_command_ms) & 0xFFFFFFFF
            if elapsed >= self.arm_lease_ms:
                self._set_safe_state()
                self._update_model()

    def advance(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("milliseconds must be >= 0")
        self.now_ms = (self.now_ms + int(milliseconds)) & 0xFFFFFFFF
        self._check_lease()

    def tcp_greeting(self) -> Tuple[str, str]:
        return ("OK NutUPS HID Simulator v2", "OK ARMED" if self.armed else "OK DISARMED")

    def status_fields(self) -> Dict[str, str]:
        self._update_model()
        s = self.hid_status
        return {
            "armed": "1" if self.armed else "0",
            "ac": "1" if self.ac_present else "0",
            "battery": str(self.battery_percent),
            "runtime": str(self.runtime_seconds),
            "runtime_mode": "auto" if self.runtime_auto else "manual",
            "voltage_cv": str(self.battery_voltage_cv),
            "load": str(self.load_percent),
            "input_voltage_cv": str(self.input_voltage_cv),
            "output_voltage_cv": str(self.output_voltage_cv),
            "charging_mode": self.charging_mode,
            "charging_active": "1" if s.charging else "0",
            "lowbat_mode": self.low_battery_mode,
            "lowbat_active": "1" if s.below_remaining_capacity_limit else "0",
            "overload": "1" if self.overload else "0",
            "replace": "1" if self.need_replacement else "0",
            "commlost": "1" if self.communication_lost else "0",
            "shutdown": "1" if self.shutdown_requested else "0",
            "shutdown_imminent": "1" if s.shutdown_imminent else "0",
            "host_start_delay": str(self.host_start_delay),
            "host_shutdown_delay": str(self.host_shutdown_delay),
            "host_reboot_delay": str(self.host_reboot_delay),
            "ip": self.ip,
        }

    def _status_response(self) -> str:
        fields = self.status_fields()
        order = ("armed", "ac", "battery", "runtime", "runtime_mode", "voltage_cv",
                 "load", "input_voltage_cv", "output_voltage_cv", "charging_mode",
                 "charging_active", "lowbat_mode", "lowbat_active", "overload",
                 "replace", "commlost", "shutdown", "shutdown_imminent",
                 "host_start_delay", "host_shutdown_delay", "host_reboot_delay", "ip")
        return "OK " + " ".join(f"{key}={fields[key]}" for key in order)

    def _network_response(self) -> str:
        return f"OK ip={self.ip} gateway={self.gateway} subnet={self.subnet} port={self.port}"

    def command(self, line: str) -> str:
        line = line.replace("\r", "").lstrip(" \t")
        if not line:
            return ""
        tokens = line.split()
        command = tokens[0].upper()
        arg = tokens[1] if len(tokens) > 1 else None
        arg2 = tokens[2] if len(tokens) > 2 else None

        if self.armed:
            self.last_command_ms = self.now_ms

        if command == "PING":
            return "OK PONG"
        if command == "IDENT?":
            return "OK NutUPS HID Simulator v2"
        if command in {"HELP", "?"}:
            return "OK docs/CONTROL_PROTOCOL.md"
        if command in {"STATUS?", "STATUS"}:
            return self._status_response()
        if command == "NETWORK?":
            return self._network_response()

        if command == "ARM":
            enabled = self._parse_on_off(arg)
            if enabled is None:
                return "ERR mode"
            if enabled:
                lease_sec = ARM_DEFAULT_LEASE_SEC
                if arg2 is not None:
                    parsed = self._parse_unsigned(arg2, 0, ARM_MAX_LEASE_SEC)
                    if parsed is None:
                        return "ERR range"
                    lease_sec = parsed
                self.armed = True
                self.arm_lease_ms = lease_sec * 1000
                self.last_command_ms = self.now_ms
                self._update_model()
                return "OK armed"
            self._set_safe_state()
            self._update_model()
            return "OK safe"

        if command == "RESET":
            self._set_safe_state()
            self._update_model()
            return "OK safe"
        if command == "REPORT":
            self._update_model()
            return "OK"
        if not self.armed:
            return "ERR disarmed"

        if command in {"AC", "OVERLOAD", "REPLACE", "COMMLOST", "SHUTDOWN"}:
            enabled = self._parse_on_off(arg)
            if enabled is None:
                return "ERR mode"
            if command == "AC": self.ac_present = enabled
            elif command == "OVERLOAD": self.overload = enabled
            elif command == "REPLACE": self.need_replacement = enabled
            elif command == "COMMLOST": self.communication_lost = enabled
            else: self.shutdown_requested = enabled
            self._update_model()
            return "OK"

        if command in {"CHARGING", "LOWBAT"}:
            mode = self._parse_override(arg)
            if mode is None:
                return "ERR mode"
            if command == "CHARGING": self.charging_mode = mode
            else: self.low_battery_mode = mode
            self._update_model()
            return "OK"

        if command == "BATTERY":
            value = self._parse_unsigned(arg, 0, 100)
            if value is None: return "ERR range"
            self.battery_percent = value
        elif command == "LOAD":
            value = self._parse_unsigned(arg, 0, 100)
            if value is None: return "ERR range"
            self.load_percent = value
        elif command == "VOLTAGE":
            value = self._parse_unsigned(arg, 0, 65535)
            if value is None: return "ERR range"
            self.battery_voltage_cv = value
        elif command == "INPUTVOLTAGE":
            value = self._parse_unsigned(arg, 0, 65535)
            if value is None: return "ERR range"
            self.input_voltage_cv = value
        elif command == "OUTPUTVOLTAGE":
            value = self._parse_unsigned(arg, 0, 65535)
            if value is None: return "ERR range"
            self.output_voltage_cv = value
        elif command == "RUNTIME":
            if arg is not None and arg.upper() == "AUTO":
                self.runtime_auto = True
            else:
                value = self._parse_unsigned(arg, 0, 65535)
                if value is None: return "ERR range"
                self.runtime_auto = False
                self.runtime_seconds = value
        elif command == "STARTDELAY":
            value = self._parse_signed(arg, -1, 32767)
            if value is None: return "ERR range"
            self.host_start_delay = value
        else:
            return "ERR command"

        self._update_model()
        return "OK"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Behavioral simulator for NutUPS HID Simulator v2")
    parser.add_argument("commands", nargs="*", help="commands to execute; omit for interactive mode")
    parser.add_argument("--ip", default="169.254.42.42")
    parser.add_argument("--gateway", default="0.0.0.0")
    parser.add_argument("--subnet", default="255.255.0.0")
    args = parser.parse_args(argv)
    sim = FirmwareSimulator(ip=args.ip, gateway=args.gateway, subnet=args.subnet)
    for line in sim.tcp_greeting():
        print(line)
    if args.commands:
        for command in args.commands:
            print(f"> {command}")
            response = sim.command(command)
            if response:
                print(response)
        return 0
    print("Enter commands, 'advance <ms>' to advance millis(), or 'quit'.")
    while True:
        try:
            line = input("> ")
        except EOFError:
            print()
            return 0
        if line.strip().lower() in {"quit", "exit"}:
            return 0
        if line.strip().lower().startswith("advance "):
            try:
                _, value = line.split(None, 1)
                sim.advance(int(value, 10))
                print(f"OK millis={sim.now_ms}")
            except ValueError:
                print("ERR range")
            continue
        response = sim.command(line)
        if response:
            print(response)


if __name__ == "__main__":
    raise SystemExit(main())
