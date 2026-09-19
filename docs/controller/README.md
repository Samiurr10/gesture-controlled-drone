# ESP32-S3 controller — start here

**Active baseline: ESP32-S3, approved September 16, 2026.** Simulate one hand
first, then both hands and the hub; build the physical controller after the
simulation gates. The later drone remains an STM32-based virtual system.

The working board reference is **ESP32-S3-DevKitC-1-N8R2**, using
ESP32-S3-WROOM-1-N8R2 (8 MB flash, 2 MB quad PSRAM). Confirm the delivered module
marking and PCB revision before using header numbers. A different DevKit variant
requires a recorded flash/PSRAM/board configuration; it is not an automatic swap.
This is a USB-powered development-board baseline, not a finished wearable PCB.

Each hand has five flex inputs and an **external Adafruit #5543
LSM6DS3TR-C + LIS3MDL** motion module. The left hand has hold-to-enable. A third
ESP32-S3 is the BLE central hub, with CALIBRATE and a computer command link.
BLE remains the selected topology; Wi-Fi/ESP-NOW is not part of this migration.

## Read in this order

| Need | Document |
|---|---|
| Current system boundaries | [Architecture](../architecture.md) |
| ESP32-S3 capability and implementation gates | [Simantic plan](simantic-plan.md) |
| Incremental hardware | [Controller BOM](bom.md) |
| Exact proposed bench pin assignments | [Build guide](build-guide.md) |
| Drivers, calibration, BLE and host contract | [Firmware plan](firmware-plan.md) |
| Gesture table, axes and safety interlocks | [Gesture mapping](gesture-mapping.md) |
| Firmware source, build and simulation tests | [Firmware workspace](../../firmware/README.md) |
| Acceptance and evidence | [Validation](validation.md) |

## Build sequence

| Stage | Deliverable | Exit evidence |
|---|---|---|
| S0 | ESP32-S3 boot, ADC1, GPIO, I2C, timer/reset and storage probes | Tests against the selected ESP model/firmware; gaps recorded |
| S1 | One simulated hand: one flex → five flex → external motion → enable | Acquisition, calibration and fault assertions |
| S2 | Two ESP hand peripherals and ESP hub central | Two simultaneous BLE links and whole-command invalidation |
| S3 | Hub output to host test sink | Versioned command, expiry, stop/recovery and regression evidence |
| C0 | Physical board/module/revision and bench preparation | As-received record; approved ESP wiring revision |
| C1 | USB-powered first flex on GPIO1 | Continuity, measured voltages and calibrated ADC log |
| C2 | Five left-hand flex inputs plus external motion module | Channel independence, sensor identities/axes and calibration |
| C3 | Left enable and reviewed wearable power/mechanics | Power design completed and measured; no assumed LiPo compatibility |
| C4 | Right hand | Independent power, calibration and side identity |
| C5 | ESP hub | Both BLE links, calibration and valid/invalid command states |
| C6 | Controller/computer bridge | Independently decoded commands and disconnection/recovery tests |
| C7 | Physical controller qualification | Complete applicable test records, firmware/configuration archive |

## Remaining design work

- ESP32-S3 is the sole controller platform. The ADC and timer diagnostic results
  support starting one-hand firmware; full controller qualification is pending.
- The new build guide is a sourced **bench pin plan**, not a newly verified full
  ESP schematic. A revised schematic/netlist and wearable power design are
  required before permanent assembly and C3 qualification.
- Start with USB power. There is no assumed BAT socket, LiPo charger or factory
  battery measurement on DevKitC-1. GPIO10 is reserved, not wired to a battery.
