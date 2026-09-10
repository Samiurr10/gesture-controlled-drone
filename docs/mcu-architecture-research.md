# MCU Selection Research

Research baseline: 2026-09-10

## Decision

Use an STM32H743 flight controller now, specifically the Holybro Kakute H7 Mini
v1.5. Use one ESP32-C3 in the hand controller and a second ESP32-C3 as the
aircraft BLE-to-CRSF gateway. After the base aircraft flies, add one XIAO
RP2040 as a range-only hub for the four collision sensors.

| Function | Selected MCU | Why |
|---|---|---|
| Flight control | STM32H743, 480 MHz Cortex-M7 | Compact PX4-supported H7 board, enough compute and memory for estimation, position control, logging, and future sensors |
| Hand control | ESP32-C3, 160 MHz RISC-V | Existing XIAO board is sufficient for BNO085 parsing, controls, BLE, and safety-state logic |
| BLE receiver gateway | ESP32-C3, 160 MHz RISC-V | Same toolchain and radio behavior; isolates BLE from flight-control scheduling |
| Collision-sensor hub | RP2040, dual-core Cortex-M0+ up to 133 MHz | Handles same-address ToF startup and sampling without sharing the H7 compass I2C bus; has no flight authority |

Holybro lists the v1.5 board with an STM32H743, ICM-42688-P IMU, SPA06
barometer, six UARTs, 128 Mbit flash, 20 x 20 mm mounting, and 5.5 g mass.
PX4 documents the board target as `holybro_kakuteh7mini_default` and supports
the board on PX4 v1.14 and newer. [[9]](h7-ble/sources.md#source-9)
[[10]](h7-ble/sources.md#source-10)

## Why H7 Instead of F7

An F7 can stabilize this aircraft. The reason to skip it is architectural, not
that F7 is incapable of flight. The project wants one platform that can retain
headroom for:

- PX4 EKF and GNSS Position mode.
- Geofence and multiple failsafe policies.
- High-rate flight logging and post-flight analysis.
- A staged four-direction VL53L1X collision-sensing link, followed later by
  optical flow, UWB, or a wider-coverage range sensor if required.
- BLE first and CRSF/ExpressLRS later without changing flight hardware.

Starting with H7 avoids a board and firmware migration after the basic flight
demo. It does not remove the need for a position sensor, safe RF behavior, or
propulsion testing.

## H743 Versus H753

The previous design proposed a custom STM32H753 PCB. That is no longer the best
route to first flight.

| Option | Result |
|---|---|
| STM32F405/F7 flight controller | Technically sufficient for basic flight, but rejected to avoid a later platform change |
| Custom STM32H753 board | Maximum control over hardware, but introduces power, clocks, memory, sensor layout, bootloader, manufacturing, and PX4-port risk |
| Holybro STM32H743 board | Selected: H7 compute on a flight-proven form factor with published PX4 support |

H753 cryptographic peripherals are not a flight-control advantage here. The
value of the H743 choice is the complete supported board, not a claim that H743
is intrinsically faster. A custom flight-controller PCB should only begin after
the off-the-shelf architecture has flown and produced measured requirements.

## Why the ESP32-C3s Stay Separate

The hand C3 handles a human-rate sensor and radio workload. The aircraft C3
handles one BLE connection and one UART. Both are well within the C3's 160 MHz
CPU, 400 KB SRAM, BLE 5 support, and peripheral set. [[1]](h7-ble/sources.md#source-1)

The aircraft C3 is not merged into the H7 because BLE pairing and reconnection
are bursty, externally driven tasks. A separate gateway can reset or lose its
link while the H7 continues deterministic estimation and stabilization long
enough to run a controlled failsafe. The H7 independently detects CRSF silence.

The C3s are development boards for this prototype. A later custom hand PCB can
use an ESP32-C3 module or a lower-power BLE MCU after battery life and firmware
requirements are measured.

## Sensor Decision

The aircraft does not need an additional accelerometer or gyroscope for the
first prototype. The Kakute H7 Mini v1.5 already includes an ICM-42688-P
six-axis IMU and a barometer. It lacks an onboard magnetometer, so the selected
ARK SAM GPS Mini contributes both GNSS and an external IIS2MDC compass.
[[13]](h7-ble/sources.md#source-13)

This is a single-flight-IMU prototype, not a redundant or safety-certified
autopilot. Add a second aircraft IMU only after the project has a requirement
and a board with supported redundant sensor paths.

The hand BNO085 is not part of the flight estimator. It only measures the
operator's orientation. Use UART-RVC at 115200 baud because Adafruit documents
interoperability problems between BNO08x I2C behavior and ESP32-family devices.
[[6]](h7-ble/sources.md#source-6) [[7]](h7-ble/sources.md#source-7)

## Compute Does Not Make a Bounding Box

Neither H7 nor BLE can determine position without measurements. BLE RSSI varies
with antenna orientation, the operator's body, multipath, interference, and RF
front-end behavior. It is useful for diagnostics, not an enforced radius.

For the first outdoor flight, PX4 uses GNSS, compass, barometer, and aircraft
IMU data to estimate position and apply a geofence. Position mode requires a
global position estimate. [[20]](h7-ble/sources.md#source-20)

For indoor flight, the reliable first boundary is physical. A later electronic
indoor box requires a local-position source and its own loss/degradation policy.

## Software and Upgrade Consequences

- Pin PX4 v1.17.0 rather than building against a moving branch.
- Flash the PX4 bootloader because the Kakute ships with Betaflight.
- Enable PX4 `crsf_rc`; it is not present in default firmware builds.
- Connect BLE gateway CRSF to H7 `TELEM1`.
- Replace the gateway physically with an ExpressLRS receiver later.
- Keep all arming, modes, geofence, and failsafe configuration on PX4.
- Keep the RP2040 range hub outside flight authority: it reports measurements
  and health only; PX4 decides whether movement is allowed.

This decision deliberately favors getting a measured aircraft flying over
building a novel flight controller before the requirements are known.
