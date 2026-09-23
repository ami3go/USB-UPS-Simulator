from pathlib import Path
import re
import unittest

from ups_simulator.driver import CommandError, UpsSimulator
from ups_simulator.firmware_sim import FirmwareSimulator


class SimTransport:
    def __init__(self, firmware: FirmwareSimulator) -> None:
        self.firmware = firmware
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def command(self, command: str) -> str:
        self.connect()
        return self.firmware.command(command)


class FirmwareSimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sim = FirmwareSimulator()

    def assert_fields(self, **expected) -> None:
        fields = self.sim.status_fields()
        for key, value in expected.items():
            self.assertEqual(fields[key], str(value), key)

    def test_boot_state_and_tcp_greeting(self) -> None:
        self.assertEqual(
            self.sim.tcp_greeting(),
            ("OK NutUPS HID Simulator v2", "OK DISARMED"),
        )
        self.assert_fields(
            armed=0,
            ac=1,
            battery=100,
            runtime=7200,
            runtime_mode="auto",
            voltage_cv=1300,
            load=25,
            input_voltage_cv=23000,
            output_voltage_cv=23000,
            charging_mode="auto",
            charging_active=0,
            lowbat_mode="auto",
            lowbat_active=0,
            overload=0,
            replace=0,
            commlost=0,
            shutdown=0,
            shutdown_imminent=0,
            host_start_delay=-1,
            host_shutdown_delay=-1,
            host_reboot_delay=-1,
            ip="169.254.42.42",
        )

    def test_exact_read_only_responses(self) -> None:
        self.assertEqual(self.sim.command("PING"), "OK PONG")
        self.assertEqual(self.sim.command("IDENT?"), "OK NutUPS HID Simulator v2")
        self.assertEqual(self.sim.command("HELP"), "OK docs/CONTROL_PROTOCOL.md")
        self.assertEqual(self.sim.command("?"), "OK docs/CONTROL_PROTOCOL.md")
        self.assertEqual(
            self.sim.command("NETWORK?"),
            "OK ip=169.254.42.42 gateway=0.0.0.0 subnet=255.255.0.0 port=5000",
        )
        expected = (
            "OK armed=0 ac=1 battery=100 runtime=7200 runtime_mode=auto "
            "voltage_cv=1300 load=25 input_voltage_cv=23000 output_voltage_cv=23000 "
            "charging_mode=auto charging_active=0 lowbat_mode=auto lowbat_active=0 "
            "overload=0 replace=0 commlost=0 shutdown=0 shutdown_imminent=0 "
            "host_start_delay=-1 host_shutdown_delay=-1 host_reboot_delay=-1 "
            "ip=169.254.42.42"
        )
        self.assertEqual(self.sim.command("STATUS?"), expected)
        self.assertEqual(self.sim.command("STATUS"), expected)

    def test_command_names_match_actual_firmware_source(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        source = (repo_root / "examples/UPS_Simulator_Ethernet/UPS_Simulator_Ethernet.ino").read_text()
        commands = set(re.findall(r"strcasecmp\(command, \"([^\"]+)\"\)", source))
        commands.update(re.findall(r"strcmp\(command, \"([^\"]+)\"\)", source))
        self.assertEqual(commands, set(FirmwareSimulator.SUPPORTED_COMMANDS))

    def test_disarmed_mutations_are_rejected(self) -> None:
        mutations = (
            "AC OFF", "OVERLOAD ON", "REPLACE ON", "COMMLOST ON", "SHUTDOWN ON",
            "CHARGING ON", "LOWBAT ON", "BATTERY 50", "LOAD 50", "VOLTAGE 1200",
            "INPUTVOLTAGE 22000", "OUTPUTVOLTAGE 22000", "RUNTIME 60", "STARTDELAY 1",
            "BOGUS",
        )
        for command in mutations:
            with self.subTest(command=command):
                self.assertEqual(self.sim.command(command), "ERR disarmed")

    def test_arm_modes_and_lease_boundaries(self) -> None:
        for token in ("ON", "1", "TRUE", "on", "true"):
            with self.subTest(token=token):
                sim = FirmwareSimulator()
                self.assertEqual(sim.command(f"ARM {token}"), "OK armed")
                self.assertTrue(sim.armed)
                self.assertEqual(sim.arm_lease_ms, 120000)
        self.assertEqual(self.sim.command("ARM maybe"), "ERR mode")
        self.assertEqual(self.sim.command("ARM ON -1"), "ERR range")
        self.assertEqual(self.sim.command("ARM ON 3601"), "ERR range")
        self.assertEqual(self.sim.command("ARM ON 0"), "OK armed")
        self.assertEqual(self.sim.arm_lease_ms, 0)
        self.assertEqual(self.sim.command("ARM ON 3600"), "OK armed")
        self.assertEqual(self.sim.arm_lease_ms, 3600000)

    def test_arm_off_and_reset_restore_safe_state(self) -> None:
        self.sim.command("ARM ON")
        self.sim.command("AC OFF")
        self.sim.command("BATTERY 4")
        self.sim.command("LOAD 99")
        self.sim.command("OVERLOAD ON")
        self.assertEqual(self.sim.command("ARM OFF"), "OK safe")
        self.assert_fields(armed=0, ac=1, battery=100, load=25, overload=0)

        self.sim.command("ARM ON")
        self.sim.command("REPLACE ON")
        self.assertEqual(self.sim.command("RESET"), "OK safe")
        self.assert_fields(armed=0, replace=0, battery=100)

    def test_boolean_commands_and_aliases(self) -> None:
        self.sim.command("ARM ON")
        for command, attr in (
            ("AC", "ac_present"),
            ("OVERLOAD", "overload"),
            ("REPLACE", "need_replacement"),
            ("COMMLOST", "communication_lost"),
            ("SHUTDOWN", "shutdown_requested"),
        ):
            for token in ("ON", "1", "TRUE"):
                with self.subTest(command=command, token=token):
                    self.assertEqual(self.sim.command(f"{command} {token}"), "OK")
                    self.assertTrue(getattr(self.sim, attr))
            for token in ("OFF", "0", "FALSE"):
                with self.subTest(command=command, token=token):
                    self.assertEqual(self.sim.command(f"{command} {token}"), "OK")
                    self.assertFalse(getattr(self.sim, attr))
            self.assertEqual(self.sim.command(f"{command} BAD"), "ERR mode")

    def test_override_modes_and_derived_charging_low_battery(self) -> None:
        self.sim.command("ARM ON")
        self.sim.command("BATTERY 50")
        self.assert_fields(charging_mode="auto", charging_active=1)
        self.assertEqual(self.sim.command("CHARGING OFF"), "OK")
        self.assert_fields(charging_mode="off", charging_active=0)
        self.assertEqual(self.sim.command("CHARGING ON"), "OK")
        self.assert_fields(charging_mode="on", charging_active=1)
        self.assertEqual(self.sim.command("CHARGING AUTO"), "OK")
        self.assert_fields(charging_mode="auto", charging_active=1)
        self.assertEqual(self.sim.command("CHARGING BAD"), "ERR mode")

        self.sim.command("BATTERY 4")
        self.assert_fields(lowbat_mode="auto", lowbat_active=1)
        self.assertEqual(self.sim.command("LOWBAT OFF"), "OK")
        self.assert_fields(lowbat_mode="off", lowbat_active=0)
        self.assertEqual(self.sim.command("LOWBAT ON"), "OK")
        self.assert_fields(lowbat_mode="on", lowbat_active=1)
        self.assertEqual(self.sim.command("LOWBAT AUTO"), "OK")
        self.assert_fields(lowbat_mode="auto", lowbat_active=1)
        self.assertEqual(self.sim.command("LOWBAT BAD"), "ERR mode")

    def test_numeric_commands_boundaries_and_errors(self) -> None:
        self.sim.command("ARM ON")
        cases = (
            ("BATTERY", 0, 100, "battery_percent"),
            ("LOAD", 0, 100, "load_percent"),
            ("VOLTAGE", 0, 65535, "battery_voltage_cv"),
            ("INPUTVOLTAGE", 0, 65535, "input_voltage_cv"),
            ("OUTPUTVOLTAGE", 0, 65535, "output_voltage_cv"),
            ("RUNTIME", 0, 65535, "runtime_seconds"),
            ("STARTDELAY", -1, 32767, "host_start_delay"),
        )
        for command, minimum, maximum, attr in cases:
            with self.subTest(command=command, value=minimum):
                self.assertEqual(self.sim.command(f"{command} {minimum}"), "OK")
                self.assertEqual(getattr(self.sim, attr), minimum)
            with self.subTest(command=command, value=maximum):
                self.assertEqual(self.sim.command(f"{command} {maximum}"), "OK")
                self.assertEqual(getattr(self.sim, attr), maximum)
            for invalid in (str(minimum - 1), str(maximum + 1), "abc", ""):
                with self.subTest(command=command, invalid=invalid):
                    self.assertEqual(self.sim.command(f"{command} {invalid}"), "ERR range")

    def test_runtime_auto_and_derived_runtime(self) -> None:
        self.sim.command("ARM ON")
        self.sim.command("BATTERY 50")
        self.assert_fields(runtime=3600, runtime_mode="auto")
        self.sim.command("RUNTIME 123")
        self.assert_fields(runtime=123, runtime_mode="manual")
        self.sim.command("BATTERY 25")
        self.assert_fields(runtime=123, runtime_mode="manual")
        self.sim.command("RUNTIME AUTO")
        self.assert_fields(runtime=1800, runtime_mode="auto")

    def test_outage_low_battery_and_shutdown_imminent_logic(self) -> None:
        self.sim.command("ARM ON")
        self.sim.command("AC OFF")
        self.sim.command("BATTERY 4")
        self.sim.command("RUNTIME 300")
        self.assertTrue(self.sim.hid_status.discharging)
        self.assertTrue(self.sim.hid_status.below_remaining_capacity_limit)
        self.assertTrue(self.sim.hid_status.remaining_time_limit_expired)
        self.assertTrue(self.sim.hid_status.shutdown_imminent)
        self.assert_fields(ac=0, lowbat_active=1, shutdown_imminent=1)

        self.sim.command("AC ON")
        self.sim.command("SHUTDOWN ON")
        self.assertTrue(self.sim.hid_status.shutdown_requested)
        self.assertTrue(self.sim.hid_status.shutdown_imminent)
        self.assert_fields(ac=1, shutdown=1, shutdown_imminent=1)

    def test_lease_expiry_and_refresh(self) -> None:
        self.sim.command("ARM ON 2")
        self.sim.command("AC OFF")
        self.sim.advance(1999)
        self.assertTrue(self.sim.armed)
        self.sim.command("PING")
        self.sim.advance(1999)
        self.assertTrue(self.sim.armed)
        self.sim.advance(1)
        self.assertFalse(self.sim.armed)
        self.assert_fields(ac=1, battery=100, load=25)

    def test_zero_lease_never_expires(self) -> None:
        self.sim.command("ARM ON 0")
        self.sim.command("AC OFF")
        self.sim.advance(0xFFFFFFFF)
        self.assertTrue(self.sim.armed)
        self.assertFalse(self.sim.ac_present)

    def test_case_insensitive_and_extra_tokens_match_firmware_parser(self) -> None:
        self.assertEqual(self.sim.command("  ping"), "OK PONG")
        self.assertEqual(self.sim.command("arm on 120 ignored tokens"), "OK armed")
        self.assertEqual(self.sim.command("load 77 ignored"), "OK")
        self.assertEqual(self.sim.load_percent, 77)

    def test_missing_and_bad_arguments_return_expected_error_classes(self) -> None:
        self.assertEqual(self.sim.command("ARM"), "ERR mode")
        self.sim.command("ARM ON")
        for command in ("AC", "OVERLOAD", "REPLACE", "COMMLOST", "SHUTDOWN", "CHARGING", "LOWBAT"):
            with self.subTest(command=command):
                self.assertEqual(self.sim.command(command), "ERR mode")
        for command in ("BATTERY", "LOAD", "VOLTAGE", "INPUTVOLTAGE", "OUTPUTVOLTAGE", "RUNTIME", "STARTDELAY"):
            with self.subTest(command=command):
                self.assertEqual(self.sim.command(command), "ERR range")
        self.assertEqual(self.sim.command("UNKNOWN"), "ERR command")

    def test_report_is_allowed_while_disarmed(self) -> None:
        self.assertEqual(self.sim.command("REPORT"), "OK")

    def test_driver_api_runs_end_to_end_against_behavior_simulator(self) -> None:
        driver = UpsSimulator(SimTransport(self.sim))
        driver.connect()
        self.assertTrue(driver.ping())
        self.assertEqual(driver.identify(), "NutUPS HID Simulator v2")
        self.assertEqual(driver.network_status().port, 5000)
        driver.arm(lease_seconds=120)
        driver.set_ac(False)
        driver.set_battery(40)
        driver.set_load(65)
        driver.set_runtime(300)
        driver.set_voltage(13.2)
        driver.set_input_voltage(228.5)
        driver.set_output_voltage(230.1)
        driver.set_start_delay(30)
        driver.set_charging("auto")
        driver.set_low_battery("auto")
        driver.set_overload(True)
        driver.set_need_replacement(True)
        driver.set_communication_lost(True)
        driver.set_shutdown_requested(True)
        status = driver.status()
        self.assertTrue(status.armed)
        self.assertFalse(status.ac_present)
        self.assertEqual(status.battery_percent, 40)
        self.assertEqual(status.load_percent, 65)
        self.assertEqual(status.runtime_seconds, 300)
        self.assertEqual(status.voltage_centivolts, 1320)
        self.assertEqual(status.input_voltage_centivolts, 22850)
        self.assertEqual(status.output_voltage_centivolts, 23010)
        self.assertTrue(status.overload)
        self.assertTrue(status.need_replacement)
        self.assertTrue(status.communication_lost)
        self.assertTrue(status.shutdown_requested)
        driver.reset()
        self.assertFalse(driver.status().armed)

    def test_driver_sees_firmware_errors_as_command_errors(self) -> None:
        driver = UpsSimulator(SimTransport(self.sim))
        with self.assertRaises(CommandError):
            driver.set_load(50)


if __name__ == "__main__":
    unittest.main()
