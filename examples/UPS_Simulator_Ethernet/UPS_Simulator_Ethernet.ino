#include <HIDPowerDevice.h>
#include <HIDPowerDeviceNUT.h>
#include <SPI.h>
#include <Ethernet.h>
#include <string.h>
#include <util/atomic.h>

#define CONTROL_PORT 5000
#define UART_BAUD 115200
#define REPORT_INTERVAL_MS 5000UL
#define HEARTBEAT_INTERVAL_MS 1000UL
#define SD_CS_PIN 4
#define DHCP_TIMEOUT_MS 10000UL
#define DHCP_RESPONSE_TIMEOUT_MS 2000UL
#define DHCP_MAINTAIN_INTERVAL_MS 1000UL
#define DHCP_RETRY_INTERVAL_MS 60000UL
#define ARM_DEFAULT_LEASE_SEC 120UL
#define ARM_MAX_LEASE_SEC 3600UL

// DelayBeforeStartup, PercentLoad and input/output voltage are inserted into
// the single UPS application collection created by HIDPowerDevice.
HIDPOWERDEVICE_ENABLE_NUT_EXTENSION()

byte macAddress[] = { 0x02, 0x55, 0x50, 0x53, 0x00, 0x01 };
IPAddress fallbackIp(169, 254, 42, 42);
IPAddress fallbackDns(0, 0, 0, 0);
IPAddress fallbackGateway(0, 0, 0, 0);
IPAddress fallbackSubnet(255, 255, 0, 0);

EthernetServer controlServer(CONTROL_PORT);
EthernetClient controlClient;

const char STRING_DEVICECHEMISTRY[] PROGMEM = "PbAc";
const char STRING_OEMVENDOR[] PROGMEM = "NutUPS-Simulator";
const char STRING_SERIAL[] PROGMEM = "NUTSIM01";

const byte bDeviceChemistry = IDEVICECHEMISTRY;
const byte bOEMVendor = IOEMVENDOR;

PresentStatus iPresentStatus = {}, iPreviousStatus = {};

byte bRechargable = 1;
byte bCapacityMode = 2;

const uint16_t iConfigVoltage = 1380;
uint16_t iVoltage = 1300;
uint16_t iRunTimeToEmpty = 7200;
uint16_t iPrevRunTimeToEmpty = 0;
uint16_t iAvgTimeToFull = 7200;
uint16_t iAvgTimeToEmpty = 7200;
uint16_t iRemainTimeLimit = 600;
int16_t iDelayBe4Startup = -1;
int16_t iDelayBe4Reboot = -1;
int16_t iDelayBe4ShutDown = -1;
uint16_t iManufacturerDate = 0;
byte iAudibleAlarmCtrl = 2;

const byte iDesignCapacity = 100;
byte iWarnCapacityLimit = 10;
byte iRemnCapacityLimit = 5;
const byte bCapacityGranularity1 = 1;
const byte bCapacityGranularity2 = 1;
byte iFullChargeCapacity = 100;
byte iRemaining = 100;
byte iPrevRemaining = 0;

byte iPercentLoad = 25;
uint16_t iInputVoltage = 23000;
uint16_t iOutputVoltage = 23000;

enum OverrideMode : int8_t {
  OVERRIDE_AUTO = -1,
  OVERRIDE_OFF = 0,
  OVERRIDE_ON = 1
};

struct SimulatorState {
  bool armed;
  bool acPresent;
  bool overload;
  bool needReplacement;
  bool communicationLost;
  bool shutdownRequested;
  bool runtimeAuto;
  OverrideMode charging;
  OverrideMode lowBattery;
};

SimulatorState sim;

unsigned long lastReportMs = 0;
unsigned long lastHeartbeatMs = 0;
bool heartbeatState = false;
bool dhcpLeased = false;
unsigned long nextDhcpMaintainMs = 0;
unsigned long armLeaseMs = 0;
unsigned long lastCommandMs = 0;

char netLine[96];
size_t netLineLength = 0;
char uartLine[96];
size_t uartLineLength = 0;

class BufferedPrint : public Print {
public:
  explicit BufferedPrint(Print &out) : out_(out), len_(0) {}
  ~BufferedPrint() { drain(); }
  using Print::write;

