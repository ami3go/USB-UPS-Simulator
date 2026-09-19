# NutUPS simulator Python driver

Python control library and CLI for the Arduino Ethernet/UART UPS simulator in this repository.

The driver talks to the simulator control interface only. The system under test continues to see the Arduino as a USB HID UPS.

## Install

From this repository:

```bash
python -m pip install -e ./python-driver
```

For UART support, also install the optional serial dependency:

```bash
python -m pip install -e './python-driver[serial]'
```

## TCP/W5500 example

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    print(ups.identify())
    print(ups.status())

    with ups.armed_session():
        ups.set_ac(False)
        ups.set_battery(40)
        ups.set_load(65)
        ups.set_input_voltage(228.5)
        ups.set_output_voltage(230.1)
        ups.set_runtime(300)
        print(ups.status())

# armed_session() issues RESET on exit, including when the test raises.
```

## UART example

The firmware control UART is `Serial1` at 115200 baud. Connect through a suitable USB-UART adapter and use:

```python
from ups_simulator import UpsSimulator

with UpsSimulator.serial("/dev/ttyUSB0") as ups:
    print(ups.ping())
    print(ups.status())
```

## Status objects

`status()` returns a `SimulatorStatus` dataclass with parsed fields including:

- armed state
- AC present
- battery percentage
- runtime and runtime mode
- battery voltage
- load percentage (`ups.load`)
- input voltage (`input.voltage`)
- output voltage (`output.voltage`)
- charging state/mode
- low-battery state/mode
- overload
- replacement-battery flag
- communication-loss flag
- shutdown request/imminent state
- host start/shutdown/reboot delays
- simulator IP address

Voltage fields are also exposed as convenience properties in volts.

`network_status()` returns a `NetworkStatus` dataclass.

## Control methods

```python
ups.arm()
ups.disarm()
ups.reset()
ups.set_ac(True)
ups.set_battery(75)
ups.set_load(50)
ups.set_runtime(1200)
ups.set_runtime(None)                  # AUTO
ups.set_voltage(13.2)                  # battery volts
ups.set_input_voltage(230.0)           # AC input volts
ups.set_output_voltage(229.5)          # UPS output volts
ups.set_start_delay(30)                # -1 disables pending startup
ups.set_charging("auto")
ups.set_low_battery("auto")
ups.set_overload(True)
ups.set_need_replacement(True)
ups.set_communication_lost(True)
ups.set_shutdown_requested(True)
ups.report()
```

The high-level API validates numeric ranges before sending commands. Firmware `ERR` responses raise `CommandError`.

## Safe test pattern

For tests that can trigger real NUT shutdown actions, prefer `armed_session()`:

```python
with UpsSimulator.tcp("192.168.1.50") as ups:
    with ups.armed_session():
        ups.set_ac(False)
        ups.set_battery(4)
        ups.set_runtime(300)
        # assertions / NUT integration checks here
```

The context manager sends `RESET` in `finally`, returning the simulator to its disarmed AC-present 100% state even if the body raises an exception.

## CLI

After installation the `ups-sim` command is available.

```bash
ups-sim --host 192.168.1.50 status
ups-sim --host 192.168.1.50 arm
ups-sim --host 192.168.1.50 ac off
ups-sim --host 192.168.1.50 battery 40
ups-sim --host 192.168.1.50 load 65
ups-sim --host 192.168.1.50 input-voltage 228.5
ups-sim --host 192.168.1.50 output-voltage 230.1
ups-sim --host 192.168.1.50 start-delay 30
ups-sim --host 192.168.1.50 runtime 300
ups-sim --host 192.168.1.50 status
ups-sim --host 192.168.1.50 reset
```

UART examples:

```bash
ups-sim --serial /dev/ttyUSB0 status
ups-sim --serial COM5 ping
```

## NUT mapping

See [`docs/NUT_VARIABLES.md`](../docs/NUT_VARIABLES.md) for the HID-to-NUT mapping and `upsc` verification procedure.

## Exceptions

- `TransportError` - TCP/UART connection or I/O failure
- `CommandError` - simulator returned `ERR ...`
- `ProtocolError` - malformed or unexpected simulator response

## Security

The W5500 firmware control protocol has no authentication or encryption. Use it only on a trusted management/test network. `ARM ON` prevents accidental state changes but is not an access-control mechanism.
