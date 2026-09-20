import ipaddress
import unittest

from ups_simulator.selftest import (
    POWER_DEVICE_SIGNATURE,
    _descriptor_has_nut_extension,
    _descriptor_is_power_device,
    _hid_report_length,
    _parse_uevent,
    _scan_network_for_interface,
)


class SelfTestHelpersTests(unittest.TestCase):
    def test_detects_hid_power_device_signature(self):
        descriptor = b"\x00\x01" + POWER_DEVICE_SIGNATURE + b"\xc0"
        self.assertTrue(_descriptor_is_power_device(descriptor))
        self.assertFalse(_descriptor_is_power_device(b"\x05\x01\x09\x06"))

    def test_detects_nut_extension_report_ids(self):
        descriptor = b"".join(bytes((0x85, report_id)) for report_id in (0x21, 0x22, 0x23, 0x24))
        self.assertTrue(_descriptor_has_nut_extension(descriptor))
        self.assertFalse(_descriptor_has_nut_extension(descriptor[:-2]))

    def test_extracts_hid_report_descriptor_length(self):
        # HID descriptor: length=9, type=0x21, HID 1.11, country=0,
        # one subordinate descriptor, type=0x22, length=0x0123.
        extra = bytes((9, 0x21, 0x11, 0x01, 0, 1, 0x22, 0x23, 0x01))
        self.assertEqual(_hid_report_length(extra), 0x0123)

    def test_parse_uevent(self):
        values = _parse_uevent("HID_ID=0003:00002341:00008036\nHID_NAME=Arduino Leonardo\n")
        self.assertEqual(values["HID_ID"], "0003:00002341:00008036")
        self.assertEqual(values["HID_NAME"], "Arduino Leonardo")

    def test_large_network_auto_scan_is_bounded_to_local_24(self):
        local = ipaddress.IPv4Address("10.20.33.17")
        network = ipaddress.IPv4Network("10.20.0.0/16")
        self.assertEqual(
            _scan_network_for_interface(local, network),
            ipaddress.IPv4Network("10.20.33.0/24"),
        )

    def test_small_network_is_preserved(self):
        local = ipaddress.IPv4Address("192.168.50.10")
        network = ipaddress.IPv4Network("192.168.50.0/24")
        self.assertEqual(_scan_network_for_interface(local, network), network)


if __name__ == "__main__":
    unittest.main()