  size_t write(uint8_t c) override {
    buf_[len_++] = c;
    if (len_ == sizeof(buf_)) drain();
    return 1;
  }

  void drain() {
    if (len_) out_.write(buf_, len_);
    len_ = 0;
  }

private:
  Print &out_;
  uint8_t buf_[64];
  uint8_t len_;
};

uint16_t atomicReadU16(const uint16_t &value) {
  uint16_t copy;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { copy = value; }
  return copy;
}

int16_t atomicReadI16(const int16_t &value) {
  int16_t copy;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { copy = value; }
  return copy;
}

void atomicWriteU16(uint16_t &target, uint16_t value) {
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { target = value; }
}

void atomicWriteI16(int16_t &target, int16_t value) {
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { target = value; }
}

PresentStatus atomicReadStatus() {
  PresentStatus copy;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { copy = iPresentStatus; }
  return copy;
}

void setSafeState() {
  sim.armed = false;
  sim.acPresent = true;
  sim.overload = false;
  sim.needReplacement = false;
  sim.communicationLost = false;
  sim.shutdownRequested = false;
  sim.runtimeAuto = true;
  sim.charging = OVERRIDE_AUTO;
  sim.lowBattery = OVERRIDE_AUTO;
  armLeaseMs = 0;
  lastCommandMs = 0;

  iRemaining = 100;
  atomicWriteU16(iVoltage, 1300);
  atomicWriteU16(iRunTimeToEmpty, atomicReadU16(iAvgTimeToEmpty));
  atomicWriteI16(iDelayBe4Startup, -1);
  atomicWriteI16(iDelayBe4Reboot, -1);
  atomicWriteI16(iDelayBe4ShutDown, -1);
  iPercentLoad = 25;
  atomicWriteU16(iInputVoltage, 23000);
  atomicWriteU16(iOutputVoltage, 23000);
}

bool parseOnOff(const char *token, bool &value) {
  if (!token) return false;
  if (!strcasecmp(token, "ON") || !strcmp(token, "1") || !strcasecmp(token, "TRUE")) {
    value = true;
    return true;
  }
  if (!strcasecmp(token, "OFF") || !strcmp(token, "0") || !strcasecmp(token, "FALSE")) {
    value = false;
    return true;
  }
  return false;
}

bool parseOverride(const char *token, OverrideMode &mode) {
  if (!token) return false;
  if (!strcasecmp(token, "AUTO")) {
    mode = OVERRIDE_AUTO;
    return true;
  }
  bool value = false;
  if (!parseOnOff(token, value)) return false;
  mode = value ? OVERRIDE_ON : OVERRIDE_OFF;
  return true;
}

bool parseSigned(const char *token, long minValue, long maxValue, long &value) {
  if (!token || !*token) return false;
  const bool negative = (*token == '-');
  if (negative && !*++token) return false;

  long parsed = 0;
  for (; *token; ++token) {
    if (*token < '0' || *token > '9') return false;
    parsed = parsed * 10 + (*token - '0');
    if (parsed > 99999L) return false;
  }

  if (negative) parsed = -parsed;
  if (parsed < minValue || parsed > maxValue) return false;
  value = parsed;
  return true;
}

bool parseUnsigned(const char *token, unsigned long minValue, unsigned long maxValue, unsigned long &value) {
  long parsed;
  if (!parseSigned(token, (long)minValue, (long)maxValue, parsed)) return false;
  value = (unsigned long)parsed;
  return true;
}

const __FlashStringHelper *overrideName(OverrideMode mode) {
  if (mode == OVERRIDE_ON) return F("on");
  if (mode == OVERRIDE_OFF) return F("off");
  return F("auto");
}

