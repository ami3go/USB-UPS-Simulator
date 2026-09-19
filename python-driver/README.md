# NutUPS simulator Python driver user manual

`nutups-simulator-control` is the host-side control library and CLI for the Arduino Leonardo + W5500 USB HID UPS simulator.

The Python driver talks only to the simulator control interface. The machine under test continues to see the Leonardo as a USB HID UPS.

## Requirements

- Python **3.9 or newer**
- TCP access to the W5500 simulator, or a UART adapter for `Serial1`
- `pyserial` only when UART control is required

The CI test matrix covers Python 3.9 and 3.13.

## Installation

### Recommended development install

From repository root:

```bash
python -m venv .venv
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install:

```bash
python -m pip install --upgrade pip
python -m pip install -e ./python-driver
```

The editable install provides both:

```python
from ups_simulator import UpsSimulator
```

and the CLI:

```text
ups-sim
```

### UART support

Install the serial extra:

```bash
python -m pip install -e './python-driver[serial]'
```

On PowerShell, quoting the same path is recommended:

```powershell
python -m pip install -e '.\python-driver[serial]'
```

## First TCP test

```bash
ups-sim --host 192.168.1.50 ping
ups-sim --host 192.168.1.50 identify
ups-sim --host 192.168.1.50 status
```

The default control port is 5000.

If DHCP failed, the firmware fallback address is `169.254.42.42/16`.

## Basic Python usage

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    print(ups.ping())
    print(ups.identify())
    print(ups.network_status())
    print(ups.status())
```

The context manager opens the transport on entry and closes it on exit.

## Safe test pattern

For tests that can produce real NUT shutdown actions, use `armed_session()`:

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    with ups.armed_session():
        ups.set_ac(False)
        ups.set_battery(4)
        ups.set_runtime(300)
        print(ups.status())
```

`armed_session()` performs:

```text
ARM ON
... test body ...
RESET
```

The reset happens in a `finally` path, so it also runs when the test raises an exception.

### Disarm instead of reset

```python
with ups.armed_session(reset_on_exit=False):
    ...
