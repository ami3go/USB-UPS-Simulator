# Ethernet-controlled USB HID UPS simulator

This example turns an Arduino Leonardo-class ATmega32U4 board into a USB HID UPS while a W5500 Ethernet shield provides a separate control channel.

## Intended use

The USB port is connected to the system under test. That system sees a HID Power Device / UPS.

The Ethernet interface is connected to the management or test network. A test controller, Cockpit plugin, or terminal client can change the simulated UPS state without touching the USB link.

A hardware UART control channel is also available on `Serial1` at 115200 baud for bench use.

## Hardware

- Arduino Leonardo or compatible ATmega32U4 board supported by this library
- Arduino Ethernet Shield 2 or compatible W5500 shield/module
- USB cable to the host under test
- Ethernet cable to the control network

### Pin use

Common W5500 Arduino shields use:

- D10: Ethernet chip select
- D4: microSD chip select
- ICSP header: SPI bus on Leonardo

The simulator therefore does not use D4 or D10 for status/control GPIO. D4 is driven HIGH to keep the unused SD card interface de-selected.

## Network

The firmware first attempts DHCP.

If DHCP fails it uses:

- IP: `169.254.42.42`
- subnet: `255.255.0.0`
- TCP control port: `5000`

The MAC address in the example is locally administered. Change the final bytes if more than one simulator is placed on the same LAN.

## Safety model

The simulator boots in a safe state:

- disarmed
- AC present
- battery 100%
- no low-battery, overload, replacement, communication-loss, or shutdown flags

State-changing commands are rejected until:

```text
ARM ON
```

`ARM OFF` or `RESET` immediately restores the safe online state and disarms the simulator.

This is intentional because a simulated `OB`/low-battery condition can cause the NUT system under test to shut down real machines.

## Control protocol

The control protocol is line-oriented ASCII over TCP port 5000 or hardware UART.

Commands are case-insensitive and terminated by LF (`\n`). CRLF is also accepted.

### Read-only commands

```text
PING
IDENT?
STATUS?
NETWORK?
HELP
```

### State control

```text
ARM ON|OFF
RESET

AC ON|OFF
BATTERY 0..100
RUNTIME AUTO|0..65535
VOLTAGE 0..65535
CHARGING AUTO|ON|OFF
LOWBAT AUTO|ON|OFF
OVERLOAD ON|OFF
REPLACE ON|OFF
COMMLOST ON|OFF
SHUTDOWN ON|OFF
REPORT
```

`VOLTAGE` is expressed in centivolts to match the HID descriptor. For example, `1300` represents 13.00 V.

With `RUNTIME AUTO`, runtime-to-empty scales from `iAvgTimeToEmpty` according to the current battery percentage.

With `LOWBAT AUTO`, the HID `BelowRemainingCapacityLimit` flag becomes active at or below `iRemnCapacityLimit` (5% by default).

## Example sessions

### Basic outage

```text
ARM ON
AC OFF
BATTERY 70
STATUS?
```

The host should observe an on-battery / discharging condition.

### Low battery

```text
ARM ON
AC OFF
BATTERY 4
RUNTIME 300
STATUS?
```

This should assert both the low-battery capacity flag and, because runtime is below the default 600-second remaining-time limit, the remaining-time-limit-expired flag.

### Overload

```text
ARM ON
OVERLOAD ON
STATUS?
```

### Power restored

```text
AC ON
BATTERY 45
RUNTIME AUTO
LOWBAT AUTO
OVERLOAD OFF
REPLACE OFF
COMMLOST OFF
SHUTDOWN OFF
STATUS?
```

Charging is automatically reported while AC is present and battery capacity is below 100%.

### Finish a test safely

```text
RESET
```

## Connecting from Linux

For a simple interactive test:

```bash
nc <simulator-ip> 5000
```

Then enter commands such as:

```text
STATUS?
ARM ON
AC OFF
BATTERY 4
```

## Integration with Nut-ups

The recommended architecture is:

```text
                     control LAN
Cockpit / test tool --------------------+
                                        |
                                        v
                                  +-----------+
                                  |  W5500    |
                                  +-----+-----+
                                        |
                                  Arduino Leonardo
                                        |
                                  USB HID Power Device
                                        |
                                        v
                                Nut-ups server under test
```

The Nut-ups host should consume the USB HID UPS normally. The management side should use the Ethernet control port only to inject simulated conditions.

Do not expose TCP port 5000 to an untrusted network. The current protocol intentionally has no authentication; the `ARM` mechanism protects against accidental state changes, not hostile access.
