# Simulator control protocol

The same ASCII line protocol is available over:

- W5500 TCP port **5000**
- Leonardo hardware UART `Serial1` at **115200 baud**

Ethernet is the recommended control channel. UART exists for bench testing and recovery.

## Framing

- ASCII text
- one command per line
- terminate commands with LF (`\n`)
- CRLF is accepted
- commands are case-insensitive
- maximum firmware input line buffer is 96 bytes
- one TCP control client is active at a time
- a newly accepted TCP client replaces the previous client, which recovers from stale/half-open sessions

A TCP connection starts with two lines:

```text
OK NutUPS HID Simulator v2
OK DISARMED
```

If the simulator is already armed when a new controller connects, the second line is:

```text
OK ARMED
```

The Python driver does not depend on greeting timing. It sends `PING` while connecting and consumes all lines up to `OK PONG`, so it also remains compatible with older firmware that emitted the greeting only after receiving the first command.

## Response format

Success is returned as either:

```text
OK
```

or:

```text
OK <payload>
```

Errors start with `ERR`, for example:

```text
ERR disarmed
ERR range
ERR mode
ERR command
ERR line
```

The firmware intentionally keeps error strings short to fit the Leonardo flash limit. Client software should treat the `ERR` prefix as the authoritative failure indicator.

## Safety model and arming lease

After boot the simulator is disarmed. Read-only commands work immediately, but state-changing commands are rejected until it is armed.

The preferred form is:

```text
ARM ON
```

`ARM ON` uses the firmware default **120-second lease**. Every command received while armed refreshes the lease timer. If no command arrives before the lease expires, the firmware automatically restores the safe online state and disarms itself.

An explicit lease may be selected:

```text
ARM ON 300
```

Accepted lease range is `0..3600` seconds. `0` explicitly disables automatic lease expiry and should only be used for controlled bench work where an indefinite armed state is intentional.

To restore a safe state immediately:

```text
RESET
```

or:

```text
ARM OFF
```

Both restore safe defaults and leave the simulator disarmed.

The lease is enforced by the firmware, so it still works if the Python controller is killed, loses power, or loses the network connection.

## Read-only commands

| Command | Response / purpose |
|---|---|
| `PING` | Returns `OK PONG`; while armed it also refreshes the arming lease. |
| `IDENT?` | Returns simulator identity/version. |
| `STATUS?` | Returns current state as space-separated `key=value` fields. `STATUS` is also accepted. |
| `NETWORK?` | Returns local IP, gateway, subnet, and TCP port. |
| `HELP` | Returns a compact pointer to documentation. `?` is also accepted. |
| `REPORT` | Forces an immediate USB HID report refresh. Allowed while disarmed. |

## Safety/control commands

| Command | Range | Meaning |
|---|---:|---|
| `ARM ON` | default 120 s | Permit state-changing commands with the default lease. |
| `ARM ON n` | `0..3600` seconds | Arm with an explicit lease; `0` disables lease expiry. |
| `ARM OFF` | - | Reset to safe state and disarm. |
| `RESET` | - | Reset to safe state and disarm. |

## Simulated state commands

All commands below require the simulator to be armed.

| Command | Value | NUT/HID effect |
|---|---|---|
| `AC ON\|OFF` | boolean | Controls AC-present / online versus on-battery state. |
| `BATTERY n` | `0..100` | Battery charge percentage / `battery.charge`. |
| `RUNTIME n` | `0..65535` seconds | Manual `battery.runtime`. |
| `RUNTIME AUTO` | - | Runtime scales from full runtime according to battery percentage. |
| `VOLTAGE n` | `0..65535` centivolts | Battery voltage / `battery.voltage`. |
| `LOAD n` | `0..100` percent | UPS load / `ups.load`. |
| `INPUTVOLTAGE n` | `0..65535` centivolts | AC input voltage / `input.voltage`. |
| `OUTPUTVOLTAGE n` | `0..65535` centivolts | UPS output voltage / `output.voltage`. |
| `STARTDELAY n` | `-1..32767` seconds | `ups.delay.start` / `ups.timer.start`. `-1` means no pending startup timer. |
| `CHARGING AUTO\|ON\|OFF` | mode | Charging status override. |
| `LOWBAT AUTO\|ON\|OFF` | mode | Low-battery status override. |
| `OVERLOAD ON\|OFF` | boolean | Overload status. |
| `REPLACE ON\|OFF` | boolean | Replace-battery status. |
| `COMMLOST ON\|OFF` | boolean | Sets the HID `CommunicationLost` status bit. |
| `SHUTDOWN ON\|OFF` | boolean | Simulated shutdown-request status. |

