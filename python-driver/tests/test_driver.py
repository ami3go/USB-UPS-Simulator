import contextlib
import io
import sys
import types
import unittest

from ups_simulator import (
    CommandError,
    ProtocolError,
    SerialLineTransport,
    TransportError,
    UpsSimulator,
)


STATUS = (
    "OK armed=1 ac=0 battery=4 runtime=300 runtime_mode=manual "
    "voltage_cv=1260 load=55 input_voltage_cv=23120 output_voltage_cv=22980 "
    "charging_mode=auto charging_active=0 lowbat_mode=auto lowbat_active=1 "
    "overload=0 replace=0 commlost=0 shutdown=0 shutdown_imminent=1 "
    "host_start_delay=30 host_shutdown_delay=-1 host_reboot_delay=-1 "
    "ip=192.168.1.50"
)
NETWORK = "OK ip=192.168.1.50 gateway=192.168.1.1 subnet=255.255.255.0 port=5000"


class FakeTransport:
    def __init__(self):
        self.commands = []
        self.connected = False

    def connect(self):
        self.connected = True

    def close(self):
        self.connected = False

    def command(self, command):
        self.commands.append(command)
        if command == "PING":
            return "OK PONG"
        if command == "IDENT?":
            return "OK NutUPS HID Simulator v2"
        if command == "STATUS?":
            return STATUS
        if command == "NETWORK?":
            return NETWORK
        if command == "FAIL":
            return "ERR deliberate test failure"
        return "OK"


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.sim = UpsSimulator(self.transport)

    def test_connect_checks_firmware_version(self):
        self.assertIs(self.sim.connect(), self.sim)
        self.assertEqual(self.transport.commands, ["IDENT?"])

    def test_ping_and_identify(self):
        self.assertTrue(self.sim.ping())
        self.assertEqual(self.sim.identify(), "NutUPS HID Simulator v2")

    def test_status_is_parsed(self):
        status = self.sim.status()
        self.assertTrue(status.armed)
        self.assertFalse(status.ac_present)
        self.assertEqual(status.battery_percent, 4)
        self.assertEqual(status.runtime_seconds, 300)
        self.assertEqual(status.runtime_mode, "manual")
        self.assertEqual(status.voltage_centivolts, 1260)
        self.assertAlmostEqual(status.voltage_volts, 12.60)
        self.assertEqual(status.load_percent, 55)
        self.assertAlmostEqual(status.input_voltage_volts, 231.20)
        self.assertAlmostEqual(status.output_voltage_volts, 229.80)
        self.assertEqual(status.host_start_delay, 30)
        self.assertTrue(status.low_battery_active)
        self.assertTrue(status.shutdown_imminent)
        self.assertEqual(status.ip, "192.168.1.50")

    def test_network_status_is_parsed(self):
        network = self.sim.network_status()
        self.assertEqual(network.ip, "192.168.1.50")
        self.assertEqual(network.gateway, "192.168.1.1")
        self.assertEqual(network.subnet, "255.255.255.0")
        self.assertEqual(network.port, 5000)

    def test_high_level_commands(self):
        self.sim.arm(lease_seconds=45)
        self.sim.set_ac(False)
        self.sim.set_battery(25)
        self.sim.set_load(60)
        self.sim.set_runtime(1200)
        self.sim.set_runtime(None)
        self.sim.set_voltage(13.25)
        self.sim.set_input_voltage(231.5)
        self.sim.set_output_voltage(229.75)
        self.sim.set_start_delay(30)
        self.sim.set_charging("auto")
        self.sim.set_low_battery(True)
        self.sim.set_overload(True)
        self.sim.set_need_replacement(True)
        self.sim.set_communication_lost(True)
        self.sim.set_shutdown_requested(True)
        self.sim.report()
        self.assertEqual(
            self.transport.commands,
            [
                "ARM ON 45",
                "AC OFF",
                "BATTERY 25",
                "LOAD 60",
                "RUNTIME 1200",
                "RUNTIME AUTO",
                "VOLTAGE 1325",
                "INPUTVOLTAGE 23150",
                "OUTPUTVOLTAGE 22975",
                "STARTDELAY 30",
                "CHARGING AUTO",
                "LOWBAT ON",
                "OVERLOAD ON",
                "REPLACE ON",
                "COMMLOST ON",
                "SHUTDOWN ON",
                "REPORT",
            ],
        )

    def test_invalid_ranges_are_rejected_locally(self):
        with self.assertRaises(ValueError):
            self.sim.set_battery(101)
        with self.assertRaises(ValueError):
            self.sim.set_load(-1)
        with self.assertRaises(ValueError):
            self.sim.set_runtime(-1)
        with self.assertRaises(ValueError):
            self.sim.set_voltage_centivolts(65536)
        with self.assertRaises(ValueError):
            self.sim.set_input_voltage(700.0)
        with self.assertRaises(ValueError):
            self.sim.set_start_delay(-2)
        with self.assertRaises(ValueError):
            self.sim.arm(lease_seconds=3601)
        self.assertEqual(self.transport.commands, [])

    def test_firmware_error_becomes_exception(self):
        with self.assertRaises(CommandError):
            self.sim.raw_command("FAIL")

    def test_armed_session_resets_after_exception(self):
        with self.assertRaises(RuntimeError):
            with self.sim.armed_session(lease_seconds=60):
                self.sim.set_ac(False)
                raise RuntimeError("test failed")
        self.assertEqual(self.transport.commands, ["ARM ON 60", "AC OFF", "RESET"])


