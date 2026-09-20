#pragma once

#include <Arduino.h>
#include "HID/HID.h"

#define HID_PD_DELAYBE4STARTUP  0x21
#define HID_PD_PERCENTLOAD      0x22
#define HID_PD_INPUTVOLTAGE     0x23
#define HID_PD_OUTPUTVOLTAGE    0x24

extern const uint8_t hidPowerDeviceNutFragment[] PROGMEM;
extern const uint16_t hidPowerDeviceNutFragmentSize;

// Use once at global scope in a sketch. HIDPowerDevice_ inserts the fragment
// before the END_COLLECTION of its UPS application collection. The hook is
// resolved at link time, avoiding cross-translation-unit initialization order.
#define HIDPOWERDEVICE_ENABLE_NUT_EXTENSION()                                \
  HIDSubDescriptor* HIDPowerDevice_extension() {                             \
    static HIDSubDescriptor node(hidPowerDeviceNutFragment,                  \
                                 hidPowerDeviceNutFragmentSize);             \
    return &node;                                                            \
  }
