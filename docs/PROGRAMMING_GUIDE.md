# Firmware programming guide

This guide is for developers modifying the Arduino firmware or extending its NUT/HID behavior.

## Design priorities

1. Present one standards-based USB HID Power Device / UPS to the host under test.
2. Allow deterministic fault injection over Ethernet and UART.
3. Boot into a valid safe HID state and require explicit arming for mutation.
4. Fail safe if the controller disappears while armed.
5. Keep the main loop responsive; avoid blocking USB/network operations during a test.
6. Stay inside the Leonardo/ATmega32U4 flash/RAM budget.

## Source layout

```text
src/
  HIDPowerDevice.h/.cpp       base HID UPS implementation
  HIDPowerDeviceNUT.h/.cpp    optional NUT-specific HID fragment
  HID/                        low-level HID support

examples/
  UPS/                        original minimal UPS example
  UPS_Simulator_Ethernet/     Leonardo + W5500 simulator firmware

python-driver/
  src/ups_simulator/          Python TCP/UART driver
  tests/                      protocol/transport tests
```

## Startup sequence

The simulator `setup()` deliberately establishes a valid HID model before potentially slow Ethernet work:

1. start USB CDC and `Serial1`
2. configure heartbeat LED
3. `setSafeState()`
4. `updateModel()` so `PresentStatus` is valid
5. register HID Feature storage
6. attempt initial interrupt report
7. initialize Ethernet/DHCP/fallback networking

This prevents a failed DHCP attempt from leaving the host with a zero-initialized `PresentStatus` that can look like on-battery/no-battery.

State is not persisted across MCU reset. Reboot always returns to the safe state.

## Main loop

The loop handles:

- arming-lease expiry
- bounded DHCP maintenance when disarmed
- accepting/replacing the TCP controller
- TCP/UART command parsing
- model recomputation
- non-blocking USB interrupt-report attempts
- heartbeat LED

Do not add `delay()` or long blocking work to the armed path.

### DHCP rule

A failed initial DHCP request falls back to `169.254.42.42/16`. `Ethernet.maintain()` is called only if a lease was actually obtained. Maintenance is postponed while the simulator is armed because a failed renew/rebind can block inside the Arduino Ethernet DHCP implementation.

## Arming lease

`ARM ON` defaults to a 120-second firmware lease. `ARM ON n` accepts `0..3600` seconds, with `0` deliberately disabling expiry. Every received command refreshes the timer while armed.

If a non-zero lease expires:

```text
setSafeState()
updateModel()
sendUsbReports(true)
```

This is a firmware fail-safe and must not be replaced by Python-only cleanup.

## Command parser rules

Read-only commands and `REPORT` are available while disarmed. State-changing commands remain after `requireArmed()`.

When adding a state command:

1. define safe reset behavior
2. validate before mutation
3. keep dangerous mutation behind the armed guard
4. use atomic access if the value is shared with USB control requests
5. update derived status
6. request an immediate HID refresh if relevant
7. expose useful state in `STATUS?`
8. update Python API/CLI and tests
9. update `CONTROL_PROTOCOL.md`

The numeric parser intentionally accepts only optional `-` followed by decimal digits. It avoids linking `strtol`/`strtoul` on the flash-constrained AVR.

## USB HID architecture

### One top-level UPS collection

`HIDPowerDevice.cpp` owns descriptor order. Its base descriptor leaves the UPS Application collection open, an optional extension hook is inserted, and a final one-byte descriptor node closes the Application collection.

The weak default hook returns no extension:

```cpp
__attribute__((weak)) HIDSubDescriptor* HIDPowerDevice_extension();
```

When `HIDPowerDeviceNUT.cpp` is linked it provides the strong hook containing the NUT fragment. The compatibility object:

```cpp
HIDPowerDeviceNUT_ NutHidExtension;
```

forces that object file to link but does not append a second top-level descriptor itself. This removes cross-translation-unit constructor-order dependence and keeps Windows-facing HID topology to a single UPS Application collection.

The original `examples/UPS` does not instantiate the extension object, so the NUT fragment is not linked for that sketch.

### NUT extension paths

```text
UPS.PowerSummary.DelayBeforeStartup
UPS.PowerSummary.PercentLoad
UPS.PowerConverter.Input.[1].Voltage
UPS.PowerConverter.Output.Voltage
```

Report IDs:

```text
0x21 DelayBeforeStartup
0x22 PercentLoad
0x23 InputVoltage
0x24 OutputVoltage
```

The Input collection uses collection type `0x81` because NUT interprets values >= `0x80` as indexed collections, producing the required `Input.[1]` path.

`DelayBeforeStartup` explicitly declares seconds. Voltage fields use the centivolt HID unit encoding.

