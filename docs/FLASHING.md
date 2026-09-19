# Flashing and first-use guide

This guide covers the recommended Arduino Leonardo + W5500 Ethernet shield configuration.

## 1. Required hardware

- Arduino Leonardo or compatible ATmega32U4 board
- W5500 Arduino Ethernet shield with the **2x3 ICSP socket populated**
- USB data cable
- Ethernet cable
- Optional external Leonardo power supply for full shutdown/recovery testing
- Optional USB-UART adapter for the `Serial1` fallback control interface

The W5500 shield must obtain SPI from the Leonardo ICSP header. A shield that only uses UNO D11/D12/D13 for SPI will not work on Leonardo without rewiring.

See [HARDWARE.md](HARDWARE.md) before powering the assembly.

## 2. Software requirements

The project is continuously compiled with:

- Arduino AVR core 1.8.8
- Arduino Ethernet library 2.0.2
- board target `arduino:avr:leonardo`

Newer compatible versions may also work, but the CI versions above are the known build reference.

## 3. Arduino IDE method

### Install the Arduino IDE

Install Arduino IDE 2.x from Arduino's official distribution for your operating system.

### Install the project as an Arduino library

Either clone the repository into the Arduino libraries directory or download the repository ZIP and add it as a library.

Recommended clone layout:

```text
<Arduino sketchbook>/libraries/HIDPowerDevice/
    library.properties
    src/
    examples/
    ...
```

For the default Linux sketchbook that is normally:

```bash
mkdir -p ~/Arduino/libraries
cd ~/Arduino/libraries
git clone https://github.com/ami3go/USB-UPS-Simulator.git HIDPowerDevice
cd HIDPowerDevice
git switch main
```

On Windows the sketchbook is commonly under `Documents\Arduino\libraries`.

### Install the Ethernet library

In Arduino IDE:

1. Open **Tools -> Manage Libraries**.
2. Search for `Ethernet`.
3. Install the Arduino Ethernet library.

### Select the sketch

Open:

```text
examples/UPS_Simulator_Ethernet/UPS_Simulator_Ethernet.ino
```

or use:

```text
File -> Examples -> HIDPowerDevice -> UPS_Simulator_Ethernet
```

### Select the board and port

Choose:

```text
Tools -> Board -> Arduino AVR Boards -> Arduino Leonardo
```

Then select the Leonardo serial port under **Tools -> Port**.

### Compile before upload

Use **Sketch -> Verify/Compile** first. The current reference build is close to the Leonardo flash limit and should report approximately:

```text
Sketch uses 28070 bytes (97%) of program storage space.
Global variables use 1296 bytes (50%) of dynamic memory.
```

Small differences can occur with toolchain/library versions.

### Upload

Use **Sketch -> Upload**.

After programming, reconnect/re-enumeration of the Leonardo USB device is normal because the bootloader and application use different USB states.

## 4. Arduino CLI method

### Install dependencies

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli lib install Ethernet
```

### Clone into the Arduino library directory

```bash
mkdir -p ~/Arduino/libraries
cd ~/Arduino/libraries
git clone https://github.com/ami3go/USB-UPS-Simulator.git HIDPowerDevice
cd HIDPowerDevice
git switch main
```

### Detect the Leonardo

```bash
arduino-cli board list
```

Example device names may look like `/dev/ttyACM0` on Linux or `COM5` on Windows.

### Compile

```bash
arduino-cli compile \
  --fqbn arduino:avr:leonardo \
  ~/Arduino/libraries/HIDPowerDevice/examples/UPS_Simulator_Ethernet
```

### Upload

Linux example:

```bash
arduino-cli upload \
  --fqbn arduino:avr:leonardo \
  -p /dev/ttyACM0 \
  ~/Arduino/libraries/HIDPowerDevice/examples/UPS_Simulator_Ethernet
```

Windows example:

```powershell
arduino-cli upload --fqbn arduino:avr:leonardo -p COM5 "$HOME\Documents\Arduino\libraries\HIDPowerDevice\examples\UPS_Simulator_Ethernet"
```

If the port changes when the bootloader starts, rerun `arduino-cli board list` and use the new port.

## 5. Connect the W5500 shield

With power removed:

1. Stack the W5500 shield onto the Leonardo.
2. Confirm that the shield's 2x3 ICSP socket mates with the Leonardo ICSP header.
3. Do not install a microSD card for initial commissioning.
4. Connect Ethernet.
5. Connect Leonardo USB to the NUT host under test.

The firmware keeps D4 HIGH to deselect the unused SD interface. Ethernet uses D10 as chip select.

## 6. Network startup

The firmware first requests an address using DHCP.

Find the leased address in your router/DHCP server, then test TCP port 5000.

If DHCP fails, the simulator falls back to:

```text
IP:     169.254.42.42
Mask:   255.255.0.0
Port:   5000/tcp
```

The fallback is link-local style addressing, so the control computer must have a compatible `169.254.x.x/16` interface to reach it.

## 7. First commissioning test

Open a TCP session:

```bash
nc <simulator-ip> 5000
```

A new connection should print two greeting lines similar to:

```text
OK NutUPS HID Simulator v2
OK DISARMED
```

Run:

```text
PING
IDENT?
STATUS?
ARM ON
AC OFF
BATTERY 40
LOAD 65
INPUTVOLTAGE 22850
OUTPUTVOLTAGE 23010
STATUS?
RESET
STATUS?
```

Expected high-level behavior:

- `PING` -> `OK PONG`
- state-changing commands fail while disarmed
- `ARM ON` enables state changes
- `AC OFF` creates an on-battery/discharging condition
- `BATTERY 40` changes battery charge to 40%
- `LOAD 65` produces `ups.load = 65`
- `INPUTVOLTAGE 22850` represents 228.50 V
- `OUTPUTVOLTAGE 23010` represents 230.10 V
- `RESET` restores safe defaults and disarms the simulator

## 8. Verify USB HID on Linux

Check that the board enumerates:

```bash
lsusb
```

For NUT verification, continue with [NUT_SETUP.md](NUT_SETUP.md).

The repository also contains:

```text
linux/98-upower-hid.rules
```

That rule is useful for Linux desktop/UDev recognition of the Arduino HID power device. NUT itself still requires its normal USB permissions/configuration.

## 9. Full power-cycle testing

For a test where the NUT host is intentionally shut down, the simulator must remain powered after the host turns off. Power the Leonardo independently through its supported external input while keeping USB connected to the host.

A common Leonardo recommendation is 7-12 V on the barrel/VIN input path. Follow the specifications of the exact board or clone you own.

This arrangement lets an external controller continue to reach the W5500 and later simulate mains restoration.

## 10. Upload recovery

If an application sketch makes normal uploading difficult:

1. Disconnect the shield temporarily if needed.
2. Press Leonardo reset twice quickly to enter the bootloader.
3. Watch for the temporary bootloader port.
4. Select that port and start upload immediately.

On Linux:

```bash
watch -n 0.2 'arduino-cli board list'
```

can help identify the temporary port.

## Next steps

- [Control protocol](CONTROL_PROTOCOL.md)
- [Python driver manual](../python-driver/README.md)
- [NUT setup](NUT_SETUP.md)
- [Troubleshooting](TROUBLESHOOTING.md)