```

exits using `ARM OFF`, which also restores the safe state. In normal automated tests the default reset behavior is recommended.

## TCP constructor

```python
ups = UpsSimulator.tcp(
    host="192.168.1.50",
    port=5000,
    timeout=2.0,
)
```

Parameters:

| Parameter | Default | Meaning |
|---|---:|---|
| `host` | required | Simulator IP/hostname. |
| `port` | `5000` | W5500 control TCP port. |
| `timeout` | `2.0` | Connect/read timeout in seconds. |

The transport handles the two firmware greeting lines automatically, including the case where both arrive in one TCP packet.

## UART constructor

```python
ups = UpsSimulator.serial(
    port="/dev/ttyUSB0",
    baudrate=115200,
    timeout=2.0,
)
```

Windows example:

```python
ups = UpsSimulator.serial("COM5")
```

Leonardo UART wiring uses hardware `Serial1` on D0/D1. See `docs/HARDWARE.md`.

## Read-only API

### `ping()`

```python
ups.ping() -> bool
```

Returns `True` for the expected `PONG` response.

### `identify()`

```python
ups.identify() -> str
```

Current firmware returns identity similar to:

```text
NutUPS HID Simulator v2
```

### `status()`

```python
status = ups.status()
```

Returns a frozen `SimulatorStatus` dataclass.

Fields:

| Attribute | Type | Meaning |
|---|---|---|
| `armed` | `bool` | Whether mutation commands are enabled. |
| `ac_present` | `bool` | Simulated AC state. |
| `battery_percent` | `int` | Battery charge 0..100. |
| `runtime_seconds` | `int` | Runtime-to-empty. |
| `runtime_mode` | `str` | `auto` or `manual`. |
| `voltage_centivolts` | `int` | Battery voltage raw value. |
| `load_percent` | `int` | UPS load percentage. |
| `input_voltage_centivolts` | `int` | Input voltage raw value. |
| `output_voltage_centivolts` | `int` | Output voltage raw value. |
| `charging_mode` | `str` | `auto`, `on`, or `off`. |
| `charging_active` | `bool` | Effective charging status. |
| `low_battery_mode` | `str` | `auto`, `on`, or `off`. |
| `low_battery_active` | `bool` | Effective low-battery status. |
| `overload` | `bool` | Overload flag. |
| `need_replacement` | `bool` | Replace-battery flag. |
| `communication_lost` | `bool` | HID CommunicationLost flag. |
| `shutdown_requested` | `bool` | Explicit simulated shutdown request. |
| `shutdown_imminent` | `bool` | Effective shutdown-imminent state. |
| `host_start_delay` | `int` | HID startup delay. |
| `host_shutdown_delay` | `int` | HID shutdown delay. |
| `host_reboot_delay` | `int` | HID reboot delay. |
| `ip` | `str` | Current simulator IP. |

Convenience properties:

```python
status.voltage_volts
status.input_voltage_volts
status.output_voltage_volts
```

return floating-point volts.

### `network_status()`

```python
network = ups.network_status()
```

Returns:

```text
NetworkStatus(ip, gateway, subnet, port)
```

## Safety/control API

### `arm()`

```python
ups.arm()
```

Equivalent to `ARM ON`.

### `disarm()`

```python
ups.disarm()
```

Equivalent to `ARM OFF`; the firmware restores the safe state.

### `reset()`

```python
ups.reset()
```

Restores safe defaults and disarms the simulator.

### `report()`

```python
ups.report()
```

Forces an immediate HID report update.

## Measurement/state API

### AC

```python
ups.set_ac(False)   # simulate mains failure
ups.set_ac(True)    # simulate mains restored
```

### Battery charge

```python
ups.set_battery(75)
```

Valid range: `0..100`.

### UPS load

```python
ups.set_load(65)
```

Valid range: `0..100` percent.

### Runtime

Manual:

```python
ups.set_runtime(1200)
```

Automatic:

```python
ups.set_runtime(None)
```

Manual range: `0..65535` seconds.

### Battery voltage

Use volts:

```python
ups.set_voltage(13.2)
```

or raw centivolts:

```python
ups.set_voltage_centivolts(1320)
```

### Input voltage

```python
ups.set_input_voltage(228.5)
```

or:

```python
ups.set_input_voltage_centivolts(22850)
```

### Output voltage

```python
ups.set_output_voltage(230.1)
```

or:

```python
ups.set_output_voltage_centivolts(23010)
```

Voltage helper range is 0..655.35 V because the underlying HID value is an unsigned 16-bit centivolt field.

### Startup delay

```python
ups.set_start_delay(30)
```

Valid range: `-1..32767` seconds. `-1` represents no pending startup delay.

## Mode/flag API

### Charging

```python
ups.set_charging("auto")
ups.set_charging("on")
ups.set_charging("off")
```

Booleans are also accepted:

```python
ups.set_charging(True)
ups.set_charging(False)
```

### Low battery

```python
ups.set_low_battery("auto")
ups.set_low_battery(True)
ups.set_low_battery(False)
```

### Fault/status flags

```python
ups.set_overload(True)
ups.set_need_replacement(True)
ups.set_communication_lost(True)
ups.set_shutdown_requested(True)
```

Remember that `set_communication_lost(True)` only sets the HID flag. It does not physically interrupt USB and is not equivalent to guaranteed NUT `NOCOMM`.

## Complete automation example

```python
from ups_simulator import UpsSimulator

SIMULATOR = "192.168.1.50"

with UpsSimulator.tcp(SIMULATOR) as ups:
    print("initial:", ups.status())

    with ups.armed_session():
        # Normal loaded UPS
        ups.set_load(55)
        ups.set_input_voltage(230.0)
        ups.set_output_voltage(230.0)

        # Mains failure
        ups.set_ac(False)
        ups.set_battery(70)
        print("on battery:", ups.status())

        # Approach shutdown condition
        ups.set_battery(4)
        ups.set_runtime(300)
        print("low battery:", ups.status())

        # Restore mains before context exits
        ups.set_ac(True)
        ups.set_battery(45)
        ups.set_runtime(None)
        ups.set_low_battery("auto")
        ups.set_charging("auto")
        print("restored:", ups.status())

