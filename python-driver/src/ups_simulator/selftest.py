from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Iterable, List, Optional, Sequence, Set, Tuple

from .driver import CommandError, SimulatorError, UpsSimulator


CONTROL_PORT = 5000
FALLBACK_IP = "169.254.42.42"
POWER_DEVICE_SIGNATURE = b"\x05\x84\x09\x04\xa1\x01"
NUT_EXTENSION_REPORT_IDS = (0x21, 0x22, 0x23, 0x24)
KNOWN_ARDUINO_VIDS = {0x2341, 0x2A03, 0x1B4F, 0x239A}
MAX_AUTO_SCAN_HOSTS = 1024


@dataclass(frozen=True)
class HidDevice:
    source: str
    identity: str
    exact_power_device: bool
    nut_extension: bool


class CheckFailed(RuntimeError):
    pass


def _ok(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[PASS] {label}{suffix}")


def _warn(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[WARN] {label}{suffix}")


def _fail(label: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[FAIL] {label}{suffix}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def _descriptor_is_power_device(data: bytes) -> bool:
    return POWER_DEVICE_SIGNATURE in data


def _descriptor_has_nut_extension(data: bytes) -> bool:
    return all(bytes((0x85, report_id)) in data for report_id in NUT_EXTENSION_REPORT_IDS)


def _parse_uevent(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _linux_hid_devices(sysfs_root: Path = Path("/sys/bus/hid/devices")) -> List[HidDevice]:
    matches: List[HidDevice] = []
    if not sysfs_root.is_dir():
        return matches

    for entry in sysfs_root.iterdir():
        descriptor_path = entry / "report_descriptor"
        try:
            descriptor = descriptor_path.read_bytes()
        except OSError:
            continue
        if not _descriptor_is_power_device(descriptor):
            continue

        identity = entry.name
        try:
            fields = _parse_uevent((entry / "uevent").read_text(errors="replace"))
            hid_id = fields.get("HID_ID", "")
            hid_name = fields.get("HID_NAME", "")
            parts = [part for part in (hid_id, hid_name) if part]
            if parts:
                identity = " ".join(parts)
        except OSError:
            pass

        matches.append(
            HidDevice(
                source=str(entry),
                identity=identity,
                exact_power_device=True,
                nut_extension=_descriptor_has_nut_extension(descriptor),
            )
        )
    return matches


def _hid_report_length(extra: bytes) -> Optional[int]:
    """Extract HID report-descriptor length from an interface HID descriptor."""
    offset = 0
    while offset + 2 <= len(extra):
        length = extra[offset]
        if length < 2 or offset + length > len(extra):
            break
        block = extra[offset : offset + length]
        if len(block) >= 9 and block[1] == 0x21:
            descriptors = block[5]
            pos = 6
            for _ in range(descriptors):
                if pos + 3 > len(block):
                    break
                dtype = block[pos]
                dlen = block[pos + 1] | (block[pos + 2] << 8)
                if dtype == 0x22:
                    return dlen
                pos += 3
        offset += length
    return None


def _pyusb_hid_devices() -> List[HidDevice]:
    """Best-effort HID Power Device detection for non-Linux hosts."""
    try:
        import usb.core  # type: ignore
        import usb.util  # type: ignore
    except ImportError:
        return []

    matches: List[HidDevice] = []
    try:
        devices = list(usb.core.find(find_all=True) or [])
    except Exception:
        return matches

    for dev in devices:
        try:
            config = dev.get_active_configuration()
        except Exception:
            try:
                config = dev[0]
            except Exception:
                continue

        manufacturer = ""
        product = ""
        try:
            manufacturer = usb.util.get_string(dev, dev.iManufacturer) or ""
            product = usb.util.get_string(dev, dev.iProduct) or ""
        except Exception:
            pass

        for interface in config:
            if getattr(interface, "bInterfaceClass", None) != 0x03:
                continue

            exact = False
            extension = False
            extra = bytes(getattr(interface, "extra_descriptors", b"") or b"")
            report_len = _hid_report_length(extra)
            if report_len:
                try:
                    descriptor = bytes(
                        dev.ctrl_transfer(
                            0x81,
                            0x06,
                            0x2200,
                            int(interface.bInterfaceNumber),
                            report_len,
                            timeout=1000,
                        )
                    )
                    exact = _descriptor_is_power_device(descriptor)
                    extension = _descriptor_has_nut_extension(descriptor)
                except Exception:
                    pass

            arduino_like = int(dev.idVendor) in KNOWN_ARDUINO_VIDS or "leonardo" in product.lower()
            if exact or arduino_like:
                ident = (
                    f"{int(dev.idVendor):04x}:{int(dev.idProduct):04x} "
                    f"{manufacturer} {product}"
                ).strip()
                matches.append(
                    HidDevice(
                        source=f"usb:{int(dev.bus or 0)}:{int(dev.address or 0)}",
                        identity=ident,
                        exact_power_device=exact,
                        nut_extension=extension,
                    )
                )
                break
    return matches


def discover_hid_devices() -> List[HidDevice]:
    matches = _linux_hid_devices()
    if matches:
        return matches
    return _pyusb_hid_devices()


def _load_psutil():
    try:
        import psutil  # type: ignore
    except ImportError as exc:
        raise CheckFailed(
            "LAN discovery requires psutil; install with "
            "'python -m pip install -e \"./python-driver[selftest]\"' or pass --host"
        ) from exc
    return psutil


def _local_ipv4_networks() -> List[Tuple[ipaddress.IPv4Address, ipaddress.IPv4Network]]:
    psutil = _load_psutil()
    result: List[Tuple[ipaddress.IPv4Address, ipaddress.IPv4Network]] = []
    for addresses in psutil.net_if_addrs().values():
        for addr in addresses:
            if addr.family != socket.AF_INET or not addr.address or not addr.netmask:
                continue
            try:
                ip = ipaddress.IPv4Address(addr.address)
                network = ipaddress.IPv4Network(f"{addr.address}/{addr.netmask}", strict=False)
            except ValueError:
                continue
            if ip.is_loopback or ip.is_unspecified:
                continue
            result.append((ip, network))
    return result


def _scan_network_for_interface(
    local_ip: ipaddress.IPv4Address, network: ipaddress.IPv4Network
) -> ipaddress.IPv4Network:
    if network.num_addresses <= MAX_AUTO_SCAN_HOSTS:
        return network
    # Keep automatic discovery bounded on large enterprise/home-lab subnets.
    # Users can supply --network when the simulator lives outside this local /24.
    return ipaddress.IPv4Network(f"{local_ip}/24", strict=False)


def _candidate_addresses(extra_networks: Sequence[str] = ()) -> List[str]:
    candidates: Set[str] = {FALLBACK_IP}
    own_ips: Set[str] = set()

    for local_ip, network in _local_ipv4_networks():
        own_ips.add(str(local_ip))
        scan_net = _scan_network_for_interface(local_ip, network)
        for host in scan_net.hosts():
            candidates.add(str(host))

    for cidr in extra_networks:
        network = ipaddress.IPv4Network(cidr, strict=False)
        if network.num_addresses > 65536:
            raise CheckFailed(f"refusing to scan very large network {network}; use a narrower CIDR")
        for host in network.hosts():
            candidates.add(str(host))

    candidates.difference_update(own_ips)
    return sorted(candidates, key=lambda value: int(ipaddress.IPv4Address(value)))


def _probe_simulator(host: str, timeout: float) -> Optional[str]:
    try:
        with UpsSimulator.tcp(host, CONTROL_PORT, timeout=timeout) as ups:
            if ups.ping() and ups.identify() == "NutUPS HID Simulator v2":
                return host
    except (SimulatorError, OSError):
        return None
    return None


def discover_simulators(
    extra_networks: Sequence[str], timeout: float, workers: int
) -> List[str]:
    candidates = _candidate_addresses(extra_networks)
    found: List[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_probe_simulator, host, timeout): host for host in candidates}
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(result)
    return sorted(set(found), key=lambda value: int(ipaddress.IPv4Address(value)))


def _nut_monitor_running() -> List[str]:
    """Return active NUT monitor processes/services that can shut down this PC."""
    found: Set[str] = set()
    try:
        psutil = _load_psutil()
        for proc in psutil.process_iter(["name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                cmdline = " ".join(proc.info.get("cmdline") or []).lower()
            except Exception:
                continue
            if name == "upsmon" or " upsmon" in f" {cmdline}":
                found.add(f"process:{proc.pid}:upsmon")
    except CheckFailed:
        pass

    if shutil.which("systemctl"):
        for unit in ("nut-monitor.service", "nut-monitor", "upsmon.service"):
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", "--quiet", unit],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode == 0:
                found.add(f"service:{unit}")
    return sorted(found)


def _check_status(ups: UpsSimulator, label: str, **expected) -> None:
    status = ups.status()
    for attr, value in expected.items():
        actual = getattr(status, attr)
        _require(actual == value, f"{label}: expected {attr}={value!r}, got {actual!r}")
    _ok(label)


def _expect_command_error(label: str, func) -> None:
    try:
        func()
    except CommandError:
        _ok(label)
        return
    raise CheckFailed(f"{label}: command unexpectedly succeeded")


def run_command_self_test(ups: UpsSimulator) -> None:
    """Exercise every v2 primary protocol command and verify read-back state."""
    ups.reset()
    _check_status(
        ups,
        "RESET safe state",
        armed=False,
        ac_present=True,
        battery_percent=100,
        load_percent=25,
        input_voltage_centivolts=23000,
        output_voltage_centivolts=23000,
    )

    _require(ups.ping(), "PING did not return PONG")
    _ok("PING")
    _require(ups.identify() == "NutUPS HID Simulator v2", "IDENT? returned unexpected firmware")
    _ok("IDENT?")
    network = ups.network_status()
    _require(network.port == CONTROL_PORT, f"NETWORK? returned port {network.port}")
    _ok("NETWORK?", network.ip)
    ups.status()
    _ok("STATUS?")

    for command in ("HELP", "?"):
        response = ups.transport.command(command)
        _require(response.startswith("OK "), f"{command} returned {response!r}")
        _ok(command)

    _expect_command_error("disarmed mutation guard", lambda: ups.set_load(30))

    ups.arm(lease_seconds=120)
    _check_status(ups, "ARM ON", armed=True)

    ups.report()
    _ok("REPORT")

    ups.set_battery(73)
    _check_status(ups, "BATTERY", battery_percent=73)

    ups.set_runtime(1234)
    _check_status(ups, "RUNTIME manual", runtime_seconds=1234, runtime_mode="manual")
    ups.set_runtime(None)
    _check_status(ups, "RUNTIME AUTO", runtime_mode="auto")

    ups.set_voltage_centivolts(1325)
    _check_status(ups, "VOLTAGE", voltage_centivolts=1325)

    ups.set_load(42)
    _check_status(ups, "LOAD", load_percent=42)

    ups.set_input_voltage_centivolts(22850)
    _check_status(ups, "INPUTVOLTAGE", input_voltage_centivolts=22850)

    ups.set_output_voltage_centivolts(22950)
    _check_status(ups, "OUTPUTVOLTAGE", output_voltage_centivolts=22950)

    ups.set_start_delay(15)
    _check_status(ups, "STARTDELAY", host_start_delay=15)

    ups.set_charging("on")
    _check_status(ups, "CHARGING ON", charging_mode="on", charging_active=True)
    ups.set_charging("off")
    _check_status(ups, "CHARGING OFF", charging_mode="off", charging_active=False)
    ups.set_charging("auto")
    _check_status(ups, "CHARGING AUTO", charging_mode="auto")

    # Potentially actionable UPS states are kept very brief. The caller checks
    # that no live upsmon is present before this suite is entered.
    ups.set_ac(False)
    _check_status(ups, "AC OFF", ac_present=False)
    ups.set_ac(True)
    _check_status(ups, "AC ON", ac_present=True)

    ups.set_low_battery("on")
    _check_status(ups, "LOWBAT ON", low_battery_mode="on", low_battery_active=True)
    ups.set_low_battery("off")
    _check_status(ups, "LOWBAT OFF", low_battery_mode="off", low_battery_active=False)
    ups.set_low_battery("auto")
    _check_status(ups, "LOWBAT AUTO", low_battery_mode="auto")

    ups.set_overload(True)
    _check_status(ups, "OVERLOAD ON", overload=True)
    ups.set_overload(False)
    _check_status(ups, "OVERLOAD OFF", overload=False)

    ups.set_need_replacement(True)
    _check_status(ups, "REPLACE ON", need_replacement=True)
    ups.set_need_replacement(False)
    _check_status(ups, "REPLACE OFF", need_replacement=False)

    ups.set_communication_lost(True)
    _check_status(ups, "COMMLOST ON", communication_lost=True)
    ups.set_communication_lost(False)
    _check_status(ups, "COMMLOST OFF", communication_lost=False)

    ups.set_shutdown_requested(True)
    _check_status(
        ups,
        "SHUTDOWN ON",
        shutdown_requested=True,
        shutdown_imminent=True,
    )
    ups.set_shutdown_requested(False)
    _check_status(ups, "SHUTDOWN OFF", shutdown_requested=False)

    ups.disarm()
    _check_status(ups, "ARM OFF", armed=False, ac_present=True, battery_percent=100)

    ups.arm(lease_seconds=30)
    _check_status(ups, "ARM ON lease", armed=True)
    ups.reset()
    _check_status(ups, "final RESET", armed=False, ac_present=True, battery_percent=100)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ups-sim-selftest",
        description=(
            "Discover a NutUPS Leonardo/W5500 on the local LAN, verify the USB HID "
            "Power Device, and exercise the v2 control protocol."
        ),
    )
    parser.add_argument("--host", help="simulator IP/hostname; skips automatic LAN scan")
    parser.add_argument(
        "--network",
        action="append",
        default=[],
        metavar="CIDR",
        help="additional IPv4 network to scan; may be repeated",
    )
    parser.add_argument("--scan-timeout", type=float, default=0.20, help="TCP probe timeout (default: 0.20 s)")
    parser.add_argument("--workers", type=int, default=64, help="parallel discovery workers (default: 64)")
    parser.add_argument("--timeout", type=float, default=2.0, help="normal command timeout (default: 2 s)")
    parser.add_argument(
        "--allow-live-nut",
        action="store_true",
        help="allow OB/LB/shutdown-state tests even when upsmon appears to be running",
    )
    parser.add_argument(
        "--skip-hid",
        action="store_true",
        help="skip USB HID detection (use only for Ethernet-only diagnostics)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    print("NutUPS hardware self-test")
    print("=========================")

    try:
        if not args.skip_hid:
            hid_devices = discover_hid_devices()
            _require(hid_devices, "no USB HID UPS/Leonardo candidate found")
            exact = [device for device in hid_devices if device.exact_power_device]
            if exact:
                for device in exact:
                    detail = device.identity
                    if device.nut_extension:
                        detail += "; NUT extension report IDs present"
                    _ok("USB HID Power Device", detail)
                _require(
                    any(device.nut_extension for device in exact),
                    "HID Power Device found but NUT extension report IDs 0x21..0x24 were not detected",
                )
            else:
                for device in hid_devices:
                    _warn("USB HID candidate", device.identity)
                _warn(
                    "HID descriptor verification",
                    "platform/backend could not read the report descriptor; candidate detection only",
                )

        if args.host:
            hosts = [args.host]
        else:
            print("[INFO] scanning local LAN for NutUPS TCP/5000 ...")
            hosts = discover_simulators(args.network, args.scan_timeout, args.workers)
            _require(hosts, "no NutUPS HID Simulator v2 found on the scanned LAN")
            _require(
                len(hosts) == 1,
                "multiple simulators found: " + ", ".join(hosts) + "; rerun with --host",
            )
        host = hosts[0]
        _ok("Ethernet simulator discovery", host)

        monitors = _nut_monitor_running()
        if monitors and not args.allow_live_nut:
            raise CheckFailed(
                "live NUT monitor detected (" + ", ".join(monitors) + "). "
                "The full command test briefly asserts OB/LB/shutdown states and could shut down this PC. "
                "Stop upsmon for the self-test, or deliberately use --allow-live-nut."
            )
        if monitors:
            _warn("live NUT monitor override", ", ".join(monitors))
        else:
            _ok("shutdown safety pre-check", "no active upsmon detected")

        with UpsSimulator.tcp(host, CONTROL_PORT, timeout=args.timeout) as ups:
            try:
                run_command_self_test(ups)
            finally:
                try:
                    ups.reset()
                except SimulatorError as exc:
                    _fail("emergency RESET", str(exc))
                    raise

        _ok("self-test complete", "simulator restored to safe RESET state")
        return 0
    except (CheckFailed, SimulatorError, ValueError) as exc:
        _fail("self-test", str(exc))
        return 1
    except KeyboardInterrupt:
        _fail("self-test", "interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
