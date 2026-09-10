# Gesture-Controlled H7 Drone

This repository contains the researched hardware, firmware, and safety design
for a small gesture-controlled quadcopter. The project now goes directly to an
STM32H7 flight controller. Bluetooth Low Energy (BLE) is the first control
transport; ExpressLRS is a later receiver swap, not a flight-controller
redesign.

## Selected Build

```text
HAND CONTROLLER                    AIRCRAFT

BNO085 + controls                 GNSS + compass       4 x VL53L1X
        |                                |                    |
XIAO ESP32-C3 -- encrypted BLE --> XIAO ESP32-C3     XIAO RP2040
                                          |                    |
                                     CRSF |          range UART|
                                          v                    v
                                 Holybro Kakute H7 Mini v1.5
                                     STM32H743 + PX4 v1.17
                                          |
                                        DShot
                                          v
                                  4-in-1 ESC + motors
```

The H7/PX4 flight controller is the only flight authority. It owns arming,
state estimation, stabilization, position control, geofencing, failsafes, and
motor output. The aircraft ESP32-C3 only validates BLE commands and presents
them to PX4 as a conventional CRSF receiver.

## Locked Baseline

- Flight controller: Holybro Kakute H7 Mini v1.5, STM32H743.
- Flight firmware: pinned PX4 v1.17.0 custom build with `crsf_rc` enabled.
- Aircraft sensors: onboard ICM-42688-P accelerometer/gyroscope and SPA06
  barometer, an external ARK SAM GPS Mini GNSS/compass, and a staged
  four-direction VL53L1X collision-sensing package.
- Initial air link: encrypted, bonded BLE between two XIAO ESP32-C3 boards.
- Flight-controller link: full-duplex CRSF on `TELEM1`.
- Motors: four T-Motor F1204 5000KV motors on 3S, conditional on testing the
  team's actual propellers.
- ESC: T-Motor V45A Lite four-in-one, selected because the manufacturer lists
  current inventory. Its 30.5 mm mount requires the body to support separate
  20 mm and 30.5 mm electronics patterns.
- Battery: 3S 450 mAh standard LiPo with XT30, with final capacity subject to
  all-up mass and measured voltage sag.
- Boundary: PX4 GNSS geofence outdoors; physical net/enclosure indoors.
- Collision assistance: four VL53L1X sensors feed the H7 through a dedicated
  RP2040 hub on `TELEM2`. PX4 may brake only in the four measured directions;
  diagonal movement stays blocked in the first collision-assisted mode.

BLE RSSI is not a position sensor and cannot enforce a bounding box. The
software boundary is therefore based on the H7's estimated position outdoors.
An electronic indoor box would require a local-position system such as UWB,
motion capture, or validated optical flow and range sensing.

## Documentation

- [System architecture](docs/architecture.md)
- [H7 MCU decision](docs/mcu-architecture-research.md)
- [Direct H7 BLE build specification](docs/h7-ble/README.md)
- [Component list and procurement gates](docs/h7-ble/component-list.md)
- [Pin-level MCU and electrical architecture](docs/h7-ble/pin-architecture.md)
- [Electronics and wiring](docs/h7-ble/electronics-design.md)
- [Firmware and protocols](docs/h7-ble/firmware-design.md)
- [Collision sensing and prevention](docs/h7-ble/collision-prevention.md)
- [Safety and test plan](docs/h7-ble/safety-and-test-plan.md)
- [Research sources](docs/h7-ble/sources.md)

The documents are a prototype engineering baseline, not an assertion that the
aircraft is safe merely because it has been designed. Every gate in the test
plan must be demonstrated with the finished body and propeller before free
flight.
