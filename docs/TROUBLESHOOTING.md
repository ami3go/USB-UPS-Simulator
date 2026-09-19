# Troubleshooting guide

## Build says the sketch is too large

The reference Ethernet/NUT simulator is already close to the Leonardo limit:

```text
28070 / 28672 bytes flash (97%)
```

If your build exceeds flash:

1. Confirm board target is `arduino:avr:leonardo`.
2. Use the reference Arduino AVR core and Ethernet library versions if possible.
3. Check whether local edits added strings, libraries, or debug code.
4. Avoid adding HTTP, JSON, TLS, web UI, or scenario logic to the AVR firmware.
5. Move new functionality into the Python/Cockpit side.

The original minimal `examples/UPS` sketch should remain much smaller.

## Upload port disappears or changes

Leonardo uses native USB and the bootloader can enumerate differently from the application.

Try:

1. Press reset twice quickly to enter the bootloader.
2. Run `arduino-cli board list` repeatedly.
3. Select the temporary bootloader port.
4. Upload immediately.
5. Temporarily remove the Ethernet shield if you suspect hardware interference.

Linux helper:

```bash
watch -n 0.2 'arduino-cli board list'
```

## W5500 shield does not work on Leonardo

Check the **2x3 ICSP connector** on the shield.

Leonardo SPI is on ICSP, not UNO D11/D12/D13. A W5500 shield without ICSP pass-through may stack physically but fail electrically.

Also verify:

- D10 is not reused by other hardware
- D4 is not pulled low by an SD card or other device
- Ethernet cable/link LEDs are active
- the Ethernet library is installed

## No DHCP address

The simulator falls back to:

```text
169.254.42.42/16
```

If DHCP fails:

1. Check link LEDs and cable.
2. Check your DHCP server/router lease table.
3. Put the control PC on a compatible `169.254.x.x/16` address if necessary.
4. Test:

```bash
ping 169.254.42.42
nc 169.254.42.42 5000
```

If several simulators use the same default MAC address, change the final MAC bytes in firmware.

## TCP connection works but commands return `ERR disarmed`

This is expected after boot/reset.

Run:

```text
ARM ON
```

Then issue state-changing commands.

Finish with:

```text
RESET
```

## `HELP` does not list every command

Intentional. The firmware keeps help/error strings very small to save flash.

Use [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md) as the authoritative command reference.

## NUT does not detect the Arduino

Start with:

```bash
lsusb
sudo usbhid-ups -DD -a nutups-sim
```

Check:

- USB cable supports data, not power only
- board application is running, not stuck in bootloader
- `ups.conf` uses `driver = usbhid-ups`
- actual USB VID/PID
- NUT build includes Arduino HID support
- UDev/USB permissions
- no other process has claimed the HID interface

See [NUT_SETUP.md](NUT_SETUP.md).

## `ups.load`, `input.voltage`, or `output.voltage` is missing

These fields require the NUT extension descriptor in the current Ethernet simulator.

Check that you flashed:

```text
examples/UPS_Simulator_Ethernet/UPS_Simulator_Ethernet.ino
```

and not the older/minimal:

```text
examples/UPS/UPS.ino
```

Then verify the firmware identity:

```text
IDENT?
```

Expected current simulator identity:

```text
OK NutUPS HID Simulator v2
```

If the fields are still absent, run `usbhid-ups -DD` and inspect the detected HID paths/NUT version.

## `input.voltage` specifically is missing

The expected NUT path is:

```text
UPS.PowerConverter.Input.[1].Voltage
```

The firmware generates this using the indexed HID Input collection in `HIDPowerDeviceNUT.cpp`. If you modified that descriptor, verify the collection remains indexed as required by the NUT HID parser.

## NUT reports the wrong voltage scale

The simulator wire protocol stores voltage in centivolts:

```text
1300  = 13.00 V
23000 = 230.00 V
```

When using the Python API, call the volt-based methods instead of sending raw centivolts:

```python
ups.set_voltage(13.2)
ups.set_input_voltage(230.0)
ups.set_output_voltage(229.5)
```

## Low battery does not appear

With `LOWBAT AUTO`, low battery activates at or below the configured 5% charge limit.

Example:

```text
ARM ON
AC OFF
BATTERY 4
STATUS?
```

You can force the flag independently with:

```text
LOWBAT ON
```

## Charging does not appear

Default `CHARGING AUTO` requires:

- AC present
- battery below 100%

Example:

```text
ARM ON
AC ON
BATTERY 50
CHARGING AUTO
STATUS?
```

Or force it:

```text
CHARGING ON
```

## `COMMLOST ON` does not make NUT say `NOCOMM`

Expected limitation.

`COMMLOST ON` sets the HID `CommunicationLost` status bit. It does not physically break USB transport.

For driver-level `NOCOMM` testing, genuinely interrupt USB/driver communication using a separate test method.

## Python driver cannot connect over TCP

Check raw transport first:

```bash
nc <simulator-ip> 5000
```

Then:

```text
PING
```

If raw TCP works but Python does not:

```bash
ups-sim --host <simulator-ip> --timeout 5 status
```

Check firewalls and whether another control client is already holding the simulator's single TCP connection.

## Python UART driver fails to import `serial`

Install the optional dependency:

```bash
python -m pip install -e './python-driver[serial]'
```

or:

```bash
python -m pip install pyserial
```

## UART gives no response

Verify:

```text
baud: 115200
TX Leonardo D1 -> adapter RX
RX Leonardo D0 -> adapter TX
GND -> GND
```

Use TTL-compatible logic levels, not RS-232 voltage levels.

## Python `armed_session()` resets state unexpectedly

That is its safety behavior.

```python
with ups.armed_session():
    ...
```

calls `RESET` when leaving the context, including after exceptions.

For special test cases that intentionally need the state preserved, inspect/use the `reset_on_exit` option deliberately and restore the safe state yourself afterward.

## Host shuts down during testing

The simulator is doing what it was designed to do: NUT may react to `OB`, `LB`, or shutdown-imminent states.

Before running aggressive scenarios:

- isolate the NUT test environment
- disconnect production clients
- disable real shutdown actions if appropriate for the test stage
- keep a second management machine available
- use `RESET` immediately after the required observation

## Simulator disappears when the NUT host powers off

The Leonardo was probably powered only from the host USB port.

For full-cycle shutdown tests, independently power the Leonardo through a supported external-power input so the W5500 remains reachable after the host shuts down.

## Ethernet simulator resets to online/100% after MCU reboot

Intentional. Simulator state is not persisted. Every MCU restart returns to the disarmed safe state to prevent stale fault conditions from causing unintended shutdowns after a power interruption.

## CI fails after documentation-only changes

Documentation changes should not alter firmware output, but repository CI still compiles the Arduino examples and runs Python tests. Inspect the Actions logs for whether the failure is environmental or caused by an accidental source change.