void updateModel() {
  const int16_t hostShutdownDelay = atomicReadI16(iDelayBe4ShutDown);
  const uint16_t remainTimeLimit = atomicReadU16(iRemainTimeLimit);

  if (sim.runtimeAuto && iFullChargeCapacity) {
    const uint16_t avgEmpty = atomicReadU16(iAvgTimeToEmpty);
    atomicWriteU16(iRunTimeToEmpty,
                   (uint16_t)((uint32_t)avgEmpty * iRemaining / iFullChargeCapacity));
  }

  const uint16_t runtime = atomicReadU16(iRunTimeToEmpty);
  const bool autoCharging = sim.acPresent && (iRemaining < iFullChargeCapacity);
  const bool charging = (sim.charging == OVERRIDE_AUTO) ? autoCharging : (sim.charging == OVERRIDE_ON);
  const bool discharging = !sim.acPresent && iRemaining > 0;
  const bool autoLowBattery = iRemaining <= iRemnCapacityLimit;
  const bool lowBattery = (sim.lowBattery == OVERRIDE_AUTO) ? autoLowBattery : (sim.lowBattery == OVERRIDE_ON);

  PresentStatus s = {};
  s.Charging = charging;
  s.Discharging = discharging;
  s.ACPresent = sim.acPresent;
  s.BatteryPresent = 1;
  s.BelowRemainingCapacityLimit = lowBattery;
  s.RemainingTimeLimitExpired = discharging && (runtime <= remainTimeLimit);
  s.NeedReplacement = sim.needReplacement;
  s.VoltageNotRegulated = 0;
  s.FullyCharged = iRemaining >= iFullChargeCapacity;
  s.FullyDischarged = iRemaining == 0;
  s.ShutdownRequested = sim.armed && (sim.shutdownRequested || (hostShutdownDelay > 0));
  s.ShutdownImminent = s.ShutdownRequested || s.RemainingTimeLimitExpired;
  s.CommunicationLost = sim.communicationLost;
  s.Overload = sim.overload;

  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { iPresentStatus = s; }
}

bool usbSend(uint8_t id, const void *data, uint8_t len) {
  return USB_SendSpace(HID_TX) >= (uint8_t)(len + 1) &&
         PowerDevice.sendReport(id, data, len) >= 0;
}

void sendUsbReports(bool force) {
  const unsigned long now = millis();
  const PresentStatus status = atomicReadStatus();
  const uint16_t runtime = atomicReadU16(iRunTimeToEmpty);
  const uint16_t batteryVoltage = atomicReadU16(iVoltage);
  const uint16_t inputVoltage = atomicReadU16(iInputVoltage);
  const uint16_t outputVoltage = atomicReadU16(iOutputVoltage);

  const bool changed =
      (status != iPreviousStatus) ||
      (iRemaining != iPrevRemaining) ||
      (runtime != iPrevRunTimeToEmpty);

  if (!force && !changed && (now - lastReportMs < REPORT_INTERVAL_MS)) return;

  bool sent = usbSend(HID_PD_PRESENTSTATUS, &status, sizeof(status));
  if (sent) sent = usbSend(HID_PD_REMAININGCAPACITY, &iRemaining, sizeof(iRemaining));
  if (sent) sent = usbSend(HID_PD_RUNTIMETOEMPTY, &runtime, sizeof(runtime));
  if (sent) sent = usbSend(HID_PD_VOLTAGE, &batteryVoltage, sizeof(batteryVoltage));
  if (sent) sent = usbSend(HID_PD_PERCENTLOAD, &iPercentLoad, sizeof(iPercentLoad));
  if (sent) sent = usbSend(HID_PD_INPUTVOLTAGE, &inputVoltage, sizeof(inputVoltage));
  if (sent) sent = usbSend(HID_PD_OUTPUTVOLTAGE, &outputVoltage, sizeof(outputVoltage));

  // Only acknowledge a report cycle when every report was queued. If the USB
  // endpoint was full, leave the previous snapshot untouched so the next loop
  // retries immediately instead of waiting for the periodic refresh.
  if (sent) {
    iPreviousStatus = status;
    iPrevRemaining = iRemaining;
    iPrevRunTimeToEmpty = runtime;
    lastReportMs = now;
  }
}