### Voltage units

The wire protocol uses **centivolts**:

```text
1300  = 13.00 V
22850 = 228.50 V
23010 = 230.10 V
```

The Python API accepts volts and performs this conversion automatically.

## Automatic behaviors

### Runtime AUTO

With:

```text
RUNTIME AUTO
```

runtime is calculated proportionally from the configured full runtime and current battery percentage.

### Charging AUTO

With:

```text
CHARGING AUTO
```

charging is active when AC is present and battery charge is below full capacity.

### LOWBAT AUTO

With:

```text
LOWBAT AUTO
```

low battery becomes active when battery charge is at or below the configured remaining-capacity limit. The current default is 5%.

### Remaining-time limit

The current remaining-time threshold is 600 seconds. While discharging, runtime at or below this threshold asserts the remaining-time-limit-expired condition and contributes to shutdown-imminent behavior.

### Arm lease expiry

If the simulator is armed with a non-zero lease and receives no command before that lease expires, it performs the equivalent of a safe reset:

- disarms
- AC present
- battery 100%
- runtime automatic
- clears overload, replacement, communication-loss and shutdown flags
- restores default load and voltages

This is intentionally a firmware-level fail-safe rather than a Python-only cleanup mechanism.

## `STATUS?` fields

Example:

```text
OK armed=1 ac=0 battery=40 runtime=2880 runtime_mode=auto voltage_cv=1300 load=65 input_voltage_cv=22850 output_voltage_cv=23010 charging_mode=auto charging_active=0 lowbat_mode=auto lowbat_active=0 overload=0 replace=0 commlost=0 shutdown=0 shutdown_imminent=0 host_start_delay=30 host_shutdown_delay=-1 host_reboot_delay=-1 ip=192.168.1.50
```

Field reference:

| Field | Meaning |
|---|---|
| `armed` | `1` when state changes are enabled. |
| `ac` | `1` when simulated AC is present. |
| `battery` | Battery percentage. |
| `runtime` | Runtime-to-empty in seconds. |
| `runtime_mode` | `auto` or `manual`. |
| `voltage_cv` | Battery voltage in centivolts. |
| `load` | UPS load percent. |
| `input_voltage_cv` | Input voltage in centivolts. |
| `output_voltage_cv` | Output voltage in centivolts. |
| `charging_mode` | `auto`, `on`, or `off`. |
| `charging_active` | Computed/forced charging state. |
| `lowbat_mode` | `auto`, `on`, or `off`. |
| `lowbat_active` | Computed/forced low-battery state. |
| `overload` | Overload flag. |
| `replace` | Replace-battery flag. |
| `commlost` | HID communication-lost flag. |
| `shutdown` | Explicit simulator shutdown-request flag. |
| `shutdown_imminent` | Computed shutdown-imminent condition. |
| `host_start_delay` | HID startup delay value. |
| `host_shutdown_delay` | HID shutdown delay value, potentially written by the USB host/NUT. |
| `host_reboot_delay` | HID reboot delay value. |
| `ip` | Current simulator IP address. |

## Safe test recipes

### Normal online

```text
RESET
STATUS?
```

Default measurements after reset include:

```text
battery=100
voltage_cv=1300
load=25
input_voltage_cv=23000
output_voltage_cv=23000
host_start_delay=-1
```

### On battery

```text
ARM ON
AC OFF
BATTERY 70
STATUS?
```

### Low battery / short runtime

```text
ARM ON 120
AC OFF
BATTERY 4
RUNTIME 300
STATUS?
```

### Load and voltage test

```text
ARM ON
LOAD 80
INPUTVOLTAGE 21500
OUTPUTVOLTAGE 22950
STATUS?
```

### Overload

```text
ARM ON
OVERLOAD ON
STATUS?
```

### Restore mains

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

### End any test

```text
RESET
```

## Important note about `COMMLOST`

`COMMLOST ON` sets the HID status flag named `CommunicationLost`. It does **not** electrically detach USB or guarantee that NUT will enter its driver-level `NOCOMM` state. Testing actual USB transport loss requires a separate mechanism.

## Security

TCP/5000 has no authentication or encryption. `ARM ON` and the arming lease are **safety controls, not access controls**.

Use one of these deployment patterns for the control interface:

- a direct point-to-point Ethernet connection to the test controller
- a dedicated test/management VLAN with firewall rules limiting TCP/5000 to authorized controller hosts
- another physically or logically isolated trusted lab network

Authentication implemented only in Python or Cockpit cannot protect the raw Arduino TCP port because another host could bypass that software and connect directly to TCP/5000.
