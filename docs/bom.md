# ESP32-S3 controller BOM

Parts for the two hands and the hub, bought in the order the
[wiring](wiring/README.md#build-order) is built. The drone is simulated, so it
needs no parts.

Board choice is open. The wiring drawings use the genuine Espressif
ESP32-S3-DevKitC-1 header. The N8R2 variant used as the simulation reference was
discontinued on 2026-09-30, so the table lists the N8R8. The firmware runs with
PSRAM off, so the extra PSRAM changes nothing. The ADC bench measurements so far used a
Freenove ESP32-S3 WROOM (N8R8). Its header differs, so using it needs its own pin
mapping for the drawings; the GPIO numbers stay the same.

## Incremental quantities

Totals below are cumulative; buy the first column for the first physical test
only after the relevant simulation gate. Existing correctly specified passive
parts and flex sensors may be reused after inspection.

| Part | One flex | Complete left bench | Two hands + hub bench | Notes |
|---|---:|---:|---:|---|
| Genuine ESP32-S3-DevKitC-1-N8R8 | 1 | 1 | 3 | Two hands and one BLE hub. The N8R2 is obsolete (2026-09-30); firmware runs with PSRAM off, so the N8R8's 8 MB octal PSRAM changes nothing, and its GPIO35-37 are not in the pin map |
| Adafruit #1070 flex sensor | 1 | 5 | 10 | One per finger; measure actual comfortable resistance range |
| 47 kΩ, 1% resistor | 1 | 5 | 10 | Each flex signal to local GND |
| 100 nF ceramic capacitor | 1 | 6 | 12 | Ten flex shunts plus left ENABLE and hub CALIBRATE shunts |
| Adafruit #5543 LSM6DS3TR-C + LIS3MDL breakout | 0 | 1 | 2 | External motion module per hand; hub needs none |
| Momentary normally-open button | 0 | 1 | 2 | Left ENABLE; hub CALIBRATE |
| 10 kΩ resistor | 0 | 1 | 2 | Button pull-up to local 3V3 |
| 1 kΩ resistor | 0 | 1 | 2 | Button series resistor between signal and switch |
| Two-pin keyed sensor connector pair | 1 | 5 | 10 | Optional for breadboard; recommended before wearable harnessing |
| Four-wire IMU connection or STEMMA-QT-to-header cable | 0 | 1 | 2 | DevKit has no assumed STEMMA QT socket; verify cable functions |
| USB data cable matching actual board socket | 1 | 1 | 3 | Initial programming/power through USB-to-UART port |
| Breadboard/perfboard, jumper wires, labels | As needed | As needed | As needed | Check DevKit width; two breadboards may be more convenient |

The 12-capacitor total excludes board-mounted decoupling and all optional trainer
parts. Keep a few spare resistors, capacitors and connectors; spares are not
additional channels.

## Selection details

Before wiring, confirm the module marking printed on each board and its PCB
revision ([DevKitC-1 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html),
[module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)).

The selected [Adafruit #5543](https://www.adafruit.com/product/5543) adds the
accelerometer, gyroscope and magnetometer that are no longer onboard the MCU
board. Its default I2C addresses are 0x6A and 0x1C. Use one module on each hand's
own bus. Start with acceleration/gyro measurements; magnetic calibration and
heading quality need separate evidence.

## Power

USB powers every board. Nothing in this list is for battery power. A wearable
power circuit (cell, charger, regulator, switch, battery monitor) has to be designed
and reviewed before any parts for it are chosen. Until then, do not connect a cell
to 3V3, GPIO10 or any other pin.