void printStatus(Print &out) {
  updateModel();
  const PresentStatus status = atomicReadStatus();
  const uint16_t runtime = atomicReadU16(iRunTimeToEmpty);
  const uint16_t batteryVoltage = atomicReadU16(iVoltage);
  const uint16_t inputVoltage = atomicReadU16(iInputVoltage);
  const uint16_t outputVoltage = atomicReadU16(iOutputVoltage);
  const int16_t startDelay = atomicReadI16(iDelayBe4Startup);
  const int16_t shutdownDelay = atomicReadI16(iDelayBe4ShutDown);
  const int16_t rebootDelay = atomicReadI16(iDelayBe4Reboot);

  out.print(F("OK armed=")); out.print(sim.armed ? 1 : 0);
  out.print(F(" ac=")); out.print(sim.acPresent ? 1 : 0);
  out.print(F(" battery=")); out.print(iRemaining);
  out.print(F(" runtime=")); out.print(runtime);
  out.print(F(" runtime_mode=")); out.print(sim.runtimeAuto ? F("auto") : F("manual"));
  out.print(F(" voltage_cv=")); out.print(batteryVoltage);
  out.print(F(" load=")); out.print(iPercentLoad);
  out.print(F(" input_voltage_cv=")); out.print(inputVoltage);
  out.print(F(" output_voltage_cv=")); out.print(outputVoltage);
  out.print(F(" charging_mode=")); out.print(overrideName(sim.charging));
  out.print(F(" charging_active=")); out.print(status.Charging ? 1 : 0);
  out.print(F(" lowbat_mode=")); out.print(overrideName(sim.lowBattery));
  out.print(F(" lowbat_active=")); out.print(status.BelowRemainingCapacityLimit ? 1 : 0);
  out.print(F(" overload=")); out.print(sim.overload ? 1 : 0);
  out.print(F(" replace=")); out.print(sim.needReplacement ? 1 : 0);
  out.print(F(" commlost=")); out.print(sim.communicationLost ? 1 : 0);
  out.print(F(" shutdown=")); out.print(sim.shutdownRequested ? 1 : 0);
  out.print(F(" shutdown_imminent=")); out.print(status.ShutdownImminent ? 1 : 0);
  out.print(F(" host_start_delay=")); out.print(startDelay);
  out.print(F(" host_shutdown_delay=")); out.print(shutdownDelay);
  out.print(F(" host_reboot_delay=")); out.print(rebootDelay);
  out.print(F(" ip=")); out.println(Ethernet.localIP());
}

void printIdent(Print &out) {
  out.println(F("OK NutUPS HID Simulator v2"));
}

void printHelp(Print &out) {
  out.println(F("OK commands: see docs/CONTROL_PROTOCOL.md"));
}

bool requireArmed(Print &out) {
  if (sim.armed) return true;
  out.println(F("ERR disarmed"));
  return false;
}

void applyBooleanCommand(Print &out, const char *arg, bool &target) {
  bool value = false;
  if (!parseOnOff(arg, value)) {
    out.println(F("ERR mode"));
    return;
  }
  target = value;
  updateModel();
  sendUsbReports(true);
  out.println(F("OK"));
}

