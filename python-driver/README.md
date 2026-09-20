# NutUPS simulator Python driver user manual

`nutups-simulator-control` is the host-side API and CLI for the Arduino Leonardo + W5500 USB HID UPS simulator.

The driver controls only the simulator's TCP/UART management interface. The system under test continues to see the Leonardo as a USB HID UPS.

## Requirements

- Python 3.9+
- TCP access to W5500 port 5000, or a UART adapter connected to Leonardo `Serial1`
- `pyserial` only for UART use
- firmware identity `NutUPS HID Simulator v2`

CI covers Python 3.9 and 3.13.

## Install

From repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ./python-driver
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .\python-driver
```

UART extra:

```bash
python -m pip install -e './python-driver[serial]'
```

Hardware self-test extra:

```bash
python -m pip install -e './python-driver[selftest]'
```

The install provides:

```python
from ups_simulator import UpsSimulator
```

and:

```bash
ups-sim
ups-sim-selftest
```

## Hardware self-test

When the Leonardo USB cable is connected to the same PC that can reach the W5500 on the LAN, run:

```bash
ups-sim-selftest
```

The self-test:

- detects the USB HID Power Device and the NUT extension report IDs when the OS exposes the report descriptor
- discovers `NutUPS HID Simulator v2` on local TCP/5000
- verifies the disarmed mutation guard
- exercises every primary v2 command with `STATUS?` read-back checks
- always attempts a final `RESET`
- refuses OB/LB/shutdown-state tests if a live `upsmon` is detected, unless explicitly overridden

If the IP is known, skip LAN discovery:

```bash
ups-sim-selftest --host 192.168.1.50
```

See [`docs/SELF_TEST.md`](../docs/SELF_TEST.md) for the complete guide and safety behavior.

## Connection behavior

### TCP

```python
ups = UpsSimulator.tcp("192.168.1.50", port=5000, timeout=2.0)
```

On connection the transport sends `PING` and reads until `OK PONG`. Any greeting/banner lines before that response are consumed and recorded. This works with both:

- older firmware that emitted its greeting only after the first command arrived
- hardened firmware that greets immediately on TCP accept

`UpsSimulator.connect()` then sends `IDENT?` and requires exactly:

```text
NutUPS HID Simulator v2
```

A different firmware protocol version raises `ProtocolError` immediately rather than failing later while parsing `STATUS?`.

### UART

```python
ups = UpsSimulator.serial("/dev/ttyUSB0", baudrate=115200, timeout=2.0)
```

Windows:

```python
ups = UpsSimulator.serial("COM5")
```

UART uses the same `PING` synchronization so a late `NutUPS ready` boot banner cannot be mistaken for a command response.

## Basic read-only use

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    print(ups.ping())
    print(ups.identify())
    print(ups.network_status())
    print(ups.status())
```

`status()` returns a frozen `SimulatorStatus` dataclass containing:

- armed state
- AC present
- battery percentage
- runtime and runtime mode
- battery/input/output voltage
- load percentage
- charging/low-battery modes and effective states
- overload/replacement/communication-loss/shutdown flags
- start/shutdown/reboot delay values
- current IP address

Convenience properties convert centivolts to volts:

```python
status.voltage_volts
status.input_voltage_volts
status.output_voltage_volts
```

`network_status()` returns `NetworkStatus(ip, gateway, subnet, port)`.

## Arming and the firmware lease

State-changing commands require the simulator to be armed.

```python
ups.arm()
```

sends `ARM ON`, which uses the firmware default **120-second lease**.

Use an explicit lease when needed:

```python
ups.arm(lease_seconds=300)
```

Valid explicit range is `0..3600` seconds. `0` intentionally disables lease expiry.

While the simulator is armed, every command received by the firmware refreshes the lease. If a non-zero lease expires, the firmware automatically restores the safe online state even if the Python process was killed or the network disappeared.

### Recommended safe context

```python
with UpsSimulator.tcp("192.168.1.50") as ups:
    with ups.armed_session(lease_seconds=120):
        ups.set_ac(False)
        ups.set_battery(4)
        ups.set_runtime(300)
        print(ups.status())
```

`armed_session()` attempts `RESET` on exit. If the test body raises and cleanup also fails, the original test exception is preserved and the cleanup failure is emitted as a `RuntimeWarning` instead of masking the original failure.

To use `ARM OFF` rather than `RESET` on normal exit:

```python
with ups.armed_session(reset_on_exit=False):
    ...
```

The firmware lease remains the final fail-safe for process death, `kill -9`, or network loss.

## Control API

