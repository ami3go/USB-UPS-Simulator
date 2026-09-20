# Troubleshooting guide

## Build says the sketch is too large

Pinned reference build:

```text
Ethernet/NUT simulator: 27854 / 28672 bytes flash, 1321 / 2560 bytes RAM
```

CI rejects simulator builds above 28,160 bytes to preserve at least 512 bytes of flash for reliability fixes.

If your build exceeds the limit:

1. target `arduino:avr:leonardo`
2. use Arduino AVR core `1.8.8`
3. use Ethernet library `2.0.2`
4. check local strings/debug libraries
5. keep web/TLS/scenario/persistence features on Python/Cockpit

## Upload port disappears or changes

Leonardo uses native USB and the bootloader may enumerate on a different port.

1. Press reset twice quickly.
2. Run `arduino-cli board list` repeatedly.
3. Select the temporary bootloader port.
4. Upload immediately.
5. Remove the Ethernet shield temporarily if hardware interference is suspected.

## W5500 does not work on Leonardo

The shield must use the Leonardo **2x3 ICSP connector** for SPI. Check:

- ICSP socket physically populated/mated
- D10 free for W5500 CS
- D4 held HIGH / SD unused during commissioning
- Ethernet link LEDs
- Ethernet 2.0.2 installed for the reference build

## No DHCP address

The hardened firmware waits a bounded time for DHCP and then uses:

```text
169.254.42.42/16
TCP 5000
```

Test:

```bash
ping 169.254.42.42
nc 169.254.42.42 5000
```

Only a real DHCP lease is maintained later. DHCP maintenance is postponed while armed so a failed renewal cannot stall a fault-injection sequence.

## TCP greeting or first command looks wrong

Current firmware greets immediately when a client connects:

```text
OK NutUPS HID Simulator v2
OK DISARMED
```

or `OK ARMED` when already armed.

The current Python driver also sends `PING` during connect and reads through `OK PONG`, so it works with older firmware that emitted its greeting only after the first command.

If a custom client is used, do not assume a fixed timing window; frame replies by lines and account for the two greeting lines.

## A second TCP client disconnects the first one

Intentional. The newest TCP connection takes over the simulator. This is the recovery mechanism for stale/half-open W5500 sessions.

Do not run two independent controllers simultaneously unless takeover is intended.

## Commands return `ERR disarmed`

Expected after boot/reset or after an arming lease expires.

```text
ARM ON
```

uses the default 120-second lease. Every command refreshes it.

```text
ARM ON 300
```

selects a 300-second lease. `ARM ON 0` explicitly disables lease expiry.

If the controller crashes and stops sending commands, a non-zero lease automatically restores the safe state.

## `REPORT` returns `ERR disarmed`

Update the firmware. Hardened firmware permits `REPORT` while disarmed because it only re-sends the current state.

## NUT does not detect the Arduino

Start with:

```bash
lsusb
usbhid-ups -V
sudo usbhid-ups -DD -a nutups-sim
```

Check USB data cable, VID/PID, `driver = usbhid-ups`, permissions, and whether another process has claimed the HID interface.

## `ups.load`, `input.voltage`, or `output.voltage` is missing

These variables require **NUT 2.8.5 or later**.

First check:

```bash
usbhid-ups -V
```

NUT 2.8.0-2.8.4 can use the core Arduino HID variables but does not map these three fields.

Also verify that you flashed:

```text
examples/UPS_Simulator_Ethernet/UPS_Simulator_Ethernet.ino
```

and that:

```text
IDENT?
```

returns:

```text
OK NutUPS HID Simulator v2
```

## `input.voltage` specifically is missing on NUT 2.8.5+

The required path is:

```text
UPS.PowerConverter.Input.[1].Voltage
```

The descriptor uses an indexed collection (`0x81`) to create `[1]`. Descriptor edits that remove that indexed collection can make the field disappear even though the firmware still compiles.

## NUT reports the wrong voltage scale

The raw control protocol uses centivolts:

```text
1300  = 13.00 V
23000 = 230.00 V
```

The Python API accepts volts:

```python
ups.set_voltage(13.2)
ups.set_input_voltage(230.0)
ups.set_output_voltage(229.5)
```

## NUT briefly reports OB/RB when the simulator resets

That was a pre-hardening startup bug. Current firmware computes its safe `PresentStatus` before starting Ethernet/DHCP. Reflash the current firmware and retest while watching NUT logs.

If a transient remains on real hardware, capture `usbhid-ups -DD` output during reset; hardware timing still needs validation.

## Low battery does not appear

With `LOWBAT AUTO`, low battery activates at or below 5% by default:

```text
ARM ON
AC OFF
BATTERY 4
STATUS?
```

Force independently with `LOWBAT ON`.

## Charging does not appear

`CHARGING AUTO` needs AC present and battery below 100%:

```text
ARM ON
AC ON
BATTERY 50
CHARGING AUTO
```

## `COMMLOST ON` does not produce `NOCOMM`

Expected. It sets the HID `CommunicationLost` bit; it does not detach USB. Real NUT transport-loss testing requires actually interrupting USB/driver communication.

## Python reports an unsupported firmware

The hardened Python driver verifies:

```text
NutUPS HID Simulator v2
```

on connect. Flash matching v2 firmware or use a driver version compatible with your firmware protocol.

## Python TCP cannot connect

Check raw access:

```bash
nc <simulator-ip> 5000
```

A new client takes over from a stale one, so power cycling should no longer be necessary merely to recover a half-open control socket.

Check VLAN/firewall rules as well. TCP/5000 is intentionally unauthenticated and should only be reachable from trusted test controllers.

## Python UART fails to import `serial`

```bash
python -m pip install -e './python-driver[serial]'
```

or install `pyserial` directly.

## UART reply is shifted by `NutUPS ready`

Use the current Python driver. It synchronizes UART with `PING`, consuming late boot/banner lines before normal commands.

UART wiring is Leonardo D1 -> adapter RX, D0 <- adapter TX, plus common GND at 115200 8N1.

## `armed_session()` masks my test exception

Update the Python driver. Current behavior preserves the original test exception. If cleanup fails because the connection is gone, cleanup failure is emitted as `RuntimeWarning`.

The firmware lease is still the final safety mechanism if the process is killed outright.

## Host-written delay timers do not count down

Current limitation. `DelayBeforeStartup`, `DelayBeforeShutdown`, and `DelayBeforeReboot` are HID storage values, not yet a full output-power countdown model. A realistic delayed output-off/start state machine is planned as a separate feature rather than being hidden inside this hardening change.

## Simulator disappears when the NUT host powers off

The Leonardo was likely powered only by USB. For full shutdown/recovery tests, independently power Leonardo + W5500 through a supported external-power input.

## Multiple simulators conflict

MAC and USB serial are currently compile-time defaults. Multiple boards on one LAN/host need unique identities. A unified simulator-ID mechanism is not implemented yet.

## Security concern: raw TCP/5000

There is no protocol authentication. Python/Cockpit authentication cannot secure the raw Arduino listener because a reachable host can bypass those clients.

Use a point-to-point control link, dedicated management/test VLAN, or firewall rules restricting TCP/5000.

## CI fails after a firmware/HID change

Current CI pins the reference toolchain, enables warnings, compiles both Leonardo sketches, runs Python 3.9/3.13 tests when the firmware/protocol changes, and enforces the 28,160-byte simulator flash budget.

Inspect whether the failure is:

- actual compiler error
- simulator over the flash budget
- host/firmware protocol-test mismatch
- upstream Arduino-core warning versus repository warning