void handleCommand(char *line, Print &out) {
  while (*line == ' ' || *line == '\t') ++line;
  if (!*line) return;

  char *save = NULL;
  char *command = strtok_r(line, " \t", &save);
  char *arg = strtok_r(NULL, " \t", &save);
  char *arg2 = strtok_r(NULL, " \t", &save);

  if (sim.armed) lastCommandMs = millis();

  if (!strcasecmp(command, "PING")) {
    out.println(F("OK PONG"));
    return;
  }
  if (!strcasecmp(command, "IDENT?")) {
    printIdent(out);
    return;
  }
  if (!strcasecmp(command, "HELP") || !strcmp(command, "?")) {
    printHelp(out);
    return;
  }
  if (!strcasecmp(command, "STATUS?") || !strcasecmp(command, "STATUS")) {
    printStatus(out);
    return;
  }
  if (!strcasecmp(command, "NETWORK?")) {
    out.print(F("OK ip=")); out.print(Ethernet.localIP());
    out.print(F(" gateway=")); out.print(Ethernet.gatewayIP());
    out.print(F(" subnet=")); out.print(Ethernet.subnetMask());
    out.print(F(" port=")); out.println(CONTROL_PORT);
    return;
  }

  if (!strcasecmp(command, "ARM")) {
    bool value = false;
    if (!parseOnOff(arg, value)) {
      out.println(F("ERR mode"));
      return;
    }
    if (value) {
      unsigned long leaseSec = ARM_DEFAULT_LEASE_SEC;
      if (arg2 && !parseUnsigned(arg2, 0, ARM_MAX_LEASE_SEC, leaseSec)) {
        out.println(F("ERR range"));
        return;
      }
      sim.armed = true;
      armLeaseMs = leaseSec * 1000UL;
      lastCommandMs = millis();
      out.println(F("OK armed"));
    } else {
      setSafeState();
      updateModel();
      sendUsbReports(true);
      out.println(F("OK safe"));
    }
    return;
  }

  if (!strcasecmp(command, "RESET")) {
    setSafeState();
    updateModel();
    sendUsbReports(true);
    out.println(F("OK safe"));
    return;
  }

  if (!strcasecmp(command, "REPORT")) {
    updateModel();
    sendUsbReports(true);
    out.println(F("OK"));
    return;
  }

  if (!requireArmed(out)) return;

  if (!strcasecmp(command, "AC")) {
    applyBooleanCommand(out, arg, sim.acPresent);
    return;
  }
  if (!strcasecmp(command, "OVERLOAD")) {
    applyBooleanCommand(out, arg, sim.overload);
    return;
  }
  if (!strcasecmp(command, "REPLACE")) {
    applyBooleanCommand(out, arg, sim.needReplacement);
    return;
  }
  if (!strcasecmp(command, "COMMLOST")) {
    applyBooleanCommand(out, arg, sim.communicationLost);
    return;
  }
  if (!strcasecmp(command, "SHUTDOWN")) {
    applyBooleanCommand(out, arg, sim.shutdownRequested);
    return;
  }

  if (!strcasecmp(command, "CHARGING") || !strcasecmp(command, "LOWBAT")) {
    OverrideMode value;
    if (!parseOverride(arg, value)) {
      out.println(F("ERR mode"));
      return;
    }
    if (!strcasecmp(command, "CHARGING")) sim.charging = value;
    else sim.lowBattery = value;
    updateModel();
    sendUsbReports(true);
    out.println(F("OK"));
    return;
  }

  unsigned long value = 0;
  if (!strcasecmp(command, "BATTERY")) {
    if (!parseUnsigned(arg, 0, 100, value)) { out.println(F("ERR range")); return; }
    iRemaining = (byte)value;
  } else if (!strcasecmp(command, "LOAD")) {
    if (!parseUnsigned(arg, 0, 100, value)) { out.println(F("ERR range")); return; }
    iPercentLoad = (byte)value;
  } else if (!strcasecmp(command, "VOLTAGE")) {
    if (!parseUnsigned(arg, 0, 65535UL, value)) { out.println(F("ERR range")); return; }
    atomicWriteU16(iVoltage, (uint16_t)value);
  } else if (!strcasecmp(command, "INPUTVOLTAGE")) {
    if (!parseUnsigned(arg, 0, 65535UL, value)) { out.println(F("ERR range")); return; }
    atomicWriteU16(iInputVoltage, (uint16_t)value);
  } else if (!strcasecmp(command, "OUTPUTVOLTAGE")) {
    if (!parseUnsigned(arg, 0, 65535UL, value)) { out.println(F("ERR range")); return; }
    atomicWriteU16(iOutputVoltage, (uint16_t)value);
  } else if (!strcasecmp(command, "RUNTIME")) {
    if (arg && !strcasecmp(arg, "AUTO")) {
      sim.runtimeAuto = true;
    } else {
      if (!parseUnsigned(arg, 0, 65535UL, value)) { out.println(F("ERR range")); return; }
      sim.runtimeAuto = false;
      atomicWriteU16(iRunTimeToEmpty, (uint16_t)value);
    }
  } else if (!strcasecmp(command, "STARTDELAY")) {
    long signedValue = 0;
    if (!parseSigned(arg, -1, 32767L, signedValue)) { out.println(F("ERR range")); return; }
    atomicWriteI16(iDelayBe4Startup, (int16_t)signedValue);
  } else {
    out.println(F("ERR command"));
    return;
  }

  updateModel();
  sendUsbReports(true);
  out.println(F("OK"));
}

