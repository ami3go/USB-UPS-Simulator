#include "HIDPowerDeviceNUT.h"

#if defined(_USING_HID)

// Optional descriptor fragment for fields that the NUT arduino-hid subdriver
// already maps but the original HIDPowerDevice example did not expose.
//
// Paths produced for NUT:
//   UPS.PowerSummary.DelayBeforeStartup
//   UPS.PowerSummary.PercentLoad
//   UPS.PowerConverter.Input.[1].Voltage
//   UPS.PowerConverter.Output.Voltage
static const uint8_t _nutHidReportDescriptor[] PROGMEM = {
    0x05, 0x84, // USAGE_PAGE (Power Device)
    0x09, 0x04, // USAGE (UPS)
    0xA1, 0x01, // COLLECTION (Application)

    // PowerSummary -----------------------------------------------------------
    0x09, 0x24, //   USAGE (PowerSummary)
    0xA1, 0x02, //   COLLECTION (Logical)

    0x75, 0x10, //     REPORT_SIZE (16)
    0x95, 0x01, //     REPORT_COUNT (1)
    0x16, 0x00, 0x80, // LOGICAL_MINIMUM (-32768)
    0x27, 0xFF, 0x7F, 0x00, 0x00, // LOGICAL_MAXIMUM (32767)
    0x85, HID_PD_DELAYBE4STARTUP,
    0x09, 0x56, //     USAGE (DelayBeforeStartup)
    0xB1, 0xA2, //     FEATURE (Data, Variable, Absolute, Volatile)

    0x75, 0x08, //     REPORT_SIZE (8)
    0x15, 0x00, //     LOGICAL_MINIMUM (0)
    0x25, 0x64, //     LOGICAL_MAXIMUM (100)
    0x85, HID_PD_PERCENTLOAD,
    0x09, 0x35, //     USAGE (PercentLoad)
    0x81, 0xA2, //     INPUT (Data, Variable, Absolute, Volatile)
    0x09, 0x35, //     USAGE (PercentLoad)
    0xB1, 0xA2, //     FEATURE (Data, Variable, Absolute, Volatile)

    0xC0,       //   END_COLLECTION (PowerSummary)

    // PowerConverter ---------------------------------------------------------
    0x05, 0x84, //   USAGE_PAGE (Power Device)
    0x09, 0x16, //   USAGE (PowerConverter)
    0xA1, 0x02, //   COLLECTION (Logical)

    // NUT's HID parser treats collection types >= 0x80 as an indexed
    // collection. 0x81 therefore produces the required Input.[1] path.
    0x09, 0x1A, //     USAGE (Input)
    0xA1, 0x81, //     COLLECTION (Vendor-defined/index 1)
    0x75, 0x10, //       REPORT_SIZE (16)
    0x95, 0x01, //       REPORT_COUNT (1)
    0x15, 0x00, //       LOGICAL_MINIMUM (0)
    0x27, 0xFF, 0xFF, 0x00, 0x00, // LOGICAL_MAXIMUM (65535)
    0x67, 0x21, 0xD1, 0xF0, 0x00, // UNIT (centivolts, same encoding as battery voltage)
    0x55, 0x05, //       UNIT_EXPONENT (5)
    0x85, HID_PD_INPUTVOLTAGE,
    0x09, 0x30, //       USAGE (Voltage)
    0x81, 0xA2, //       INPUT (Data, Variable, Absolute, Volatile)
    0x09, 0x30, //       USAGE (Voltage)
    0xB1, 0xA2, //       FEATURE (Data, Variable, Absolute, Volatile)
    0xC0,       //     END_COLLECTION (Input.[1])

    0x09, 0x1C, //     USAGE (Output)
    0xA1, 0x02, //     COLLECTION (Logical)
    0x75, 0x10, //       REPORT_SIZE (16)
    0x95, 0x01, //       REPORT_COUNT (1)
    0x15, 0x00, //       LOGICAL_MINIMUM (0)
    0x27, 0xFF, 0xFF, 0x00, 0x00, // LOGICAL_MAXIMUM (65535)
    0x67, 0x21, 0xD1, 0xF0, 0x00, // UNIT (centivolts)
    0x55, 0x05, //       UNIT_EXPONENT (5)
    0x85, HID_PD_OUTPUTVOLTAGE,
    0x09, 0x30, //       USAGE (Voltage)
    0x81, 0xA2, //       INPUT (Data, Variable, Absolute, Volatile)
    0x09, 0x30, //       USAGE (Voltage)
    0xB1, 0xA2, //       FEATURE (Data, Variable, Absolute, Volatile)
    0xC0,       //     END_COLLECTION (Output)

    0xC0,       //   END_COLLECTION (PowerConverter)
    0xC0        // END_COLLECTION (UPS)
};

HIDPowerDeviceNUT_::HIDPowerDeviceNUT_() {
    static HIDSubDescriptor node(_nutHidReportDescriptor, sizeof(_nutHidReportDescriptor));
    HID().AppendDescriptor(&node);
}

#endif
