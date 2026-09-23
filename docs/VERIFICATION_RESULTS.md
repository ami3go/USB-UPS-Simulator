# Firmware verification results

This file records the latest reproducible software/firmware verification for the USB UPS Simulator.

## Verification snapshot

- Date: **2026-09-23**
- Current `main` commit: `12b45b554f6e10b1ed428e46636eaffb8573d75c`
- Verified Git tree: `16af2a5f248a6735b7602b00ddac8278ef5e5571`
- Verification merge ref: `773f637672104d47a228eca3101cb354fb3bd43c`

The current `main` squash commit and the verification merge ref have the **same Git tree SHA**, so the rerun exercised the same repository content that is present in `main`.

## Behavioral verification

GitHub Actions run:

- https://github.com/ami3go/USB-UPS-Simulator/actions/runs/35846279202

Results:

```text
Python 3.9   PASS
Python 3.13  PASS

Tests run: 41
Passed:    41
Failed:     0
```

The behavioral suite verifies the firmware command/state model and Python-driver protocol compatibility, including:

- safe boot/reset state
- `PING`, `IDENT?`, `STATUS?`, `STATUS`, `NETWORK?`, `HELP`, and `?`
- `ARM ON|OFF` and lease boundaries
- arm-lease refresh and expiry
- zero/infinite arm lease
- disarmed mutation rejection
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
- `REPORT`
- numeric min/max boundaries and invalid input
- missing/bad argument error classes
- case-insensitive parser behavior
- boolean aliases (`ON/OFF`, `TRUE/FALSE`, `1/0`)
- automatic runtime calculation
- derived charging/discharging state
- derived low-battery state
- remaining-time-limit expiry
- shutdown-requested/shutdown-imminent logic
- safe recovery after lease timeout
- exact read-only protocol responses
- real Python `UpsSimulator` API against the behavioral firmware simulator
- command-list drift detection against the actual `.ino` source

The fresh rerun completed all **41 tests successfully** on both Python versions.

## Leonardo compile verification

GitHub Actions run:

- https://github.com/ami3go/USB-UPS-Simulator/actions/runs/35846279181

Pinned toolchain:

```text
Target:            arduino:avr:leonardo
Arduino AVR core:  1.8.8
Ethernet library:  2.0.2
Compiler warnings: all
```

### Original UPS example

```text
Flash: 10,176 / 28,672 bytes (35%)
RAM:      330 /  2,560 bytes (12%)
Result: PASS
```

### Ethernet + NUT simulator

```text
Flash: 27,854 / 28,672 bytes (97%)
RAM:    1,321 /  2,560 bytes (51%)

Flash free: 818 bytes
RAM free:   1,239 bytes
Result: PASS
```

The CI flash-budget limit is **28,160 bytes**. The Ethernet simulator therefore remains **306 bytes below the CI limit** and **818 bytes below the Leonardo absolute flash limit**.

Compiler warnings observed during this run come from the Arduino AVR core `new.cpp` implementation (`std::nothrow_t` unused parameters), not from the simulator source.

## Verification status

| Area | Result |
|---|---|
| Firmware command parser | PASS |
| State machine | PASS |
| Safe reset/disarm | PASS |
| Arm lease/fail-safe | PASS |
| Input/range validation | PASS |
| Derived UPS states | PASS |
| Python driver compatibility | PASS |
| Firmware/source command-list consistency | PASS |
| Leonardo AVR compilation | PASS |
| Ethernet/NUT simulator compilation | PASS |
| Flash-budget gate | PASS |
| Real hardware USB HID Power Device + NUT extension IDs | PASS |
| Real hardware Ethernet/W5500 discovery | PASS |
| Real hardware v2 protocol self-test | PASS |

## Real hardware self-test (Leonardo + W5500)

