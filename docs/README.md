# USB UPS Simulator documentation

This directory contains the complete user and developer documentation for the Arduino Leonardo + W5500 USB HID UPS simulator.

## Start here

| Guide | Purpose |
|---|---|
| [Quick start and flashing](FLASHING.md) | Assemble the hardware, install Arduino tools, build, flash, and run the first simulator test. |
| [Hardware self-test](SELF_TEST.md) | Detect the USB HID UPS and Ethernet simulator from one PC, then verify the complete v2 command set safely. |
| [Firmware behavior simulator](FIRMWARE_SIMULATOR.md) | Run the v2 command parser/state model without hardware and verify exact responses, state transitions, and arming-lease behavior. |
| [Hardware guide](HARDWARE.md) | Leonardo/W5500 compatibility, pin usage, USB/UART/Ethernet wiring, and power recommendations. |
| [Control protocol](CONTROL_PROTOCOL.md) | Complete TCP/UART command reference, status fields, units, responses, and test sequences. |
| [Python driver manual](../python-driver/README.md) | Install and use the `ups_simulator` Python API and `ups-sim` CLI. |
| [NUT setup](NUT_SETUP.md) | Connect the simulated USB HID UPS to Network UPS Tools and verify it with `upsc`. |
| [NUT variable map](NUT_VARIABLES.md) | HID paths and NUT variables exported by the simulator. |
| [Firmware programming guide](PROGRAMMING_GUIDE.md) | Architecture, source tree, HID extension, state model, safe development rules, and how to add features. |
| [Troubleshooting](TROUBLESHOOTING.md) | Upload, USB HID, Ethernet, NUT, UART, and Python-driver diagnostics. |
| [Ethernet simulator design](ETHERNET_SIMULATOR.md) | Design rationale and operational details for the W5500-controlled simulator. |

## Architecture

```text
                  management / test network
                          TCP 5000
                             |
                             v
                    +----------------+
                    | W5500 Ethernet |
                    +-------+--------+
                            |
                         SPI/ICSP
                            |
                    +-------+--------+
                    | Arduino        |
                    | Leonardo       |
                    +---+--------+---+
                        |        |
                 USB HID UPS   Serial1
                        |       115200
                        v
                 NUT host under test
```

The USB connection is the simulated UPS interface. Ethernet and UART are control interfaces used to inject conditions such as AC failure, low battery, overload, load percentage, and input/output voltage.

## Safety principle

The simulator boots **disarmed** and in a safe online state. Commands that modify the simulated UPS require `ARM ON`. `RESET` and `ARM OFF` restore the safe state. The firmware also applies a default arming lease so a lost controller cannot leave injected fault state armed indefinitely.

This matters because a low-battery or shutdown-imminent condition can cause a real NUT installation to shut down physical machines. The hardware self-test therefore refuses its OB/LB/shutdown checks when it detects a live `upsmon`, unless the operator explicitly overrides that guard.

## Current Leonardo resource usage

The pinned reference build uses:

- flash: **27,854 / 28,672 bytes (97%)**
- static RAM: **1,321 / 2,560 bytes (51%)**

The AVR firmware should therefore be treated as effectively feature-frozen. New automation, scenarios, authentication, web UI, logging, orchestration, and test tooling should normally be implemented in the Python/Cockpit side rather than added to the Leonardo image.
