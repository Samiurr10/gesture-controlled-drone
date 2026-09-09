# Hand-Controlled Drone Pyrite Simulation Design

This repository captures the architecture plan for a hand-controlled drone
system that can be simulated end to end in pyrite before the physical boards
exist.

The researched baseline uses two PCBs and three processors:

- Hand controller PCB: ESP32-C3-MINI-1-N4X plus IMU.
- Drone PCB: STM32H753VIT6 flight controller plus a second
  ESP32-C3-MINI-1-N4X BLE gateway.

The hand controller reads tilt and gesture data, converts it into an 18-byte
command frame, and sends notifications over BLE. The drone-side ESP32-C3
validates those frames and publishes CRSF receiver frames over a full-duplex
UART. The STM32H753 runs PX4-class flight-control firmware and remains the sole
authority for arming, failsafes, stabilization, and motor commands.

The simulation goal is to run the whole control path:

```text
hand tilt trace -> hand ESP32-C3 -> BLE -> drone ESP32-C3 -> CRSF/UART
-> STM32H753 flight firmware -> ESC/motor sink
```

## Architecture

Start here:

- [System architecture](docs/architecture.md)
- [MCU and architecture research](docs/mcu-architecture-research.md)

## Target System In Simulation

```text
HAND PCB                    AIR                  DRONE PCB
+------------------+    +-----------+    +------------------+    +------------------+
| ESP32-C3         |    | BLE       |    | ESP32-C3        |    | STM32H753        |
| IMU -> gestures  +--->| medium    +--->| validate/map    +--->| PX4 flight stack |
| NimBLE peripheral|    | loss/lag  |    | CRSF gateway    |UART| estimator/control|
+------------------+    +-----------+    +------------------+    +--------+---------+
                                                                          |
                                                                          v
                                                                 +----------------+
                                                                 | ESC/motor sink |
                                                                 +----------------+
```

The two ESP32-C3 firmwares run exactly in Pyrite first. PX4 SITL and H753 HITL
cover vehicle dynamics and real flight hardware while the H753 Pyrite platform
is brought up incrementally.

## What Pyrite Already Has

- ESP32-C3 machine booting mask ROM plus flash image.
- C3 BLE controller through connection and GATT discovery.
- `BleMedium` with pcap tap.
- Lockstep multi-machine `Emulation`.
- STM32 F401/F429 platforms with reusable UART, DMA, GPIO, timer, SPI, and I2C
  models.
- `spi_device` seam for external devices.
- `sim` crate with pyrite-backed binary and scenario loader.

## Workstreams

| # | Workstream | Effort | Gate |
|---|---|---:|---|
| W1 | STM32H7 platform in pyrite | 2-3 weeks | Flight firmware boots and prints on USART; timer PWM toggles. |
| W2 | CRSF UART wire medium | days | Drone C3 sends CRSF, and a scripted receiver peer parses it. |
| W3 | Scripted protocol peer | days | Each radio firmware passes alone against its peer. |
| W4 | C3 I2C or GPSPI2 master model | 1-2 weeks | Unmodified ESP-IDF driver reads `WHO_AM_I`. |
| W5 | IMU device model | about 1 week | IDF IMU driver streams samples; FIFO overflow path is exercised. |
| W6 | BLE impairment knobs | days | Scenario cuts link; drone failsafe is asserted. |
| W7 | Sensor feed plus ESC sink | small | Recorded hand-tilt trace produces expected motor commands. |

W2 and W3 unblock both radio firmware teams early. W1 is no longer allowed to
block PX4 SITL or H753 HITL validation. The original 6-8 person-week estimate
should be treated as provisional until an H753 peripheral inventory is complete.

## Milestones

1. M1 - Hop by hop:
   remote C3 to drone C3 BLE, drone C3 to scripted peer, and H7 boot.
2. M2 - Wire closed:
   drone C3 emits CRSF and PX4 detects both valid input and receiver loss.
3. M3 - Sensor in:
   IMU on remote C3, recorded trace to BLE to drone to H7 command.
4. M4 - Failure modes:
   BLE loss, latency, cut, stale frames, garbage injection, and CI failsafe
   assertions.
5. M5 - Loop out:
   ESC sink and measured hand-to-motor latency budget.

## Open Decisions

- Exact hand and flight IMU selections and bus allocation.
- PX4 board port versus a smaller custom flight stack.
- BLE demonstrator-only operating range and the threshold for moving to
  ExpressLRS.
