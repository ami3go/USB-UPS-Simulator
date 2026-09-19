# Firmware programming guide

This guide is for developers modifying the Arduino firmware or extending its NUT/HID behavior.

## Design goals

The firmware has four priorities:

1. Present a standards-based USB HID Power Device to the host under test.
2. Allow deterministic state injection over Ethernet and UART.
3. Start in a safe state and require explicit arming before dangerous state changes.
4. Stay small enough to fit the Leonardo/ATmega32U4.

The current image is already at approximately 97% flash usage, so host-side implementation is preferred for most future features.

## Source layout

```text
src/
  HIDPowerDevice.h/.cpp       original HID UPS implementation
  HIDPowerDeviceNUT.h/.cpp    optional NUT-specific HID extension
  HID/                        low-level HID support

examples/
  UPS/                        original minimal UPS example
  UPS_Simulator_Ethernet/     Leonardo + W5500 simulator firmware

python-driver/
  src/ups_simulator/          Python TCP/UART control library
  tests/                      Python unit/transport tests

linux/
  98-upower-hid.rules         Linux desktop/UDev HID-power rule

docs/
  ...                         user/developer documentation
```

## Firmware architecture

```text
                        +-----------------------+
TCP/5000 -------------->|                       |
Serial1/115200 -------->| command parser/state  |
                        |                       |
                        +-----------+-----------+
                                    |
                                updateModel()
                                    |
                  +-----------------+-----------------+
                  |                                   |
          PresentStatus                        measurements
                  |                                   |
                  +-----------------+-----------------+
                                    |
                             sendUsbReports()
                                    |
                             HID Power Device
                                    |
                                   USB
```

## Startup sequence

`setup()` performs roughly:

1. initialize USB CDC and hardware UART
2. configure heartbeat LED
3. call `setSafeState()`
4. register/set HID features
5. start Ethernet using DHCP or fallback addressing
6. calculate status
7. send initial HID reports

State is intentionally **not persisted**. A reset or unexpected power interruption returns the simulator to a disarmed safe state.

## Safe state

`setSafeState()` resets the important simulator values to:

```text
armed              false
AC present          true
battery             100 %
battery voltage     13.00 V
runtime             7200 s / AUTO model
load                25 %
input voltage       230.00 V
output voltage      230.00 V
start delay         -1
shutdown delay      -1
reboot delay        -1
charging mode       AUTO
low-battery mode    AUTO
fault flags         cleared
```

Do not weaken this behavior when adding features.

## Main loop

The loop is non-blocking and handles:

- DHCP lease maintenance via `Ethernet.maintain()`
- accepting/replacing a TCP control client
- consuming line-oriented TCP input
- consuming UART input
- recomputing the simulated model
- periodic/changed USB HID reports
- heartbeat LED

Avoid `delay()` in the main control path.

## Command parser

Commands enter `handleCommand()` from either TCP or UART.

Read-only commands are processed before the armed-state check. `ARM` and `RESET` are also available while disarmed. All simulated-state mutation occurs after `requireArmed()`.

When adding a new state-changing command:

1. define the backing state variable
2. choose safe reset behavior in `setSafeState()`
3. validate arguments before changing state
4. keep the command behind `requireArmed()`
5. call `updateModel()` if derived status changes
6. call `sendUsbReports(true)` if the USB host must see the change immediately
7. expose the value in `STATUS?` when useful
8. add a Python driver method/CLI command
9. add tests
10. update `CONTROL_PROTOCOL.md`

Keep firmware error messages compact (`ERR range`, `ERR mode`, etc.) because flash is constrained.

## Model logic

`updateModel()` calculates dynamic HID `PresentStatus` bits.

Important relationships include:

- AC absent + battery above zero -> discharging
- AC present + battery below full + charging AUTO -> charging
- battery <= remaining-capacity limit + LOWBAT AUTO -> low battery
- discharging + runtime <= remaining-time limit -> remaining-time-limit expired
- shutdown request or remaining-time expiry -> shutdown imminent

`RUNTIME AUTO` scales runtime from the full-runtime reference according to battery percentage.

## USB HID implementation

### Base descriptor

`HIDPowerDevice.cpp` contains the original HID Power Device descriptor and feature/report support.

The simulator relies on features such as:

- battery chemistry
- nominal/actual battery voltage
- charge and capacity limits
- runtime
- delay-before-shutdown/reboot
- `PresentStatus`

### NUT extension descriptor

`HIDPowerDeviceNUT.cpp` adds fields that upstream NUT's `arduino-hid` subdriver maps but that the original library did not expose:

