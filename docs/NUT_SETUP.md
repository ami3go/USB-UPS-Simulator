# NUT setup and verification

This guide connects the Arduino simulator's USB HID interface to Network UPS Tools (NUT).

The simulator firmware is designed for NUT's `usbhid-ups` driver and the upstream Arduino HID subdriver used for the `HIDPowerDevice` implementation.

## NUT version

For the complete simulator variable set, use **NUT 2.8.5 or later**. The `arduino-hid` mappings for `ups.load`, `input.voltage`, and `output.voltage` first ship in NUT 2.8.5. Earlier 2.8.x releases can still use the core charge/runtime/status fields and startup delay, but those three measurements will be absent from `upsc`.

Check the installed driver version with:

```bash
usbhid-ups -V
```

## Safety warning

A real NUT configuration may execute shutdown commands when it sees `OB`, `LB`, or shutdown-imminent states.

For first commissioning:

- use a disposable/test host
- disconnect production NUT clients
- keep the simulator disarmed until read-only communication is verified
- use the firmware arming lease instead of indefinite arming where possible
- always finish state-injection tests with `RESET`

The current firmware defaults `ARM ON` to a 120-second lease. Every command received while armed refreshes the lease. `ARM ON <seconds>` selects a different lease (`0..3600`); `0` explicitly disables lease expiry.

## 1. Install NUT

Debian/Ubuntu example:

```bash
sudo apt update
sudo apt install nut
```

Confirm tools are present:

```bash
usbhid-ups -V
upsc -V
```

Package/service names and packaged NUT versions vary by distribution.

## 2. Confirm USB enumeration

Connect the Leonardo USB port to the NUT host and run:

```bash
lsusb
```

Official/compatible Leonardo devices commonly use Arduino vendor IDs such as `2341` or `2a03`. Upstream NUT's Arduino HID subdriver includes several Leonardo/Pro Micro product IDs.

For exact descriptor debugging:

```bash
lsusb -v
```

may require root permissions.

## 3. Create a NUT UPS entry

Edit `/etc/nut/ups.conf` and add a minimal device entry:

```ini
[nutups-sim]
    driver = usbhid-ups
    port = auto
    desc = "NutUPS Arduino HID simulator"
```

Start with no VID/PID filter so the upstream `usbhid-ups` matching logic can inspect the device.

If the host has multiple HID UPS devices, add filters after checking `lsusb`, for example:

```ini
    vendorid = "2341"
```

Do not copy a product ID blindly; use the value reported by your actual board/application firmware.

## 4. NUT operating mode

For a standalone test host, `/etc/nut/nut.conf` commonly contains:

```text
MODE=standalone
```

Use the mode appropriate for your real NUT architecture if the host already participates in a NUT server/client deployment.

## 5. Start/restart NUT

Systemd unit names differ by NUT package version and distribution. Inspect available units with:

```bash
systemctl list-unit-files 'nut*'
```

Recent packages may expose a driver instance corresponding to the UPS name, along with NUT server/monitor services.

For direct driver diagnostics, NUT can be run in foreground debug mode after `ups.conf` exists:

```bash
sudo usbhid-ups -DD -a nutups-sim
```

Use this only for diagnostics; stop the foreground instance before starting the normal system service.

## 6. Verify with `upsc`

Once the driver and `upsd` are running:

```bash
upsc nutups-sim@localhost
```

A normal/reset state on NUT 2.8.5+ should include values similar to:

```text
battery.charge: 100
battery.runtime: 7200
battery.voltage: 13.00
battery.voltage.nominal: 13.80
input.voltage: 230.0
output.voltage: 230.0
ups.load: 25
ups.status: OL
```

On NUT 2.8.0-2.8.4, absence of `ups.load`, `input.voltage`, and `output.voltage` is expected and is not a simulator descriptor failure.

Depending on NUT version and feature handling, delay values can also appear:

```text
ups.delay.start: -1
ups.timer.start: -1
ups.delay.shutdown: -1
ups.timer.shutdown: -1
ups.timer.reboot: -1
```

See [NUT_VARIABLES.md](NUT_VARIABLES.md) for the full mapping.

## 7. Verify state transitions

Keep one terminal watching NUT:

```bash
watch -n 1 'upsc nutups-sim@localhost'
```

From another machine or terminal connect to the W5500 control port:

```bash
nc <simulator-ip> 5000
```

### On battery

```text
ARM ON
AC OFF
BATTERY 70
```

Expected high-level NUT status includes on-battery/discharging semantics such as:

```text
ups.status: OB DISCHRG
```

Exact token ordering can vary.

### Low battery

```text
BATTERY 4
RUNTIME 300
```

Expected NUT state should include low battery (`LB`). Runtime 300 seconds is also below the firmware's default remaining-time limit of 600 seconds.

### Load and AC voltages

```text
LOAD 65
INPUTVOLTAGE 22850
OUTPUTVOLTAGE 23010
```

On NUT 2.8.5+ expected values are:

```text
ups.load: 65
input.voltage: 228.5
output.voltage: 230.1
```

### Restore safely

```text
RESET
```

Confirm NUT returns to online state.

## 8. Host-written delay features

The HID descriptor exposes delay fields that NUT can read/write. The simulator status output includes:

```text
host_start_delay
host_shutdown_delay
host_reboot_delay
```

These reflect the underlying HID feature storage. `STARTDELAY` provides an explicit simulator-side setter for startup delay.

Because shutdown behavior can affect the real host, the simulator gates shutdown-request contribution behind its armed state.

The delay values are currently stored values, not a complete countdown/output-power model. A realistic delayed output-off/start sequence remains a separate future feature.

## 9. Linux permissions

If `usbhid-ups` sees the device as root but not under the normal NUT service account, investigate UDev permissions.

Useful checks:

```bash
lsusb
udevadm info --attribute-walk --name=/dev/bus/usb/BBB/DDD
journalctl -u 'nut*' --since today
```

Replace `BBB/DDD` with the bus/device numbers from `lsusb`.

The repository's `linux/98-upower-hid.rules` is intended for Linux HID-power/UDev integration, but your distribution's NUT package may also install its own USB permission rules. Do not replace package-provided NUT rules blindly.

## 10. If the Arduino subdriver is not selected

Run:

```bash
sudo usbhid-ups -DD -a nutups-sim
```

Check:

- actual USB VID/PID
- NUT version (`usbhid-ups -V`)
- whether your NUT build includes the Arduino HID subdriver
- whether a conflicting HID driver/process has claimed the interface
- USB permissions

When using an unusual clone VID/PID, NUT may require explicit matching options even though the HID descriptor itself is compatible.

## 11. `COMMLOST` versus real `NOCOMM`

The command:

```text
COMMLOST ON
```

sets the HID `CommunicationLost` PresentStatus bit. It does not unplug USB, detach the HID interface, or necessarily make NUT report driver-level `NOCOMM`.

To validate actual NUT communication-loss handling, use a separate test that genuinely interrupts the USB transport or driver.

## 12. Production-client caution

Before connecting Synology NAS or other production NUT clients to this test server, validate the complete state machine on a non-production host:

```text
OL -> OB -> LB -> shutdown path -> reset/recovery -> OL
```

The simulator is intentionally capable of generating states that invoke real shutdown automation.
