#pragma once

#include <Arduino.h>
#include "HID/HID.h"

// Additional report IDs used by the NUT-oriented simulator extension.
// Keep these unique relative to HIDPowerDevice.h (currently IDs 1..32).
#define HID_PD_DELAYBE4STARTUP  0x21
#define HID_PD_PERCENTLOAD      0x22
#define HID_PD_INPUTVOLTAGE     0x23
#define HID_PD_OUTPUTVOLTAGE    0x24

// Instantiate this object at global scope in a sketch to append the
// NUT-specific HID descriptor before USB enumeration.
class HIDPowerDeviceNUT_ {
public:
  HIDPowerDeviceNUT_();
};