`ups.load`, `input.voltage` and `output.voltage` require NUT 2.8.5+.

## Feature read/write safety

The HID core stores pointers to Feature values. Host `SET_REPORT(Feature)` therefore writes directly into registered storage unless the feature is locked.

The hardened implementation:

- initializes `HIDReport::lock`
- rejects writes to locked Feature reports
- rejects malformed/oversized Feature requests
- uses a fixed stack receive buffer instead of heap allocation in the USB request path
- bounds USB serial-number copy length

The simulator locks measurements and identity values that it owns. Delay/alarm/limit Feature values that are intentionally host-writable remain writable.

When adding a new Feature report, explicitly decide whether it is host writable and lock it if not.

## AVR atomicity rules

ATmega32U4 is 8-bit. A 16-bit read/write can be interrupted between bytes.

Any 16-bit value that is both:

- accessed by the main loop, and
- exposed as raw Feature storage to the USB control handler

must use the small `ATOMIC_BLOCK(ATOMIC_RESTORESTATE)` helpers for loop-side reads/writes.

Current examples include runtime, voltages, delay timers and remaining-time limit.

`PresentStatus` is computed into a local complete snapshot and then published atomically. `STATUS?` likewise reads shared 16-bit values through atomic snapshots.

Never hold interrupts disabled around Ethernet, printing or other slow I/O.

## USB interrupt reports

Arduino AVR `USB_Send()` can block when the interrupt endpoint is full. The simulator therefore checks `USB_SendSpace()` before calling the HID report sender.

`PresentStatus` is attempted first because it carries OL/OB/LB-related state. A report cycle is marked delivered only if the entire batch was queued. If any report cannot be queued, the previous snapshot remains unchanged so the next loop retries immediately.

Do not change this to unconditional snapshot acknowledgement after a failed send.

## Networking

```text
TCP: 5000
DHCP startup timeout: bounded
fallback: 169.254.42.42/16
one active controller
newest TCP connection takes over
```

`EthernetServer::accept()` is required rather than `available()` because the firmware speaks first with a greeting. Using `available()` delays discovery until client data arrives and breaks reply framing.

The raw TCP protocol has no authentication. Network isolation/firewalling must protect access; Python-side authentication cannot protect a port that the Arduino accepts directly.

## Resource budget

Pinned CI toolchain:

- Arduino AVR core 1.8.8
- Ethernet 2.0.2
- warnings enabled

Current reference build:

```text
Original UPS:
  flash 10,176 / 28,672
  RAM      330 / 2,560

Ethernet/NUT simulator:
  flash 27,854 / 28,672
  RAM    1,321 / 2,560
```

CI enforces `<= 28,160` bytes for the Ethernet simulator, preserving at least 512 bytes of application flash for future reliability fixes.

### Feature placement rule

Implement in firmware only when the feature must directly participate in HID behavior, minimal transport, or safety fail-safe behavior.

Prefer Python/Cockpit for:

- scenario engines
- timed battery models
- UI
- persistence
- authentication services
- logs/reports
- retries/reconnect orchestration
- NUT assertions
- Synology/client workflow logic

## Build locally

Use the same versions as CI:

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr@1.8.8
arduino-cli lib install Ethernet@2.0.2
arduino-cli compile --warnings all --fqbn arduino:avr:leonardo \
  ~/Arduino/libraries/HIDPowerDevice/examples/UPS
arduino-cli compile --warnings all --fqbn arduino:avr:leonardo \
  ~/Arduino/libraries/HIDPowerDevice/examples/UPS_Simulator_Ethernet
```

Python tests:

```bash
python -m pip install -e ./python-driver
python -m unittest discover -s python-driver/tests -v
```

## Pre-merge checklist

- original UPS example compiles
- simulator passes the 28,160-byte CI flash budget
- repository code is warning-clean under the pinned build aside from upstream Arduino-core warnings
- safe boot state is preserved
- arming lease still returns abandoned tests to safe state
- no blocking DHCP maintenance while armed
- one top-level UPS Application collection remains
- HID report IDs remain unique
- shared 16-bit state is accessed atomically
- read-only Features reject host writes
- Python transport works with immediate and delayed greeting timing
- Python tests pass on 3.9 and 3.13
- NUT/documentation versions and command names match the firmware

## Hardware validation before release

CI cannot prove physical USB/W5500 behavior. Verify on real hardware:

- TCP greeting immediately after connect
- fallback address with no DHCP
- responsive commands during no-DHCP operation
- no transient OB/RB event on simulator reboot
- NUT 2.8.5+ extended variables
- single UPS/battery device on Windows if Windows compatibility matters
- new controller can recover from a stale/abandoned TCP session
