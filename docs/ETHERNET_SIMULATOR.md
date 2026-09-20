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

For shutdown/recovery testing, power the Leonardo independently through a supported external-power input while keeping USB connected to the NUT host. This keeps the W5500/controller alive after the host powers down so restored mains can be simulated later.

Do not assume every clone implements power selection identically; verify the exact board specification before applying external and USB power simultaneously.

## Network behavior

The firmware attempts DHCP with a bounded startup timeout. If DHCP fails it falls back to:

```text
IP:      169.254.42.42
Subnet:  255.255.0.0
TCP:     5000
```

Default locally administered MAC:

```text
02:55:50:53:00:01
```

DHCP maintenance is performed only when a real DHCP lease exists. Potentially blocking renew/rebind work is postponed while the simulator is armed so an active fault-injection session is not stalled by DHCP failure.

Give each simulator a unique MAC address if multiple boards share one LAN.

## Safety model

The simulator starts in a known safe state:

```text
DISARMED
AC present
battery 100%
load 25%
input 230 V
output 230 V
fault flags cleared
```

The safe model is computed before Ethernet initialization, so a slow/failed DHCP attempt cannot leave USB HID `PresentStatus` at its zero-initialized on-battery/no-battery state.

Read-only queries work while disarmed. State-changing commands require:

```text
ARM ON
```

`ARM ON` uses a 120-second firmware-enforced lease. Every command received while armed refreshes that lease. An explicit lease is also supported:

```text
ARM ON 300
```

Accepted range is `0..3600` seconds; `0` intentionally disables lease expiry. If a non-zero lease expires, the firmware restores the safe state and disarms even if the controlling process crashed or the network disappeared.

Either `RESET` or `ARM OFF` immediately returns to the safe online state.

## Control channels

### Ethernet

```bash
nc <simulator-ip> 5000
```

A new connection prints the identity and current arming state:

```text
OK NutUPS HID Simulator v2
OK DISARMED
```

or, if an existing test is armed:

```text
OK NutUPS HID Simulator v2
OK ARMED
```

The newest TCP connection replaces the previous controller. This prevents a stale/half-open W5500 socket from locking out recovery access.

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
REPORT
```

Safety/control:

```text
ARM ON|OFF
ARM ON 0..3600
RESET
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

Voltage values are centivolts on the wire (`1300` = 13.00 V, `23000` = 230.00 V). Use [CONTROL_PROTOCOL.md](CONTROL_PROTOCOL.md) for the full reference.

## USB/HID reliability hardening

The simulator now:

- publishes a coherent `PresentStatus` snapshot atomically
- uses atomic access for 16-bit state shared with the USB interrupt
- rejects host `SET_REPORT` writes to simulator-owned read-only Feature reports
- avoids heap allocation in USB Feature receive handling
- checks HID interrupt endpoint space before sending reports
- sends `PresentStatus` first
- only marks an interrupt-report batch delivered if the whole batch was queued; otherwise it retries on the next loop
- keeps the NUT descriptor extension inside the original top-level UPS Application collection

These changes are important on the ATmega32U4 because 16-bit accesses are not atomic and the Arduino USB interrupt endpoint can otherwise block report sending.

## NUT-facing measurements

The simulator exposes the base HIDPowerDevice fields plus the NUT extension, including:

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

`ups.load`, `input.voltage`, and `output.voltage` require **NUT 2.8.5+**. See [NUT_VARIABLES.md](NUT_VARIABLES.md) for exact HID paths and version details.

## Python control

The preferred automation layer is the repository's Python driver. It synchronizes TCP/UART framing with `PING`, checks the v2 firmware identity on connect, and provides `armed_session()` cleanup plus the firmware arming lease.

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    with ups.armed_session(lease_seconds=120):
        ups.set_ac(False)
        ups.set_battery(40)
        ups.set_load(65)
        print(ups.status())
```

See [the Python driver manual](../python-driver/README.md).

## Security

The W5500 control protocol has no authentication or encryption. The arming gate and lease are safety controls, not access controls.

Use a direct control link, dedicated management/test VLAN, or firewall rules that restrict TCP/5000 to authorized controllers. Authentication only in Python/Cockpit cannot protect the raw Arduino port from another host that can connect directly.

## Current Leonardo resource use

Reference CI build is pinned to Arduino AVR core 1.8.8 and Ethernet library 2.0.2 and compiles with warnings enabled.

```text
Original UPS example:
  flash 10,176 / 28,672 bytes (35%)
  RAM      330 / 2,560 bytes (12%)

Ethernet/NUT simulator:
  flash 27,854 / 28,672 bytes (97%)
  RAM    1,321 / 2,560 bytes (51%)
```

The simulator has **818 bytes of flash headroom**. CI enforces a maximum of 28,160 bytes so at least 512 bytes remain available for reliability fixes.

Keep feature growth on the Linux/Python/Cockpit side unless firmware participation is essential to USB HID behavior. Scenario engines, web UI, persistence, rich logging and orchestration do not belong on this AVR target.

## Known limitation: communication loss

`COMMLOST ON` sets the HID `CommunicationLost` flag, but it does not physically detach USB. It therefore does not guarantee a NUT driver-level `NOCOMM` event. Real USB transport-loss testing needs a separate mechanism.

The HID delay Feature values are also stored values, not yet a complete countdown/output-power model; realistic delayed output-off/start behavior remains a future feature.