# RESET has run here.
```

## Exception handling

Public exception hierarchy:

```text
SimulatorError
├── TransportError
├── ProtocolError
└── CommandError
```

Example:

```python
from ups_simulator import (
    UpsSimulator,
    SimulatorError,
    CommandError,
)

try:
    with UpsSimulator.tcp("192.168.1.50") as ups:
        ups.arm()
        ups.set_battery(40)
except CommandError as exc:
    print("firmware rejected command:", exc)
except SimulatorError as exc:
    print("transport/protocol failure:", exc)
```

High-level setters also raise `ValueError` locally for invalid ranges before a command is sent.

## Raw command access

For protocol features not yet wrapped by a high-level method:

```python
payload = ups.raw_command("STATUS?")
```

`raw_command()` removes the leading `OK` and converts `ERR` replies to `CommandError`.

`HELP`/`?` are intentionally rejected by `raw_command()` because they are conceptually multi-line commands in older firmware variants and are not suitable for the single-response abstraction.

## CLI reference

General syntax:

```text
ups-sim (--host HOST | --serial PORT) [global options] COMMAND [arguments]
```

Global options:

```text
--host HOST
--serial PORT
--port 5000
--baud 115200
--timeout 2.0
```

### Read-only

```bash
ups-sim --host 192.168.1.50 ping
ups-sim --host 192.168.1.50 identify
ups-sim --host 192.168.1.50 status
ups-sim --host 192.168.1.50 network
```

`status` and `network` print JSON.

### Safety

```bash
ups-sim --host 192.168.1.50 arm
ups-sim --host 192.168.1.50 disarm
ups-sim --host 192.168.1.50 reset
ups-sim --host 192.168.1.50 report
```

### Measurements

```bash
ups-sim --host 192.168.1.50 ac off
ups-sim --host 192.168.1.50 battery 40
ups-sim --host 192.168.1.50 load 65
ups-sim --host 192.168.1.50 runtime 300
ups-sim --host 192.168.1.50 runtime auto
ups-sim --host 192.168.1.50 voltage 13.2
ups-sim --host 192.168.1.50 input-voltage 228.5
ups-sim --host 192.168.1.50 output-voltage 230.1
ups-sim --host 192.168.1.50 start-delay 30
```

### Modes/faults

```bash
ups-sim --host 192.168.1.50 charging auto
ups-sim --host 192.168.1.50 lowbat auto
ups-sim --host 192.168.1.50 overload on
ups-sim --host 192.168.1.50 replace on
ups-sim --host 192.168.1.50 commlost on
ups-sim --host 192.168.1.50 shutdown on
```

### UART examples

```bash
ups-sim --serial /dev/ttyUSB0 status
ups-sim --serial COM5 ping
```

### Raw CLI command

```bash
ups-sim --host 192.168.1.50 raw STATUS?
```

## Testing the Python package

From repository root after installation:

```bash
python -m unittest discover -s python-driver/tests -v
```

Tests cover:

- status parsing
- network parsing
- command generation
- numeric range validation
- firmware error conversion
- safe reset after exceptions
- TCP handling when both startup greeting lines arrive in one packet

## NUT integration

The Python driver controls the simulator; it does not replace NUT.

A typical automated integration test is:

```text
Python driver -> W5500 -> simulator state
                         |
                         v
                    USB HID reports
                         |
                         v
                       NUT
                         |
                         v
                query/assert with upsc
```

See:

- [`docs/NUT_SETUP.md`](../docs/NUT_SETUP.md)
- [`docs/NUT_VARIABLES.md`](../docs/NUT_VARIABLES.md)

## Security

The firmware TCP protocol has no authentication or encryption.

Use it only on a trusted management/test network or protect it with external network controls. `ARM ON` is a safety guard, not an authentication method.

## Recommended feature placement

Because the Leonardo firmware is at approximately 97% flash, implement future capabilities such as these in Python/Cockpit:

- scenario files
- battery drain/charge simulation over time
- scheduled events
- retries and reconnect logic
- persistent configuration
- authentication
- dashboards
- NUT assertions
- test reports
- Synology/NAS integration workflows

Keep the AVR side focused on USB HID reporting and a small deterministic control protocol.
