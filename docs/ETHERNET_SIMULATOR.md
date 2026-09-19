# Ethernet-controlled USB HID UPS simulator

The `examples/UPS_Simulator_Ethernet` firmware turns an Arduino Leonardo-class ATmega32U4 board into a remotely controlled USB HID UPS. A W5500 Ethernet shield provides the primary control channel while `Serial1` provides a UART fallback.

For installation instructions start with [FLASHING.md](FLASHING.md). For the complete command table use [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md).

## Architecture

```text
                     control / test LAN
Cockpit / Python / nc -------- TCP 5000
                              |
                              v
                        +-----------+
                        |   W5500   |
                        +-----+-----+
                              | SPI/ICSP
                        +-----+-----+
                        | Leonardo  |
                        +--+-----+--+
                           |     |
                     USB HID   Serial1
                           |     115200
                           v
                     NUT host under test
```

The USB interface remains the UPS-facing connection. Ethernet/UART are only used to inject simulated conditions.

## Hardware

Reference hardware:

- Arduino Leonardo or compatible ATmega32U4 native-USB board
- W5500 Arduino Ethernet shield
- shield must have the 2x3 ICSP socket populated for Leonardo SPI
- USB data cable to the system under test
- Ethernet cable to the control network

Standard shield pin use:

- ICSP: MOSI/MISO/SCK
- D10: W5500 chip select
- D4: microSD chip select; firmware holds it HIGH while SD is unused
- D0/D1: optional hardware UART (`Serial1`)

See [HARDWARE.md](HARDWARE.md) for wiring and powering details.

## Powering for full shutdown tests

If the simulated UPS causes the USB host to shut down, the controller must remain alive so it can later simulate restored power.

Therefore, for full-cycle tests, power the Leonardo independently through a supported external-power input while keeping its USB cable connected to the NUT host.

Do not assume every clone implements power selection identically; verify the exact board specification before applying external and USB power simultaneously.

## Network behavior

The firmware first attempts DHCP.

If DHCP fails it falls back to:

```text
IP:      169.254.42.42
Subnet:  255.255.0.0
TCP:     5000
```

Default locally administered MAC:

```text
02:55:50:53:00:01
```

Give each simulator a unique MAC address if multiple boards share one LAN.

## Safety model

The simulator starts:

```text
DISARMED
AC present
battery 100%
load 25%
input 230 V
output 230 V
fault flags cleared
```

Read-only queries work while disarmed. State-changing commands require:

```text
ARM ON
```

Either:

```text
RESET
```

or:

```text
ARM OFF
```

returns the simulator to the safe online state and disarms it.

This behavior is deliberate because NUT can react to the generated `OB`, `LB`, overload, and shutdown-imminent states by shutting down real systems.

## Control channels

### Ethernet

```bash
nc <simulator-ip> 5000
```

A new connection prints:

```text
OK NutUPS HID Simulator v2
OK DISARMED
```

### UART

Use `Serial1` at 115200 baud on Leonardo D0/D1. The UART accepts the same commands as TCP.

## Command summary

Read-only:

```text
PING
IDENT?
STATUS?
NETWORK?
HELP
```

Safety/control:

```text
ARM ON|OFF
RESET
REPORT
```

State injection:

```text
AC ON|OFF
BATTERY 0..100
RUNTIME AUTO|0..65535
VOLTAGE 0..65535
LOAD 0..100
INPUTVOLTAGE 0..65535
OUTPUTVOLTAGE 0..65535
STARTDELAY -1..32767
CHARGING AUTO|ON|OFF
LOWBAT AUTO|ON|OFF
OVERLOAD ON|OFF
REPLACE ON|OFF
COMMLOST ON|OFF
SHUTDOWN ON|OFF
```

Voltage values are centivolts on the wire:

```text
1300  = 13.00 V
23000 = 230.00 V
```

Use [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md) for the full reference.

## Dynamic model

### Runtime

`RUNTIME AUTO` scales runtime according to battery charge and the configured full-runtime reference.

### Charging

`CHARGING AUTO` reports charging when AC is present and battery charge is below 100%.

### Low battery

`LOWBAT AUTO` becomes active at or below the default 5% remaining-capacity limit.

### Remaining-time limit

The default low-runtime threshold is 600 seconds. While discharging, runtime at or below this threshold sets the remaining-time-limit-expired condition and contributes to shutdown-imminent behavior.

## NUT-facing measurements

The simulator exposes the base HIDPowerDevice fields plus the NUT extension:

```text
battery.charge
battery.runtime
battery.voltage
battery.voltage.nominal
battery.charge.low
battery.charge.warning
battery.runtime.low
battery.type
ups.load
input.voltage
output.voltage
ups.delay.start / ups.timer.start
ups.delay.shutdown / ups.timer.shutdown
ups.timer.reboot
ups.status
```

See [NUT_VARIABLES.md](NUT_VARIABLES.md) for exact HID paths.

## Example outage

```text
ARM ON
AC OFF
BATTERY 70
LOAD 55
STATUS?
```

The NUT host should observe on-battery/discharging state.

## Example low battery

```text
ARM ON
AC OFF
BATTERY 4
RUNTIME 300
STATUS?
```

This activates low-battery state and places runtime below the default 600-second remaining-time limit.

## Example voltage/load simulation

```text
ARM ON
LOAD 80
INPUTVOLTAGE 21500
OUTPUTVOLTAGE 22950
STATUS?
```

NUT should report approximately:

```text
ups.load: 80
input.voltage: 215.0
output.voltage: 229.5
```

## Example restoration

```text
AC ON
BATTERY 45
RUNTIME AUTO
LOWBAT AUTO
CHARGING AUTO
OVERLOAD OFF
REPLACE OFF
COMMLOST OFF
SHUTDOWN OFF
STATUS?
```

Finish with:

```text
RESET
```

## Python control

The preferred automation layer is the repository's Python driver:

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    with ups.armed_session():
        ups.set_ac(False)
        ups.set_battery(40)
        ups.set_load(65)
        ups.set_input_voltage(228.5)
        ups.set_output_voltage(230.1)
        print(ups.status())
```

`armed_session()` resets the simulator on exit, including exception paths.

See [the Python driver manual](../python-driver/README.md).

## Security

The W5500 control protocol has no authentication or encryption. Do not expose TCP/5000 to an untrusted network.

`ARM ON` protects against accidental mutation; it is not an authentication mechanism.

## Current Leonardo resource use

Reference CI build with Arduino AVR core 1.8.8 and Ethernet library 2.0.2:

```text
Original UPS example:
  flash  9,818 / 28,672 bytes (34%)
  RAM      302 / 2,560 bytes (11%)

Ethernet/NUT simulator:
  flash 28,070 / 28,672 bytes (97%)
  RAM    1,296 / 2,560 bytes (50%)
```

Only about 602 bytes of flash headroom remain. Treat the AVR firmware as effectively feature-frozen. Put scenario engines, web/Cockpit UI, persistent configuration, authentication, logs, and orchestration in the Linux/Python side.

## Known limitation: communication loss

`COMMLOST ON` sets the HID `CommunicationLost` flag, but it does not physically detach USB. It therefore does not guarantee a NUT driver-level `NOCOMM` event. Real USB transport-loss testing needs a separate mechanism.