class FailingResetTransport(FakeTransport):
    def command(self, command):
        if command == "RESET":
            raise TransportError("link lost")
        return super().command(command)


class NotPongTransport(FakeTransport):
    def command(self, command):
        if command == "PING":
            return "OK NOT-PONG"
        return super().command(command)


class OldFirmwareTransport(FakeTransport):
    def command(self, command):
        if command == "IDENT?":
            self.commands.append(command)
            return "OK NutUPS HID Simulator v1"
        return super().command(command)


class FakeSerial:
    """pyserial stand-in with a late boot banner still in flight."""

    def __init__(self, *args, **kwargs):
        self.rx = [b"NutUPS ready\r\n"]

    def reset_input_buffer(self):
        pass

    def write(self, data):
        command = data.strip()
        if command == b"PING":
            self.rx.append(b"OK PONG\r\n")
        elif command == b"IDENT?":
            self.rx.append(b"OK NutUPS HID Simulator v2\r\n")
        else:
            self.rx.append(b"OK\r\n")

    def flush(self):
        pass

    def readline(self):
        return self.rx.pop(0) if self.rx else b""

    def close(self):
        pass


class RobustnessTests(unittest.TestCase):
    def test_armed_session_keeps_original_error_when_cleanup_fails(self):
        sim = UpsSimulator(FailingResetTransport())
        with self.assertWarns(RuntimeWarning):
            with self.assertRaises(ValueError):
                with sim.armed_session():
                    raise ValueError("test failed")

    def test_cli_ping_failure_returns_nonzero(self):
        from ups_simulator import cli

        original = cli._make_client
        cli._make_client = lambda args: UpsSimulator(NotPongTransport())
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["--host", "sim", "ping"]), 1)
        finally:
            cli._make_client = original

    def test_serial_transport_skips_boot_banner(self):
        module = types.ModuleType("serial")
        module.Serial = FakeSerial
        sys.modules["serial"] = module
        try:
            transport = SerialLineTransport("/dev/ttyFAKE")
            transport.connect()
            self.assertEqual(transport.command("IDENT?"), "OK NutUPS HID Simulator v2")
        finally:
            del sys.modules["serial"]

    def test_old_firmware_is_rejected_on_connect(self):
        sim = UpsSimulator(OldFirmwareTransport())
        with self.assertRaises(ProtocolError):
            sim.connect()


if __name__ == "__main__":
    unittest.main()
