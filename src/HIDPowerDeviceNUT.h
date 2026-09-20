#pragma once

#include <Arduino.h>
#include "HID/HID.h"

#define HID_PD_DELAYBE4STARTUP  0x21
#define HID_PD_PERCENTLOAD      0x22
#define HID_PD_INPUTVOLTAGE     0x23
#define HID_PD_OUTPUTVOLTAGE    0x24

extern const uint8_t hidPowerDeviceNutFragment[] PROGMEM;
extern const uint16_t hidPowerDeviceNutFragmentSize;

// Instantiate once at global scope. The constructor itself does not append a
// descriptor; referencing it forces this extension object file to link, whose
// strong HIDPowerDevice_extension() hook inserts the fragment inside the main
// UPS application collection before USB enumeration.
class HIDPowerDeviceNUT_ {
public:
  HIDPowerDeviceNUT_();
};
