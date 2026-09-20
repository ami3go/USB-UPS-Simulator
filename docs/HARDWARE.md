# Hardware guide

## Recommended platform

The supported reference hardware is:

- **Arduino Leonardo / ATmega32U4** for native USB HID
- **W5500 Ethernet shield** for the control network

The Leonardo's native USB peripheral can present the board as a USB HID Power Device while the SPI-connected W5500 remains a separate management path.

## W5500 shield compatibility

A common UNO R3 W5500 Ethernet shield is suitable **when the 2x3 ICSP socket is populated and physically mates with the Leonardo ICSP header**.

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

The USB link is the UPS-facing interface. Ethernet is the primary simulator-control interface and UART is the recovery/bench interface.

## UART wiring

Leonardo `Serial1` is on hardware pins D0/D1.

| Leonardo | USB-UART adapter |
|---|---|
| TX / D1 | RX |
| RX / D0 | TX |
| GND | GND |

Use a logic-level-compatible adapter, not RS-232 voltage levels.

UART settings are `115200 8N1` and use the same line protocol as Ethernet.

## Power options

### Normal development

USB power from the test host is sufficient for ordinary flashing and functional testing if the shield/board combination stays within the USB power budget.

### Full shutdown tests

For shutdown/recovery testing, independently power the Leonardo so the controller remains alive when the NUT host powers down. This allows the test controller to simulate restored mains after the host is off.

Follow the input-voltage requirements of the exact Leonardo or clone. For an official-style Leonardo, the commonly recommended barrel/VIN range is 7-12 V.

## Grounding and multiple power sources

The Leonardo power-selection circuitry is designed for normal USB plus supported external-power operation, but clone boards can differ. Verify the schematic/specification of your exact board before applying external power and USB simultaneously.

Do not inject an external 5 V supply into arbitrary pins unless the board documentation explicitly supports it.

## Ethernet addressing

The firmware attempts DHCP with bounded startup time. If DHCP fails, it uses:

```text
IP:      169.254.42.42
Subnet:  255.255.0.0
TCP:     5000
```

Default locally administered MAC:

```text
02:55:50:53:00:01
```

If several simulators share a LAN, modify the final MAC bytes so each board is unique. A future board-ID mechanism is preferable to source edits but is not implemented yet.

DHCP lease maintenance is skipped while the simulator is armed so a missing DHCP server cannot stall an active fault-injection sequence.

## Safety considerations

This project can generate conditions that cause real machines to shut down.

- simulator boots disarmed and computes a valid safe HID status before Ethernet initialization
- `ARM ON` defaults to a 120-second firmware-enforced lease
- commands received while armed refresh the lease
- `ARM ON <seconds>` accepts `0..3600`; `0` disables expiry deliberately
- lease expiry restores the safe state even if the controller process dies
- newest TCP connection replaces a stale existing connection
- `RESET` and `ARM OFF` restore the safe state immediately
- TCP/5000 has no authentication; isolate it with a direct link, test VLAN or firewall rules
- validate shutdown behavior on a disposable/test host before involving NAS or production systems

The ARM mechanism is a safety control, not authentication.

## Flash/RAM limits

Pinned CI reference build:

```text
Original UPS:
Flash: 10176 / 28672 bytes
RAM:     330 / 2560 bytes

Ethernet/NUT simulator:
Flash: 27854 / 28672 bytes (97%)
RAM:    1321 / 2560 bytes (51%)
```

The simulator has 818 bytes of flash headroom. CI rejects builds above 28,160 bytes, preserving at least 512 bytes for future reliability fixes.

Avoid expanding AVR firmware with web servers, TLS, scenario engines, persistent logs, or complex configuration. Put such features into the Python/Cockpit side.

## Hardware validation still required

Compilation and host-side tests do not replace physical validation. Before a release, verify on the real Leonardo + W5500 combination:

- greeting appears immediately on TCP connect
- no-DHCP fallback becomes reachable quickly at `169.254.42.42`
- command response remains responsive while DHCP is absent
- NUT sees no transient OB/RB state during simulator reset
- NUT 2.8.5+ exposes the extended measurements
- on Windows, the HID descriptor appears as one UPS/battery device rather than duplicate top-level collections
