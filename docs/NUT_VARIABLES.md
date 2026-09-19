# NUT variables exposed by the simulator

The Ethernet simulator is designed to work with NUT's `usbhid-ups` driver and its upstream `arduino-hid` subdriver for the `HIDPowerDevice` Arduino implementation.

## Core variables

| NUT variable | HID path | Simulator source/control |
|---|---|---|
| `battery.type` | `UPS.PowerSummary.iDeviceChemistry` | fixed `PbAc` |
| `battery.voltage.nominal` | `UPS.PowerSummary.ConfigVoltage` | fixed 13.80 V |
| `battery.voltage` | `UPS.PowerSummary.Voltage` | `VOLTAGE` / `set_voltage()` |
| `battery.runtime` | `UPS.PowerSummary.RunTimeToEmpty` | `RUNTIME` / `set_runtime()` |
| `battery.runtime.low` | `UPS.PowerSummary.RemainingTimeLimit` | fixed 600 s |
| `battery.charge` | `UPS.PowerSummary.RemainingCapacity` | `BATTERY` / `set_battery()` |
| `battery.charge.low` | `UPS.PowerSummary.RemainingCapacityLimit` | fixed 5% |
| `battery.charge.warning` | `UPS.PowerSummary.WarningCapacityLimit` | fixed 10% |
| `ups.load` | `UPS.PowerSummary.PercentLoad` | `LOAD` / `set_load()` |
| `input.voltage` | `UPS.PowerConverter.Input.[1].Voltage` | `INPUTVOLTAGE` / `set_input_voltage()` |
| `output.voltage` | `UPS.PowerConverter.Output.Voltage` | `OUTPUTVOLTAGE` / `set_output_voltage()` |
| `ups.delay.start` | `UPS.PowerSummary.DelayBeforeStartup` | HID RW feature or `STARTDELAY` / `set_start_delay()` |
| `ups.timer.start` | `UPS.PowerSummary.DelayBeforeStartup` | same HID field |
| `ups.delay.shutdown` | `UPS.PowerSummary.DelayBeforeShutdown` | HID RW feature |
| `ups.timer.shutdown` | `UPS.PowerSummary.DelayBeforeShutdown` | same HID field |
| `ups.timer.reboot` | `UPS.PowerSummary.DelayBeforeReboot` | HID feature |

The additional NUT fields are implemented in `HIDPowerDeviceNUT` so the original minimal HID UPS example does not gain the extra descriptor or report IDs.

## Status flags

NUT builds `ups.status` from the simulator's HID `PresentStatus` bits. The simulator can exercise:

- online / on-battery (`OL`, `OB`)
- charging / discharging (`CHRG`, `DISCHRG`)
- low battery (`LB`)
- replace battery (`RB`)
- overload (`OVER`)
- shutdown imminent
- remaining-time-limit expired
- battery present / depleted / fully charged states

## Default values after reset

`RESET` and `ARM OFF` restore the simulator to a safe state. The NUT-facing measurements are reset to:

```text
battery.charge        = 100 %
battery.voltage       = 13.00 V
battery.runtime       = 7200 s
ups.load              = 25 %
input.voltage         = 230.00 V
output.voltage        = 230.00 V
ups.delay.start       = -1
ups.delay.shutdown    = -1
ups.timer.reboot      = -1
```

## Example control sequence

```text
ARM ON
AC OFF
BATTERY 40
LOAD 65
INPUTVOLTAGE 22850
OUTPUTVOLTAGE 23010
STARTDELAY 30
STATUS?
```

Equivalent Python:

```python
from ups_simulator import UpsSimulator

with UpsSimulator.tcp("192.168.1.50") as ups:
    with ups.armed_session():
        ups.set_ac(False)
        ups.set_battery(40)
        ups.set_load(65)
        ups.set_input_voltage(228.5)
        ups.set_output_voltage(230.1)
        ups.set_start_delay(30)
        print(ups.status())
```

## Verify with NUT

After configuring the Arduino with `usbhid-ups`, query the exported variables from the NUT server:

```bash
upsc <ups-name>@localhost
```

For the newly added fields, a normal reset state should include values similar to:

```text
ups.load: 25
input.voltage: 230.0
output.voltage: 230.0
ups.delay.start: -1
ups.timer.start: -1
```

The exact complete `upsc` list depends on the NUT version and what the HID driver accepts from the connected descriptor. Hardware-in-the-loop verification with `upsc` is therefore the final authority for the exported set.

## Units

The simulator control protocol expresses voltage reports in centivolts because the HID descriptor uses the same voltage unit encoding as the existing battery-voltage report:

- `23000` = 230.00 V
- `1325` = 13.25 V

The Python API accepts volts and performs the centivolt conversion automatically.
