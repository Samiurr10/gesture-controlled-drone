# ESP32 controller decision and migration

**Accepted September 16, 2026:** the user selected ESP32 for the hand controller. The implementation baseline is **ESP32-S3** for two hand nodes and the hub. The virtual drone remains the STM32H743/KakuteH7 firmware candidate.

## Hardware baseline

Use **ESP32-S3-DevKitC-1 carrying ESP32-S3-WROOM-1-N8R2** for USB-powered bench development. Confirm the full module marking and availability when ordering: 8 MB flash and 2 MB quad PSRAM. N8R2 is listed in the v1.0 guide; do not assume every current DevKitC-1 listing has this memory configuration. The Simantic catalog candidate is `ESP32-S3-WROOM-1-N8R2`; a module model does not automatically include the DevKit USB bridge, regulator or external sensors. [Espressif DevKitC-1 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.0.html)

Use GPIO1/2/4/5/6 for flex inputs, GPIO7 for left ENABLE or hub CALIBRATE, and GPIO8/9 for SDA/SCL. Reserve GPIO10 for a reviewed battery divider. Avoid GPIO3, a strapping pin, and preserve USB GPIO19/20 and UART0 GPIO43/44. Each hand uses an external Adafruit #5543 LSM6DS3TR-C + LIS3MDL motion-sensor breakout. Exact header positions and assembly instructions are in the [build guide](build-guide.md).

The DevKit has no integrated hand IMU or LiPo charger/connector. A smaller wearable board is a later design decision; battery power must be designed and reviewed before wearable assembly.

## Active controller configuration

| Item | ESP32-S3 implementation |
|---|---|
| Hands | ESP32-S3 plus five flex channels and external motion sensors per hand |
| Hub | ESP32-S3, planned two-peer BLE central |
| ADC | ADC1 one-shot, attenuation and calibration through ESP-IDF |
| Motion driver | LSM6DS3TR-C/LIS3MDL through ESP32 I2C |
| Framework | ESP-IDF v5.5.2 diagnostic baseline; pin the production build at S0 |
| Power | USB bench first; reviewed wearable power and monitoring design required |
| Host connection | UART0 through the onboard USB-to-UART bridge for bench work |
| Drawings | New ESP32-S3 schematic revision required before permanent assembly |

The physical ADC bench board is **Freenove ESP32-S3 WROOM N8R8** (8 MB flash,
8 MB PSRAM). Validation firmware disables PSRAM. The N8R2 remains the simulation
reference; record the exact deployed memory and header configuration.

The planned topology is two ESP32-S3 hands → BLE → ESP32-S3 hub → computer.
Start with one hand. Wi-Fi/ESP-NOW is not selected.

## Current evidence

The [September 17 readiness record](../implementation-records/2026-09-17_hand-controller-readiness.md)
records corrected ADC and full ESP-IDF driver tests, working `esp_timer`, the
TIMG gap and remaining validation. Exact IMU fixtures, NVS, watchdog recovery
and ESP BLE require further work. Production controller firmware is pending.
Only tests on the selected ESP32-S3 driver/model qualify this controller.

## Migration checkpoints

- [x] Record ESP32-S3 controller/hub decision and USB bench target.
- [x] Update active architecture, controller guides, shopping guidance and inventory semantics.
- [x] Remove retired controller simulations, model requests and inventory entries.
- [ ] Qualify ESP32-S3 runtime and real firmware framework.
- [ ] Confirm external sensor revision and required driver transactions.
- [ ] Publish/review the new ESP32 schematic revision and wearable power design.
- [ ] Implement acquisition, calibration, validity, two-hand communication and host commands.
- [ ] Pass S0–S3, then physical C0–C7, then integrated D1–D4.

The Gantt workbook uses generic controller/drone milestones and does not define MCU wiring. Its evidence gates remain applicable; the active BOM and this record supersede old part selections.
