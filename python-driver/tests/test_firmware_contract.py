from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
FIRMWARE = REPO / "examples" / "UPS_Simulator_Ethernet" / "UPS_Simulator_Ethernet.ino"
DRIVER = REPO / "python-driver" / "src" / "ups_simulator" / "driver.py"


class FirmwareContractTests(unittest.TestCase):
    def test_status_keys_required_by_driver_are_emitted_by_firmware(self):
        firmware = FIRMWARE.read_text(encoding="utf-8")
        driver = DRIVER.read_text(encoding="utf-8")

        emitted = set(re.findall(r'out\.print\(F\(" ([a-z0-9_]+)=', firmware))
        emitted.add("armed")  # first field is emitted as "OK armed=" rather than " armed="

        required = set(
            re.findall(
                r'(?:_as_bool|_as_int|_need)\(values, "([a-z0-9_]+)"\)',
                driver,
            )
        )

        self.assertTrue(required, "driver status parser keys were not detected")
        self.assertEqual(required, emitted)

    def test_protocol_identity_matches_driver_requirement(self):
        firmware = FIRMWARE.read_text(encoding="utf-8")
        driver = DRIVER.read_text(encoding="utf-8")
        identity = "NutUPS HID Simulator v2"
        self.assertIn(identity, firmware)
        self.assertIn(identity, driver)

    def test_hardened_tcp_server_uses_accept(self):
        firmware = FIRMWARE.read_text(encoding="utf-8")
        self.assertIn("controlServer.accept()", firmware)
        self.assertNotIn("controlServer.available()", firmware)


if __name__ == "__main__":
    unittest.main()