- Date: **2026-09-23**
- Board: Arduino Leonardo, `2341:8036`, USB-connected on Linux
- Toolchain: `arduino-cli 1.5.1`, Arduino AVR core `1.8.8`, Ethernet library `2.0.2` (matches the pinned CI reference exactly)
- Flash usage: `27,854 / 28,672 bytes (97%)` — identical to the CI compile figure above
- Network: W5500 shield, DHCP-leased on the local LAN, control port reachable on TCP/5000

`ups-sim-selftest` result:

```text
[PASS] USB HID Power Device - 0003:00002341:00008036 Arduino LLC Arduino Leonardo; NUT extension report IDs present
[PASS] Ethernet simulator discovery - <lan-ip>
[PASS] shutdown safety pre-check - no active upsmon detected
[PASS] RESET safe state
[PASS] PING
[PASS] IDENT?
[PASS] NETWORK?
[PASS] STATUS?
[PASS] HELP
[PASS] ?
[PASS] disarmed mutation guard
[PASS] ARM ON
[PASS] REPORT
[PASS] BATTERY
[PASS] RUNTIME manual
[PASS] RUNTIME AUTO
[PASS] VOLTAGE
[PASS] LOAD
[PASS] INPUTVOLTAGE
[PASS] OUTPUTVOLTAGE
[PASS] STARTDELAY
[PASS] CHARGING ON/OFF/AUTO
[PASS] AC OFF/ON
[PASS] LOWBAT ON/OFF/AUTO
[PASS] OVERLOAD ON/OFF
[PASS] REPLACE ON/OFF
[PASS] COMMLOST ON/OFF
[PASS] SHUTDOWN ON/OFF
[PASS] ARM OFF
[PASS] ARM ON lease
[PASS] final RESET
[PASS] self-test complete - simulator restored to safe RESET state
```

Exit code: `0`.

This exercises, on real hardware, everything the "not proven by software-only verification" list below used to call out: ATmega32U4 native USB HID enumeration, the NUT HID extension report IDs, W5500 SPI/link/DHCP behavior, and the full v2 TCP protocol surface.

**Observed transient:** the very first `ups-sim-selftest` run against a freshly DHCP-leased board failed with `timeout waiting for simulator response` immediately after Ethernet discovery succeeded. A manual probe of the same host/port right afterward got an instant, correct greeting and `PING`/`IDENT?` reply, and rerunning `ups-sim-selftest --host <ip>` a few seconds later passed cleanly with no other changes. This lines up with the documented `EthernetServer::accept()` "newest connection takes over" behavior (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)): the self-test's LAN-discovery step opens and closes one short TCP connection, and opening the persistent test connection immediately afterward can race the W5500 hardware socket's teardown/re-listen cycle. No firmware change was made for this — it is consistent with normal W5500 socket-transition timing rather than a functional defect. If it recurs, retry with `--host`, or allow a few seconds after boot before scanning.

## Not proven by software-only verification

These checks required the physical Leonardo + W5500 hardware and/or a real NUT host, and were confirmed above on real hardware on 2026-09-23:

- ATmega32U4 native USB HID enumeration
- real USB interrupt endpoint timing
- W5500 SPI/register behavior
- Ethernet electrical/link behavior
- real DHCP acquisition/renewal timing
- TCP behavior on the physical W5500
- HID report delivery to the operating system

Still outstanding, requiring a real NUT host:

- real NUT `usbhid-ups` interpretation
- `OL -> OB -> LB -> OL` observed through `upsc`
- host shutdown and recovery behavior

Use a real NUT integration test for the remaining validation layer.

## Reproduction

Behavioral tests:

```bash
python -m pip install -e ./python-driver
python -m unittest discover -s python-driver/tests -v
```

Interactive firmware behavior simulator:

```bash
ups-sim-firmware-sim
```

Real-hardware self-test:

```bash
python -m pip install -e './python-driver[selftest]'
ups-sim-selftest
```

The project intentionally keeps these validation layers separate: behavioral simulation validates parser/state semantics, compile CI validates the real AVR toolchain and resource budget, and hardware-in-the-loop testing validates USB/W5500/NUT behavior.