```python
ups.arm()
ups.arm(lease_seconds=300)
ups.disarm()
ups.reset()
ups.report()                       # allowed while disarmed

ups.set_ac(False)
ups.set_battery(75)                # 0..100
ups.set_load(50)                   # 0..100
ups.set_runtime(1200)              # 0..65535 seconds
ups.set_runtime(None)              # AUTO

ups.set_voltage(13.2)
ups.set_voltage_centivolts(1320)
ups.set_input_voltage(230.0)
ups.set_output_voltage(229.5)

ups.set_start_delay(30)            # -1..32767
ups.set_charging("auto")           # auto/on/off or bool
ups.set_low_battery("auto")
ups.set_overload(True)
ups.set_need_replacement(True)
ups.set_communication_lost(True)
ups.set_shutdown_requested(True)
```

Voltage helper methods accept volts; raw `*_centivolts()` methods accept `0..65535`, corresponding to 0..655.35 V.

`set_communication_lost(True)` only sets the HID `CommunicationLost` status bit. It does not physically interrupt USB and is not guaranteed to produce NUT driver-level `NOCOMM`.

## Complete example

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    print("initial:", ups.status())

    with ups.armed_session(lease_seconds=120):
        ups.set_load(55)
        ups.set_input_voltage(230.0)
        ups.set_output_voltage(230.0)

        ups.set_ac(False)
        ups.set_battery(70)
        print("on battery:", ups.status())

        ups.set_battery(4)
        ups.set_runtime(300)
        print("low battery:", ups.status())

        ups.set_ac(True)
        ups.set_battery(45)
        ups.set_runtime(None)
        ups.set_low_battery("auto")
        ups.set_charging("auto")
        print("restored:", ups.status())
```

## Exception hierarchy

```text
SimulatorError
├── TransportError
├── ProtocolError
└── CommandError
```

- `TransportError`: TCP/UART connection or I/O failure
- `ProtocolError`: framing, malformed response, missing fields, or unsupported firmware identity
- `CommandError`: firmware returned `ERR ...`
- `ValueError`: local invalid API argument

Example:

```python
from ups_simulator import UpsSimulator, SimulatorError, CommandError

try:
    with UpsSimulator.tcp("192.168.1.50") as ups:
        with ups.armed_session():
            ups.set_battery(4)
except CommandError as exc:
    print("firmware rejected command:", exc)
except SimulatorError as exc:
    print("transport/protocol failure:", exc)
```

## CLI

General form:

```text
ups-sim (--host HOST | --serial PORT) [global options] COMMAND [arguments]
```

Connection options:

```text
--host HOST
--serial PORT
--port 5000
--baud 115200
--timeout 2.0
```

Read-only examples:

```bash
ups-sim --host 192.168.1.50 ping
ups-sim --host 192.168.1.50 identify
ups-sim --host 192.168.1.50 status
ups-sim --host 192.168.1.50 network
```

`ping` returns a non-zero exit code if the response is not `PONG`. `status` and `network` print JSON.

Safety:

```bash
ups-sim --host 192.168.1.50 arm
ups-sim --host 192.168.1.50 arm --lease 300
ups-sim --host 192.168.1.50 arm --lease 0
ups-sim --host 192.168.1.50 disarm
ups-sim --host 192.168.1.50 reset
ups-sim --host 192.168.1.50 report
```

Measurements and faults:

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
ups-sim --host 192.168.1.50 charging auto
ups-sim --host 192.168.1.50 lowbat auto
ups-sim --host 192.168.1.50 overload on
ups-sim --host 192.168.1.50 replace on
ups-sim --host 192.168.1.50 commlost on
ups-sim --host 192.168.1.50 shutdown on
```

UART:

```bash
ups-sim --serial /dev/ttyUSB0 status
ups-sim --serial COM5 ping
```

Raw single-line command:

```bash
ups-sim --host 192.168.1.50 raw STATUS?
```

## Tests

```bash
python -m unittest discover -s python-driver/tests -v
```

Tests cover:

- status/network parsing
- command generation and argument validation
- firmware `ERR` conversion
- v2 firmware identity check
- TCP greeting sent immediately and delayed-until-first-command
- UART late boot banner synchronization
- CLI ping failure exit status
- cleanup failure without masking the original test exception
- safe reset after exception
- hardware self-test HID descriptor helpers and bounded network discovery logic

The workflow runs for Python 3.9 and 3.13 and is also triggered by firmware/HID/protocol changes so host and firmware behavior cannot silently drift apart.

## Security

TCP/5000 has no authentication or encryption. The ARM gate and lease are safety mechanisms, not authentication.

Use a direct link, dedicated management/test VLAN, or firewall rules to restrict raw TCP/5000 access. Authentication only in the Python/Cockpit layer cannot prevent another reachable host from bypassing that layer and connecting directly to the Arduino.

## NUT integration

The Python driver controls the simulator; it does not replace NUT. For NUT setup and variable mappings see:

- [`docs/NUT_SETUP.md`](../docs/NUT_SETUP.md)
- [`docs/NUT_VARIABLES.md`](../docs/NUT_VARIABLES.md)

`ups.load`, `input.voltage` and `output.voltage` require NUT 2.8.5+.
