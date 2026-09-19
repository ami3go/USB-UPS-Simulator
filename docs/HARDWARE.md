# Hardware guide

## Recommended platform

The supported reference hardware is:

- **Arduino Leonardo / ATmega32U4** for native USB HID
- **W5500 Ethernet shield** for the control network

The Leonardo is important because its native USB peripheral can present the board as a USB HID Power Device while the SPI-connected W5500 remains an independent management path.

## W5500 shield compatibility

A common shield sold as an UNO R3 W5500 Ethernet shield is suitable **when the 2x3 ICSP socket is populated and physically mates with the Leonardo ICSP header**.

On Leonardo, hardware SPI is available at the ICSP header. A shield that expects SPI only on UNO D11/D12/D13 is not directly compatible.

## Pin allocation

| Function | Leonardo connection | Notes |
|---|---|---|
| W5500 MOSI/MISO/SCK | ICSP header | Hardware SPI bus. |
| W5500 CS | D10 | Reserved for Ethernet. Do not reuse it. |
| microSD CS | D4 | Firmware drives it HIGH so the unused SD interface remains deselected. |
| UART RX/TX | D0/D1 (`Serial1`) | Optional fallback control channel at 115200 baud. |
| USB HID UPS | Native USB connector | Goes to the NUT/system-under-test host. |
| Status heartbeat | `LED_BUILTIN` | Toggles approximately once per second. |

Do not insert a microSD card during initial commissioning.

## Physical arrangement

```text
               +-----------------------+
Control LAN <--| RJ45 / W5500 shield   |
               +-----------+-----------+
                           SPI
                            |
               +------------+----------+
               | Arduino Leonardo      |
               | ATmega32U4            |
               +------+----------+-----+
                      |          |
                   USB HID     Serial1
                      |          |
                      v          +---- optional USB-UART adapter
                NUT host
```

## USB role

The USB link is not used as the normal simulator control channel. It exists primarily so the target machine sees a USB HID UPS.

This separation is intentional:

- USB = device-under-test interface
- Ethernet = primary test/control interface
- UART = recovery/bench control interface

## UART wiring

Leonardo `Serial1` is on hardware pins D0/D1.

Typical USB-UART connection:

| Leonardo | USB-UART adapter |
|---|---|
| TX / D1 | RX |
| RX / D0 | TX |
| GND | GND |

Use a logic-level-compatible adapter. Do not connect an RS-232 voltage-level interface directly to the Leonardo UART pins.

UART settings:

```text
115200 baud
8 data bits
no parity
1 stop bit
```

The UART uses the same line-oriented command protocol as Ethernet.

## Power options

### Normal development

USB power from the test host is sufficient for ordinary flashing and functional testing if the shield/board combination is within the available USB power budget.

### Full shutdown tests

For shutdown/recovery testing, USB-only power is not sufficient because the simulator would lose power when the host powers its USB ports down.

Use independent Leonardo power so that:

1. NUT observes the simulated outage over USB.
2. NUT shuts down the test host.
3. Leonardo + W5500 remain powered.
4. The external test controller can still reach TCP port 5000.
5. The controller can simulate restored mains and charging.

Follow the input-voltage requirements of the exact Leonardo or clone. For an official-style Leonardo, the commonly recommended barrel/VIN range is 7-12 V.

## Grounding and multiple power sources

The Leonardo power-selection circuitry is designed for normal USB plus supported external-power operation, but clone boards can differ. Verify the schematic/specification of your exact board before applying external power and USB simultaneously.

Do not inject an external 5 V supply into arbitrary pins unless the board documentation explicitly supports that arrangement.

## Ethernet addressing

Default behavior:

1. DHCP is attempted.
2. If DHCP fails, static fallback is used:

```text
IP:      169.254.42.42
Subnet:  255.255.0.0
TCP:     5000
```

Default locally administered MAC:

```text
02:55:50:53:00:01
```

If several simulators are placed on one LAN, modify the final MAC bytes so every board has a unique MAC address.

## Safety considerations

This project simulates conditions that can cause real machines to shut down. Keep these principles:

- simulator boots disarmed
- do not expose TCP/5000 to an untrusted network
- use `RESET` after tests
- use a dedicated test NUT configuration before connecting production clients
- verify shutdown actions with a disposable/test host before involving NAS or production systems

`ARM ON` is only an accidental-change guard. It is **not authentication**.

## Flash/RAM limits

Current reference build:

```text
Flash: 28070 / 28672 bytes (97%)
RAM:    1296 / 2560 bytes (50%)
```

Avoid expanding the AVR firmware with web servers, TLS, scenario engines, persistent logs, or complex configuration. Put such features into the Python/Cockpit side.