void pollStream(Stream &input, Print &output, char *buffer, size_t &length, size_t capacity) {
  while (input.available() > 0) {
    const char c = (char)input.read();
    if (c == '\r') continue;
    if (c == '\n') {
      buffer[length] = '\0';
      BufferedPrint reply(output);
      handleCommand(buffer, reply);
      length = 0;
      continue;
    }
    if (length + 1 < capacity) {
      buffer[length++] = c;
    } else {
      length = 0;
      output.println(F("ERR line"));
    }
  }
}

void initEthernet() {
  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(SD_CS_PIN, HIGH);
  dhcpLeased = Ethernet.begin(macAddress, DHCP_TIMEOUT_MS, DHCP_RESPONSE_TIMEOUT_MS) != 0;
  if (!dhcpLeased) {
    Ethernet.begin(macAddress, fallbackIp, fallbackDns, fallbackGateway, fallbackSubnet);
  }
  nextDhcpMaintainMs = millis() + DHCP_MAINTAIN_INTERVAL_MS;
  controlServer.begin();
}

const uint8_t kReadOnlyFeatures[] PROGMEM = {
  HID_PD_PRESENTSTATUS, HID_PD_RUNTIMETOEMPTY, HID_PD_AVERAGETIME2FULL, HID_PD_AVERAGETIME2EMPTY,
  HID_PD_RECHARGEABLE, HID_PD_CAPACITYMODE, HID_PD_CONFIGVOLTAGE, HID_PD_VOLTAGE,
  HID_PD_PERCENTLOAD, HID_PD_INPUTVOLTAGE, HID_PD_OUTPUTVOLTAGE, HID_PD_DESIGNCAPACITY,
  HID_PD_FULLCHRGECAPACITY, HID_PD_REMAININGCAPACITY, HID_PD_CPCTYGRANULARITY1,
  HID_PD_CPCTYGRANULARITY2, HID_PD_MANUFACTUREDATE
};

