> **Archived design — superseded 2026-09-16.** The active project physically builds only the hand controller: first simulate and validate it in Simantic, then build its prototype. The second goal is a virtual drone: Simantic models its hardware/microcontroller and produces actuator signals for a mechanical simulation shown on screen. Physical drone construction, aircraft purchases and flight tests are outside scope; Pocket/ELRS/trainer hardware is not required.
>
> Use the [project goals](../../README.md), [current architecture](../architecture.md) and [controller plan](../controller/README.md). The original September 10 record below is retained as design history. Its “current,” “required,” “later,” procurement and flight instructions describe that abandoned plan, not present requirements; its MCU selections do not select the virtual drone's implementation.

# Direct H7 BLE Flight Prototype

This directory is the build specification for the first flying prototype. It
uses an H7 flight controller from the beginning, BLE for the first pilot link,
and a CRSF boundary that can accept ExpressLRS later.

## Locked Architecture

```text
HAND CONTROLLER                    AIRCRAFT

BNO085 + thumb stick              ARK GNSS + compass      4 x VL53L1X
        |                                |                      |
XIAO ESP32-C3 -- encrypted BLE --> XIAO ESP32-C3       XIAO RP2040
                                          |                      |
                                     CRSF |            range UART|
                                          v                      v
                                Holybro Kakute H7 Mini v1.5
                                STM32H743 + ICM-42688-P
                                          |
                                       DShot300
                                          v
                                T-Motor V45A Lite 4-in-1
                                          |
                                4 x F1204 5000KV motors
```

The H7 runs PX4 and is the only flight authority. It owns the aircraft IMU,
state estimation, prearm checks, position mode, geofence, RC-loss behavior,
control loops, motor allocation, and DShot output. Neither ESP32-C3 stabilizes
the aircraft or directly controls an ESC.

## Core Decisions

- Use the Holybro Kakute H7 Mini v1.5, not an F7 and not a custom H753 PCB.
- Pin PX4 v1.17.0 and build it with CRSF support enabled.
- Use a XIAO ESP32-C3 and BNO085 in the hand controller.
- Use a second XIAO ESP32-C3 as BLE central and CRSF receiver gateway.
- Use the onboard aircraft ICM-42688-P accel/gyro and SPA06 barometer; do not
  add a duplicate IMU to the first prototype.
- Add ARK SAM GPS Mini GNSS/compass for outdoor position and geofence.
- Add four body-mounted VL53L1X sensors through a dedicated XIAO RP2040 hub and
  H7 `TELEM2` after the base aircraft flies. The first mode is four-direction
  collision braking, not autonomous or diagonal avoidance.
- Use four T-Motor F1204 5000KV motors on a 3S battery, conditional on testing
  the team's actual propeller.
- Use the currently listed T-Motor V45A Lite ESC. Its 30.5 mm mount is larger
  than the H7's 20 mm mount, so the custom body must provide both patterns.
- Use a physical net/enclosure indoors. BLE RSSI and GNSS cannot enforce an
  indoor bounding box.
- Later, unplug the BLE gateway and connect an ExpressLRS receiver to the same
  CRSF connector. Never connect both at once.

## Documents

1. [Architecture and decisions](design-report.md)
2. [Components, motors, and procurement](component-list.md)
3. [Pin-level MCU and electrical architecture](pin-architecture.md)
4. [Electronics, power, pinout, and wiring](electronics-design.md)
5. [Firmware, BLE, CRSF, and PX4](firmware-design.md)
6. [Collision sensing and prevention](collision-prevention.md)
7. [Boundary safety and test gates](safety-and-test-plan.md)
8. [Official research sources](sources.md)

## Baseline Assumptions

- Team-designed guarded body for nominal 2.5-inch propellers.
- Body provides separate 20 x 20 mm H7 and 30.5 x 30.5 mm ESC mounting.
- 3S standard LiPo power.
- Provisional 130-160 g base-aircraft mass and 140-175 g with collision
  hardware, both to be replaced by measured mass.
- First outdoor movement remains inside 10 m radius and 3 m height, with a
  15 m horizontal and 5 m vertical PX4 fence in a site clear for at least 25 m.
- Indoor powered tests occur only in a physical enclosure.

The selected motor, battery, and ESC are not approved by a table alone. The
finished body and actual propeller must pass the purchase and thrust gates.
