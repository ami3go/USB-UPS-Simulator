# Hardware self-test

`ups-sim-selftest` validates a real Arduino Leonardo + W5500 simulator connected to the same PC by USB and reachable on the same LAN.

It checks three layers:

1. **USB HID** — finds a HID Power Device on the PC and, when the report descriptor is readable, verifies the NutUPS extension report IDs `0x21..0x24`.
2. **Ethernet** — discovers `NutUPS HID Simulator v2` on TCP port `5000`.
3. **Protocol/state** — exercises every primary v2 control command and verifies the resulting state through `STATUS?`/`NETWORK?`.

The script always attempts a final `RESET` so the simulator returns to the safe online/disarmed state.

## Install

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e './python-driver[selftest]'
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.\python-driver[selftest]'
```

The `selftest` extra installs:

- `psutil` for cross-platform local-interface discovery and the NUT safety check
- `pyusb` as a non-Linux USB/HID fallback

Linux normally verifies the HID Power Device directly from `/sys/bus/hid/devices/*/report_descriptor`.

## Hardware arrangement

```text
                    same PC
          +-------------------------+
          |                         |
          | USB                     | Ethernet/LAN
          v                         v
    +------------+            +------------+
    | Leonardo   |------------| W5500      |
    | USB HID UPS| SPI/ICSP   | TCP 5000   |
    +------------+            +------------+
```

The W5500 and the PC must be on the same reachable IPv4 LAN. The script also probes the firmware fallback address `169.254.42.42`.

## Run

With automatic LAN discovery:

```bash
ups-sim-selftest
```

Typical output is intentionally simple:

```text
NutUPS hardware self-test
=========================
[PASS] USB HID Power Device - 0003:00002341:00008036 Arduino Leonardo; NUT extension report IDs present
[INFO] scanning local LAN for NutUPS TCP/5000 ...
[PASS] Ethernet simulator discovery - 192.168.1.72
[PASS] shutdown safety pre-check - no active upsmon detected
[PASS] RESET safe state
[PASS] PING
[PASS] IDENT?
...
[PASS] SHUTDOWN OFF
[PASS] final RESET
[PASS] self-test complete - simulator restored to safe RESET state
```

Exit code `0` means all required checks passed. A failed check exits non-zero.

## Skip LAN scanning

If the simulator IP is known:

```bash
ups-sim-selftest --host 192.168.1.72
```

This is also useful when `psutil` is not installed.

## Scan an additional subnet

Automatic discovery keeps large local networks bounded to the PC's local `/24` so a self-test cannot accidentally probe tens of thousands of hosts.

If the simulator is elsewhere in a larger routed LAN, specify the network explicitly:

```bash
ups-sim-selftest --network 10.20.32.0/23
```

The option may be repeated.

## What commands are tested

Read-only and protocol commands:

```text
PING
IDENT?
STATUS?
NETWORK?
HELP
?
```

Safety/control commands:

```text
ARM ON
ARM ON <lease>
ARM OFF
RESET
REPORT
```

Measurement commands:

```text
AC ON/OFF
BATTERY
RUNTIME <seconds>/AUTO
VOLTAGE
LOAD
INPUTVOLTAGE
OUTPUTVOLTAGE
STARTDELAY
```

Mode/fault commands:

```text
CHARGING AUTO/ON/OFF
LOWBAT AUTO/ON/OFF
OVERLOAD ON/OFF
REPLACE ON/OFF
COMMLOST ON/OFF
SHUTDOWN ON/OFF
```

For every state-changing command, the script reads `STATUS?` back and checks the corresponding field. It also verifies that state mutation is rejected while the simulator is disarmed.

## Important NUT shutdown safety check

The self-test briefly generates real UPS conditions including:

```text
OB
LB
ShutdownRequested / ShutdownImminent
```

If `upsmon` on the same PC is actively monitoring this simulator, those states can invoke the PC's real shutdown policy.

For that reason the script checks for a running NUT monitor and **refuses the full test by default** if it finds one.

Recommended procedure:

1. Stop/disable the test PC's `upsmon` monitoring action.
2. Leave the USB cable connected so HID enumeration can still be tested.
3. Run `ups-sim-selftest`.
4. Re-enable `upsmon` only after the self-test returns the simulator to `RESET` state.

There is an explicit override:

```bash
ups-sim-selftest --allow-live-nut
```

Use it only when the NUT shutdown action has deliberately been made harmless for the test environment.

## USB/HID behavior by platform

### Linux

The script reads the kernel HID report descriptor and looks for the Power Device UPS application signature. It also checks report IDs:

```text
0x21 DelayBeforeStartup
0x22 PercentLoad
0x23 InputVoltage
0x24 OutputVoltage
```

This is the strongest self-test mode and does not require claiming the HID interface.

### Other platforms

PyUSB is used as a best-effort fallback. If its backend can read the HID report descriptor, the same exact check is performed. If the OS USB stack does not allow descriptor access, the script can only identify an Arduino/Leonardo HID candidate and reports a warning rather than claiming exact HID Power Device verification.

## Multiple simulators

If more than one NutUPS simulator answers on the scanned LAN, automatic selection is intentionally refused:

```text
multiple simulators found: 192.168.1.71, 192.168.1.72; rerun with --host
```

Choose the required board explicitly:

```bash
ups-sim-selftest --host 192.168.1.72
```

The current firmware still uses a common default USB serial/MAC unless customized, so the script does not try to infer which of several Ethernet boards corresponds to which USB cable.

## Ethernet-only diagnostics

If USB is intentionally not connected:

```bash
ups-sim-selftest --skip-hid --host 192.168.1.72
```

This validates the Ethernet/control side only and should not be considered a complete hardware self-test.
