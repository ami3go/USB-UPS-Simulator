from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from typing import Optional, Sequence

from .driver import SimulatorError, UpsSimulator


def _state(value: str) -> bool:
    value = value.lower()
    if value == "on":
        return True
    if value == "off":
        return False
    raise argparse.ArgumentTypeError("expected on or off")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Control the NutUPS Arduino UPS simulator")
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument("--host", help="W5500 simulator IP address or hostname")
    transport.add_argument("--serial", dest="serial_port", help="UART serial port, e.g. /dev/ttyUSB0")
    parser.add_argument("--port", type=int, default=5000, help="TCP port (default: 5000)")
    parser.add_argument("--baud", type=int, default=115200, help="UART baud rate (default: 115200)")
    parser.add_argument("--timeout", type=float, default=2.0, help="I/O timeout in seconds")

    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("ping", "identify", "status", "network", "arm", "disarm", "reset", "report"):
        commands.add_parser(name)

    p = commands.add_parser("ac")
    p.add_argument("state", type=_state, metavar="on|off")

    p = commands.add_parser("battery")
    p.add_argument("percent", type=int)

    p = commands.add_parser("load")
    p.add_argument("percent", type=int)

    p = commands.add_parser("runtime")
    p.add_argument("seconds", help="seconds or 'auto'")

    p = commands.add_parser("voltage")
    p.add_argument("volts", type=float)

    p = commands.add_parser("input-voltage")
    p.add_argument("volts", type=float)

    p = commands.add_parser("output-voltage")
    p.add_argument("volts", type=float)

    p = commands.add_parser("start-delay")
    p.add_argument("seconds", type=int)

    for name in ("charging", "lowbat"):
        p = commands.add_parser(name)
        p.add_argument("mode", choices=("auto", "on", "off"))

    for name in ("overload", "replace", "commlost", "shutdown"):
        p = commands.add_parser(name)
        p.add_argument("state", type=_state, metavar="on|off")

    p = commands.add_parser("raw")
    p.add_argument("text", nargs=argparse.REMAINDER, help="single-line firmware command")
    return parser


def _make_client(args: argparse.Namespace) -> UpsSimulator:
    if args.host:
        return UpsSimulator.tcp(args.host, port=args.port, timeout=args.timeout)
    return UpsSimulator.serial(args.serial_port, baudrate=args.baud, timeout=args.timeout)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with _make_client(args) as sim:
            cmd = args.command
            if cmd == "ping":
                print("PONG" if sim.ping() else "unexpected response")
            elif cmd == "identify":
                print(sim.identify())
            elif cmd == "status":
                print(json.dumps(asdict(sim.status()), indent=2))
            elif cmd == "network":
                print(json.dumps(asdict(sim.network_status()), indent=2))
            elif cmd == "arm":
                sim.arm()
                print("armed")
            elif cmd == "disarm":
                sim.disarm()
                print("disarmed; safe online state restored")
            elif cmd == "reset":
                sim.reset()
                print("reset; safe online state restored")
            elif cmd == "report":
                sim.report()
                print("report sent")
            elif cmd == "ac":
                sim.set_ac(args.state)
            elif cmd == "battery":
                sim.set_battery(args.percent)
            elif cmd == "load":
                sim.set_load(args.percent)
            elif cmd == "runtime":
                if args.seconds.lower() == "auto":
                    sim.set_runtime(None)
                else:
                    sim.set_runtime(int(args.seconds))
            elif cmd == "voltage":
                sim.set_voltage(args.volts)
            elif cmd == "input-voltage":
                sim.set_input_voltage(args.volts)
            elif cmd == "output-voltage":
                sim.set_output_voltage(args.volts)
            elif cmd == "start-delay":
                sim.set_start_delay(args.seconds)
            elif cmd == "charging":
                sim.set_charging(args.mode)
            elif cmd == "lowbat":
                sim.set_low_battery(args.mode)
            elif cmd == "overload":
                sim.set_overload(args.state)
            elif cmd == "replace":
                sim.set_need_replacement(args.state)
            elif cmd == "commlost":
                sim.set_communication_lost(args.state)
            elif cmd == "shutdown":
                sim.set_shutdown_requested(args.state)
            elif cmd == "raw":
                if not args.text:
                    parser.error("raw requires a command")
                print(sim.raw_command(" ".join(args.text)))
            else:
                parser.error(f"unsupported command: {cmd}")
        return 0
    except (SimulatorError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