```text
UPS.PowerSummary.DelayBeforeStartup
UPS.PowerSummary.PercentLoad
UPS.PowerConverter.Input.[1].Voltage
UPS.PowerConverter.Output.Voltage
```

These produce:

```text
ups.delay.start / ups.timer.start
ups.load
input.voltage
output.voltage
```

The extension is instantiated only by the Ethernet simulator:

```cpp
HIDPowerDeviceNUT_ NutHidExtension;
```

This keeps the original `examples/UPS` behavior unchanged.

## HID report IDs

The base implementation currently uses IDs through 32. The NUT extension reserves:

```text
0x21  DelayBeforeStartup
0x22  PercentLoad
0x23  InputVoltage
0x24  OutputVoltage
```

New report IDs must be unique across all appended descriptors.

## Why `Input.[1]` is special

NUT's Arduino HID mapping expects:

```text
UPS.PowerConverter.Input.[1].Voltage
```

The NUT descriptor therefore declares the Input collection using collection value `0x81`. NUT's HID parser treats collection types >= `0x80` as indexed collections, yielding the required `[1]` path.

Changing this collection to an ordinary logical collection can make the firmware compile and enumerate while silently causing `input.voltage` to disappear from NUT.

## HID units

Battery/input/output voltage reports use the existing centivolt-style HID unit encoding. The simulator control protocol therefore stores voltage as integer centivolts:

```text
13.00 V  -> 1300
230.00 V -> 23000
```

The Python API hides this implementation detail from normal callers.

## Host-writable HID features

NUT can write some HID feature values, particularly delay fields. The USB HID feature storage is therefore part of the simulator's state.

Be careful when deciding whether a host-written value should trigger simulated shutdown behavior. The existing code intentionally gates shutdown-request contribution behind the simulator's armed state.

## Networking

The firmware uses Arduino Ethernet/W5500:

```text
TCP port: 5000
DHCP first
fallback: 169.254.42.42/16
```

The current implementation supports one active TCP control client. Do not add HTTP/TLS/web UI to the Leonardo; implement those on a Linux/Cockpit/Python host.

## UART

`Serial1` uses the same protocol at 115200 baud. USB `Serial` is not the primary control path and should not be confused with the hardware UART.

## Memory budget

Reference CI result:

```text
Original UPS:
  flash  9818 / 28672 (34%)
  RAM     302 / 2560  (11%)

Ethernet/NUT simulator:
  flash 28070 / 28672 (97%)
  RAM    1296 / 2560  (50%)
```

Only about 602 bytes of application flash remain with the reference toolchain.

### Feature placement rule

Implement in **firmware** only when the feature must directly affect USB HID enumeration/reporting or the minimal control transport.

Implement in **Python/Cockpit** when the feature is:

- scenario automation
- timed battery drain/charge models
- UI
- configuration storage
- authentication/access control
- logging
- retries/reconnect policies
- NUT assertions
- shutdown orchestration
- test reports

## Building locally

See [FLASHING.md](FLASHING.md). The CI-equivalent build is:

```bash
arduino-cli core install arduino:avr
arduino-cli lib install Ethernet
arduino-cli compile --fqbn arduino:avr:leonardo \
  ~/Arduino/libraries/HIDPowerDevice/examples/UPS
arduino-cli compile --fqbn arduino:avr:leonardo \
  ~/Arduino/libraries/HIDPowerDevice/examples/UPS_Simulator_Ethernet
```

## Python-side development

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ./python-driver
python -m unittest discover -s python-driver/tests -v
```

Windows PowerShell activation:

```powershell
.\.venv\Scripts\Activate.ps1
```

The CI matrix currently checks Python 3.9 and 3.13.

## Development checklist

Before merging firmware changes:

- original `UPS` example still compiles
- Ethernet simulator still fits Leonardo flash/RAM
- safe state unchanged unless deliberately documented
- dangerous commands still require arming
- no blocking loop behavior added
- HID report IDs remain unique
- NUT paths match upstream mapping exactly
- Python API and CLI are updated for protocol changes
- Python tests pass
- documentation matches command names and units

## Recommended future architecture

Because AVR flash is effectively exhausted, future Nut-ups integration should use:

```text
Cockpit UI / scenario engine
          |
      Python driver
          |
      TCP port 5000
          |
Leonardo + W5500
          |
      USB HID UPS
          |
          NUT
```

If substantially richer firmware becomes necessary, move to a native-USB MCU with materially more flash/RAM rather than continuing to squeeze features into ATmega32U4.
