/*
  Copyright (c) 2015, Arduino LLC
  Original code (pre-library): Copyright (c) 2011, Peter Barrett
  Modified code: Copyright (c) 2020, Aleksandr Bratchik

  Permission to use, copy, modify, and/or distribute this software for
  any purpose with or without fee is hereby granted, provided that the
  above copyright notice and this permission notice appear in all copies.

  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL
  WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED
  WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR
  BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES
  OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS,
  WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
  ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS
  SOFTWARE.
 */

#ifndef HID_h
#define HID_h

#include <stdint.h>
#include <Arduino.h>
#include <HardwareSerial.h>
#include <PluggableUSB.h>

#if defined(USBCON)

#define _USING_HID

#define HID_GET_REPORT        0x01
#define HID_GET_IDLE          0x02
#define HID_GET_PROTOCOL      0x03
#define HID_SET_REPORT        0x09
#define HID_SET_IDLE          0x0A
#define HID_SET_PROTOCOL      0x0B

#define HID_HID_DESCRIPTOR_TYPE         0x21
#define HID_REPORT_DESCRIPTOR_TYPE      0x22
#define HID_PHYSICAL_DESCRIPTOR_TYPE    0x23

#define HID_SUBCLASS_NONE 0
#define HID_SUBCLASS_BOOT_INTERFACE 1

#define HID_PROTOCOL_NONE 0
#define HID_PROTOCOL_KEYBOARD 1
#define HID_PROTOCOL_MOUSE 2

#define HID_BOOT_PROTOCOL 0
#define HID_REPORT_PROTOCOL 1

#define HID_REPORT_TYPE_INPUT   1
#define HID_REPORT_TYPE_OUTPUT  2
#define HID_REPORT_TYPE_FEATURE 3

#define HID_INTERFACE (CDC_ACM_INTERFACE + CDC_INTERFACE_COUNT)
#define HID_FIRST_ENDPOINT (CDC_FIRST_ENDPOINT + CDC_ENPOINT_COUNT)
#define HID_ENDPOINT_INT (HID_FIRST_ENDPOINT)
#define HID_ENDPOINT_OUT (HID_FIRST_ENDPOINT+1)

#define HID_TX HID_ENDPOINT_INT
#define HID_RX HID_ENDPOINT_OUT

typedef struct
{
  uint8_t len;
  uint8_t dtype;
  uint8_t addr;
  uint8_t versionL;
  uint8_t versionH;
  uint8_t country;
  uint8_t desctype;
  uint8_t descLenL;
  uint8_t descLenH;
} HIDDescDescriptor;

typedef struct
{
  InterfaceDescriptor hid;
  HIDDescDescriptor desc;
  EndpointDescriptor in;
  EndpointDescriptor out;
} HIDDescriptor;

class HIDReport {
public:
    HIDReport *next = NULL;
    HIDReport(uint16_t i, const void *d, uint16_t l) : id(i), data(d), length(l), lock(false) {}

    uint16_t id;
    const void* data;
    uint16_t length;
    bool lock;
};

class HIDSubDescriptor {
public:
  HIDSubDescriptor *next = NULL;
  HIDSubDescriptor(const void *d, uint16_t l) : data(d), length(l) { }

  const void* data;
  const uint16_t length;
};

class HID_ : public PluggableUSBModule
{
public:
    HID_(void);
    int begin(void);
    int SendReport(uint16_t id, const void* data, int len);
    int SetFeature(uint16_t id, const void* data, int len);
    bool LockFeature(uint16_t id, bool lock);

    void AppendDescriptor(HIDSubDescriptor* node);

    void setOutput(Serial_& out) {
        dbg = &out;
    }

    void setSerial(const char* s) {
        serial = s;
    }

    HIDReport* GetFeature(uint16_t id);

protected:
    int getInterface(uint8_t* interfaceCount) override;
    int getDescriptor(USBSetup& setup) override;
    bool setup(USBSetup& setup) override;
    uint8_t getShortName(char* name) override;

private:
    uint8_t epType[2];

    HIDSubDescriptor* rootNode;
    uint16_t descriptorSize;

    uint8_t protocol;
    uint8_t idle;

    HIDReport* rootReport;
    uint16_t reportCount;

    Serial_ *dbg;

    const char *serial;
};

HID_& HID();

#define D_HIDREPORT(length) { 9, 0x21, 0x01, 0x01, 0x21, 1, 0x22, lowByte(length), highByte(length) }

#endif // USBCON

#endif // HID_h
