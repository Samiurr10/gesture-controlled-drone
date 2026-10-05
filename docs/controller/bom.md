# ESP32-S3 controller BOM

**Active controller platform: ESP32-S3 only.** Reference board:
ESP32-S3-DevKitC-1-N8R2 with ESP32-S3-WROOM-1-N8R2. Start with one USB-powered
board. These quantities are required items, not a statement of parts on hand.
The final wearable power circuit and revised ESP schematic are still pending.

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

The N8R2 module has 8 MB quad flash and 2 MB quad PSRAM. Espressif documents the
N8R2 DevKit ordering variant, but current retailer stock and delivered PCB
revision have not been verified here. Confirm the printed module suffix before
ordering; an N8R8 or WROOM-1U board needs a recorded memory/antenna configuration.
[Espressif board ordering reference](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.0.html),
[module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf).

The selected [Adafruit #5543](https://www.adafruit.com/product/5543) adds the
accelerometer, gyroscope and magnetometer that are no longer onboard the MCU
board. Its default I2C addresses are 0x6A and 0x1C. Use one module on each hand's
own bus. Start with acceleration/gyro measurements; magnetic calibration and
heading quality need separate evidence.

## Power and mechanics — design before purchase/assembly

USB powers the initial bench. DevKitC-1 needs an external wearable power circuit.
The later wearable design must specify a protected cell/pack, charger, power-path
behavior, regulator sized for actual ESP/radio peaks, disconnect switch,
low-battery measurement and mechanical protection. Record schematics, current
budget, USB coexistence and charging procedure before selecting these parts.

Do not connect the old 1S pack directly to 3V3, GPIO10 or a supposed BAT pin.
GPIO10 is only a reserved future ADC input. No divider values or charger model
are selected in this BOM. An existing #1578 cell may be considered only after
that design review; its wiring must follow the new power design.

## Scope of purchases

This list covers the ESP32-S3 hand controller and hub. Drone hardware is simulated and does not need to be purchased.
