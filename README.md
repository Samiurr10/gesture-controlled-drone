# Hand-Controlled Drone Pyrite Simulation Design

This repository captures the architecture plan for a hand-controlled drone
system that can be simulated end to end in pyrite before the physical boards
exist.

The target system uses two PCBs:

- Hand controller PCB: ESP32-C3 plus IMU.
- Drone PCB: STM32H7 flight controller plus a second ESP32-C3 BLE radio.

The hand controller reads tilt and gesture data, converts that into command
frames, and sends those frames over BLE. The drone-side ESP32-C3 bridges BLE to
the STM32H7 over a serial link. The STM32H7 runs the flight-control firmware and
produces motor commands.

The simulation goal is to run the whole control path:

```text
hand tilt trace -> hand ESP32-C3 -> BLE -> drone ESP32-C3 -> serial wire
-> STM32H7 flight firmware -> ESC/motor sink
```

## Architecture

Start here:

- [System architecture](docs/architecture.md)

## Target System In Simulation

```text
HAND PCB                              AIR                              DRONE PCB
+-----------------------+                                      +------------------------------------------+
| ESP32-C3 remote       |                                      | ESP32-C3 drone radio     STM32H7 FC      |
|                       |                                      |                                          |
| +-------------------+ |      +----------------------+        | +-------------------+   +--------------+ |
| | IMU               | |      | BleMedium            |        | | NimBLE central    |   | flight fw    | |
| | I2C or GPSPI2     | |      | adv/connect/GATT     |        | | or peripheral    |   | Zephyr/bare  | |
| +---------+---------+ |      | L2CAP                |        | +---------+---------+   | Cortex-M7    | |
|           |           |      | impairments:         |        |           |             | USART/DMA    | |
|           v           |      | loss, range/RSSI,    |        |           | UART/SPI    | TIM/PWM      | |
| +-------------------+ |      | interval, latency    |        | +---------v---------+   +------+-------+ |
| | NimBLE peripheral | +----->| pcap tap             +------->| | bridge firmware   +--------->       | |
| | gesture -> cmd    | |      +----------------------+        | | BLE <-> serial    | cmd frames in, | |
| +-------------------+ |                                      | +-------------------+ telemetry out  | |
+-----------------------+                                      +--------------------------+--------------+
          ^                                                                                 |
          | scenario-driven IMU traces                                                       v
 +--------+---------+                                                            +----------------+
 | sensor feed      |                                                            | ESC/motor sink |
 +------------------+                                                            +----------------+
```

All three MCUs run in one pyrite `Emulation` with one virtual clock and a
lockstep quantum.

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
| W2 | Serial wire medium | days | Drone C3 sends a frame, H7 parses it, in one scenario. |
| W3 | Scripted protocol peer | days | Each firmware passes alone against the peer. |
| W4 | C3 I2C or GPSPI2 master model | 1-2 weeks | Unmodified ESP-IDF driver reads `WHO_AM_I`. |
| W5 | IMU device model | about 1 week | IDF IMU driver streams samples; FIFO overflow path is exercised. |
| W6 | BLE impairment knobs | days | Scenario cuts link; drone failsafe is asserted. |
| W7 | Sensor feed plus ESC sink | small | Recorded hand-tilt trace produces expected motor commands. |

Critical path: W1. W2 and W3 unblock both firmware teams early. The BLE hop is
usable immediately. Total estimate: about 6-8 person-weeks.

## Milestones

1. M1 - Hop by hop:
   remote C3 to drone C3 BLE, drone C3 to scripted peer, and H7 boot.
2. M2 - Wire closed:
   drone C3 to H7 over the serial wire with command-frame round trip.
3. M3 - Sensor in:
   IMU on remote C3, recorded trace to BLE to drone to H7 command.
4. M4 - Failure modes:
   BLE loss, latency, cut, stale frames, garbage injection, and CI failsafe
   assertions.
5. M5 - Loop out:
   ESC sink and measured hand-to-motor latency budget.

## Open Decisions

- Drone PCB radio: second ESP32-C3, nRF module, or HCI module driven by the H7.
- Drone C3 to H7 link: UART or SPI.
- IMU part and bus.
- Command and telemetry framing: MAVLink, COBS, or custom framing.