void setupHid() {
  PowerDevice.begin();
  PowerDevice.setSerial(STRING_SERIAL);
  PowerDevice.setOutput(Serial);

  PowerDevice.setFeature(HID_PD_PRESENTSTATUS, &iPresentStatus, sizeof(iPresentStatus));
  PowerDevice.setFeature(HID_PD_RUNTIMETOEMPTY, &iRunTimeToEmpty, sizeof(iRunTimeToEmpty));
  PowerDevice.setFeature(HID_PD_AVERAGETIME2FULL, &iAvgTimeToFull, sizeof(iAvgTimeToFull));
  PowerDevice.setFeature(HID_PD_AVERAGETIME2EMPTY, &iAvgTimeToEmpty, sizeof(iAvgTimeToEmpty));
  PowerDevice.setFeature(HID_PD_REMAINTIMELIMIT, &iRemainTimeLimit, sizeof(iRemainTimeLimit));
  PowerDevice.setFeature(HID_PD_DELAYBE4STARTUP, &iDelayBe4Startup, sizeof(iDelayBe4Startup));
  PowerDevice.setFeature(HID_PD_DELAYBE4REBOOT, &iDelayBe4Reboot, sizeof(iDelayBe4Reboot));
  PowerDevice.setFeature(HID_PD_DELAYBE4SHUTDOWN, &iDelayBe4ShutDown, sizeof(iDelayBe4ShutDown));
  PowerDevice.setFeature(HID_PD_RECHARGEABLE, &bRechargable, sizeof(bRechargable));
  PowerDevice.setFeature(HID_PD_CAPACITYMODE, &bCapacityMode, sizeof(bCapacityMode));
  PowerDevice.setFeature(HID_PD_CONFIGVOLTAGE, &iConfigVoltage, sizeof(iConfigVoltage));
  PowerDevice.setFeature(HID_PD_VOLTAGE, &iVoltage, sizeof(iVoltage));
  PowerDevice.setFeature(HID_PD_PERCENTLOAD, &iPercentLoad, sizeof(iPercentLoad));
  PowerDevice.setFeature(HID_PD_INPUTVOLTAGE, &iInputVoltage, sizeof(iInputVoltage));
  PowerDevice.setFeature(HID_PD_OUTPUTVOLTAGE, &iOutputVoltage, sizeof(iOutputVoltage));
  PowerDevice.setStringFeature(HID_PD_IDEVICECHEMISTRY, &bDeviceChemistry, STRING_DEVICECHEMISTRY);
  PowerDevice.setStringFeature(HID_PD_IOEMINFORMATION, &bOEMVendor, STRING_OEMVENDOR);
  PowerDevice.setFeature(HID_PD_AUDIBLEALARMCTRL, &iAudibleAlarmCtrl, sizeof(iAudibleAlarmCtrl));
  PowerDevice.setFeature(HID_PD_DESIGNCAPACITY, &iDesignCapacity, sizeof(iDesignCapacity));
  PowerDevice.setFeature(HID_PD_FULLCHRGECAPACITY, &iFullChargeCapacity, sizeof(iFullChargeCapacity));
  PowerDevice.setFeature(HID_PD_REMAININGCAPACITY, &iRemaining, sizeof(iRemaining));
  PowerDevice.setFeature(HID_PD_WARNCAPACITYLIMIT, &iWarnCapacityLimit, sizeof(iWarnCapacityLimit));
  PowerDevice.setFeature(HID_PD_REMNCAPACITYLIMIT, &iRemnCapacityLimit, sizeof(iRemnCapacityLimit));
  PowerDevice.setFeature(HID_PD_CPCTYGRANULARITY1, &bCapacityGranularity1, sizeof(bCapacityGranularity1));
  PowerDevice.setFeature(HID_PD_CPCTYGRANULARITY2, &bCapacityGranularity2, sizeof(bCapacityGranularity2));

  iManufacturerDate = (2026 - 1980) * 512 + 9 * 32 + 19;
  PowerDevice.setFeature(HID_PD_MANUFACTUREDATE, &iManufacturerDate, sizeof(iManufacturerDate));

  for (uint8_t i = 0; i < sizeof(kReadOnlyFeatures); i++) {
    HID().LockFeature(pgm_read_byte(&kReadOnlyFeatures[i]), true);
  }
}

void setup() {
  Serial.begin(UART_BAUD);
  Serial1.begin(UART_BAUD);
  pinMode(LED_BUILTIN, OUTPUT);
  setSafeState();
  updateModel();
  setupHid();
  sendUsbReports(true);
  initEthernet();
  Serial1.println(F("NutUPS ready"));
}

void loop() {
  const unsigned long now = millis();

  if (sim.armed && armLeaseMs && (unsigned long)(now - lastCommandMs) >= armLeaseMs) {
    setSafeState();
    updateModel();
    sendUsbReports(true);
  }

  // DHCP maintenance can block during a failed renew. Never risk that while a
  // fault-injection session is armed; postpone it until the simulator is safe.
  if (!sim.armed && dhcpLeased && (long)(now - nextDhcpMaintainMs) >= 0) {
    const int rc = Ethernet.maintain();
    nextDhcpMaintainMs = millis() +
        ((rc == 1 || rc == 3) ? DHCP_RETRY_INTERVAL_MS : DHCP_MAINTAIN_INTERVAL_MS);
  }

  EthernetClient candidate = controlServer.accept();
  if (candidate) {
    if (controlClient) controlClient.stop();
    controlClient = candidate;
    netLineLength = 0;
    BufferedPrint greeting(controlClient);
    printIdent(greeting);
    greeting.println(sim.armed ? F("OK ARMED") : F("OK DISARMED"));
  } else if (controlClient && !controlClient.connected()) {
    controlClient.stop();
  }

  if (controlClient && controlClient.connected()) {
    pollStream(controlClient, controlClient, netLine, netLineLength, sizeof(netLine));
  }
  pollStream(Serial1, Serial1, uartLine, uartLineLength, sizeof(uartLine));

  updateModel();
  sendUsbReports(false);

  if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs = now;
    heartbeatState = !heartbeatState;
    digitalWrite(LED_BUILTIN, heartbeatState ? HIGH : LOW);
  }
}
