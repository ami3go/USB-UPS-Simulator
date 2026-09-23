# Firmware behavior simulator

The repository includes a host-side behavioral simulator for `NutUPS HID Simulator v2`.

It is intended to answer a specific question before hardware is available: **for each firmware control command, does the parser return the expected reply and move the simulated UPS into the expected state?**

## Install

```bash
python -m pip install -e ./python-driver
```

## Interactive use

```bash
ups-sim-firmware-sim
```

Example:

```text
OK NutUPS HID Simulator v2
OK DISARMED
Enter commands, 'advance <ms>' to advance millis(), or 'quit'.
> PING
OK PONG
> STATUS?
OK armed=0 ac=1 battery=100 runtime=7200 runtime_mode=auto ...
> ARM ON 120
OK armed
> AC OFF
OK
> BATTERY 4
OK
> RUNTIME 300
OK
> STATUS?
OK armed=1 ac=0 battery=4 runtime=300 runtime_mode=manual ... lowbat_active=1 ... shutdown_imminent=1 ...
> RESET
OK safe
```

`advance <ms>` advances the simulated Arduino `millis()` clock and is used to verify the arming lease:

```text
> ARM ON 2
OK armed
> AC OFF
OK
> advance 2000
OK millis=2000
> STATUS?
OK armed=0 ac=1 battery=100 ...
```

A zero lease remains armed:

```text
> ARM ON 0
OK armed
```

## One-shot commands

Commands can also be supplied as command-line arguments:

```bash
ups-sim-firmware-sim \
  'PING' \
  'ARM ON' \
  'AC OFF' \
  'BATTERY 4' \
  'RUNTIME 300' \
  'STATUS?' \
  'RESET'
```

## What is modeled

The simulator mirrors the current `.ino` behavior for:

- boot/safe state
- immediate TCP greeting (`IDENT` + armed/disarmed state)
- `PING`
- `IDENT?`
- `HELP` and `?`
- `STATUS?` and `STATUS`
- `NETWORK?`
- `ARM ON|OFF [lease]`
- `RESET`
- `REPORT`
- `AC`
- `BATTERY`
- `RUNTIME` and `RUNTIME AUTO`
- `VOLTAGE`
- `LOAD`
- `INPUTVOLTAGE`
- `OUTPUTVOLTAGE`
- `STARTDELAY`
- `CHARGING AUTO|ON|OFF`
- `LOWBAT AUTO|ON|OFF`
- `OVERLOAD`
- `REPLACE`
- `COMMLOST`
- `SHUTDOWN`
- disarmed mutation rejection
- numeric range/error handling
- case-insensitive command matching
- the firmware's current behavior of ignoring tokens beyond `command`, `arg`, and `arg2`
- automatic runtime calculation
- charging/discharging state
- low-battery state
- remaining-time expiry
- shutdown-requested/shutdown-imminent state
- arming lease expiry and lease refresh by commands
- reset/disarm recovery to safe state

## Automated verification

Run:

```bash
python -m unittest discover -s python-driver/tests -v
```

`test_firmware_sim.py` includes a command-coverage guard which reads the actual:

```text
examples/UPS_Simulator_Ethernet/UPS_Simulator_Ethernet.ino
```

and extracts all command names used by the firmware parser. The test fails if the `.ino` adds/removes a command without the behavioral simulator being updated.

The suite also connects the real `UpsSimulator` Python driver to the behavior simulator through an in-memory transport. This verifies the driver and firmware protocol together without TCP/UART hardware.

## What is not emulated

This is **not an AVR instruction-level emulator**. It does not prove:

- ATmega32U4 instruction/timing correctness
- interrupt timing/races beyond the modeled state semantics
- native USB controller behavior
- USB HID enumeration on Linux/Windows
- interrupt endpoint availability or retry timing
- physical W5500 SPI/register behavior
- DHCP timing/lease renewal
- Ethernet electrical/link behavior
- Arduino bootloader/upload behavior
- NUT's real observation of the USB HID reports

Those remain covered by compile CI and the real-hardware self-test (`ups-sim-selftest`).

## Recommended validation layers

```text
1. Firmware behavior simulator
   command parser + state machine + exact replies

2. Arduino compile CI
   real Leonardo/AVR toolchain + flash/RAM budget

3. Hardware self-test
   Leonardo USB HID + W5500 TCP + full command read-back

4. NUT integration test
   real usbhid-ups / upsc state transitions
```

A behavioral simulator passing does not replace layers 2-4, but it gives fast, deterministic coverage of the command/state logic on every commit.
