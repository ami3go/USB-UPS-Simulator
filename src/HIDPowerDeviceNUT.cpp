#include "HIDPowerDeviceNUT.h"
#include "HIDPowerDevice.h"

#if defined(_USING_HID)

// Extra items mapped by NUT's arduino-hid subdriver. This fragment deliberately
// has no Application collection of its own: HIDPowerDevice_ inserts it before
// the END_COLLECTION of its UPS application collection.
const uint8_t hidPowerDeviceNutFragment[] PROGMEM = {
    0x05, 0x84, // USAGE_PAGE (Power Device)

    // PowerSummary -----------------------------------------------------------
    0x09, 0x24, // USAGE (PowerSummary)
    0xA1, 0x02, // COLLECTION (Logical)

    0x75, 0x10, //   REPORT_SIZE (16)
    0x95, 0x01, //   REPORT_COUNT (1)
    0x16, 0x00, 0x80, //   LOGICAL_MINIMUM (-32768)
    0x27, 0xFF, 0x7F, 0x00, 0x00, //   LOGICAL_MAXIMUM (32767)
    0x66, 0x01, 0x10, //   UNIT (Seconds)
    0x55, 0x00, //   UNIT_EXPONENT (0)
    0x85, HID_PD_DELAYBE4STARTUP,
    0x09, 0x56, //   USAGE (DelayBeforeStartup)
    0xB1, 0xA2, //   FEATURE (Data, Variable, Absolute, Volatile)

    0x75, 0x08, //   REPORT_SIZE (8)
    0x15, 0x00, //   LOGICAL_MINIMUM (0)
    0x25, 0x64, //   LOGICAL_MAXIMUM (100)
    0x65, 0x00, //   UNIT (None)
    0x85, HID_PD_PERCENTLOAD,
    0x09, 0x35, //   USAGE (PercentLoad)
    0x81, 0xA2, //   INPUT (Data, Variable, Absolute, Volatile)
    0x09, 0x35, //   USAGE (PercentLoad)
    0xB1, 0xA2, //   FEATURE (Data, Variable, Absolute, Volatile)

    0xC0,       // END_COLLECTION (PowerSummary)

    // PowerConverter ---------------------------------------------------------
    0x09, 0x16, // USAGE (PowerConverter)
    0xA1, 0x02, // COLLECTION (Logical)

    // NUT's HID parser treats collection types >= 0x80 as indexed.
    0x09, 0x1A, //   USAGE (Input)
    0xA1, 0x81, //   COLLECTION (Vendor-defined/index 1)
    0x75, 0x10, //     REPORT_SIZE (16)
    0x95, 0x01, //     REPORT_COUNT (1)
    0x15, 0x00, //     LOGICAL_MINIMUM (0)
    0x27, 0xFF, 0xFF, 0x00, 0x00, // LOGICAL_MAXIMUM (65535)
    0x67, 0x21, 0xD1, 0xF0, 0x00, // UNIT (centivolts)
    0x55, 0x05, //     UNIT_EXPONENT (5)
    0x85, HID_PD_INPUTVOLTAGE,
    0x09, 0x30, //     USAGE (Voltage)
    0x81, 0xA2, //     INPUT (Data, Variable, Absolute, Volatile)
    0x09, 0x30, //     USAGE (Voltage)
    0xB1, 0xA2, //     FEATURE (Data, Variable, Absolute, Volatile)
    0xC0,       //   END_COLLECTION (Input.[1])

    0x09, 0x1C, //   USAGE (Output)
    0xA1, 0x02, //   COLLECTION (Logical)
    // Report size/count, logical range and voltage unit carry over from Input.
    0x85, HID_PD_OUTPUTVOLTAGE,
    0x09, 0x30, //     USAGE (Voltage)
    0x81, 0xA2, //     INPUT (Data, Variable, Absolute, Volatile)
    0x09, 0x30, //     USAGE (Voltage)
    0xB1, 0xA2, //     FEATURE (Data, Variable, Absolute, Volatile)
    0xC0,       //   END_COLLECTION (Output)

    0xC0        // END_COLLECTION (PowerConverter)
};

const uint16_t hidPowerDeviceNutFragmentSize = sizeof(hidPowerDeviceNutFragment);

// Strong definition overrides the weak default in HIDPowerDevice.cpp when this
// extension object file is linked.
HIDSubDescriptor* HIDPowerDevice_extension() {
    static HIDSubDescriptor node(hidPowerDeviceNutFragment, hidPowerDeviceNutFragmentSize);
    return &node;
}

HIDPowerDeviceNUT_::HIDPowerDeviceNUT_() {
    // Intentionally empty. Constructing this compatibility object makes the
    // linker pull this object file, which provides HIDPowerDevice_extension().
}

#endif
