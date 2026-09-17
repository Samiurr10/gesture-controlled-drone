# ESP32 controller decision and migration

**Accepted September 16, 2026:** the user selected ESP32 for the hand controller. The implementation baseline is **ESP32-S3** for two hand nodes and the hub. The virtual drone remains the STM32H743/KakuteH7 firmware candidate.

## Hardware baseline

Use **ESP32-S3-DevKitC-1 carrying ESP32-S3-WROOM-1-N8R2** for USB-powered bench development. Confirm the full module marking and availability when ordering: 8 MB flash and 2 MB quad PSRAM. N8R2 is listed in the v1.0 guide; do not assume every current DevKitC-1 listing has this memory configuration. The Simantic catalog candidate is `ESP32-S3-WROOM-1-N8R2`; a module model does not automatically include the DevKit USB bridge, regulator or external sensors. [Espressif DevKitC-1 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.0.html)

Use GPIO1/2/4/5/6 for flex inputs, GPIO7 for left ENABLE or hub CALIBRATE, and GPIO8/9 for SDA/SCL. Reserve GPIO10 for a reviewed battery divider. Avoid GPIO3, a strapping pin, and preserve USB GPIO19/20 and UART0 GPIO43/44. Each hand uses an external Adafruit #5543 LSM6DS3TR-C + LIS3MDL motion-sensor breakout. Exact header positions and assembly instructions are in the [build guide](build-guide.md).

The DevKit has no integrated hand IMU or Feather-style LiPo charger/connector. A smaller wearable board is a later design decision; battery power must be designed and reviewed before wearable assembly.

## What changes

| Item | Previous design | Active ESP32 work |
|---|---|---|
| Hands | Feather nRF52840 Sense | ESP32-S3 plus external motion sensors |
| Hub | Feather nRF52840 Express | ESP32-S3, planned two-peer BLE central |
| ADC | Nordic SAADC/EasyDMA and A0–A4 | ESP32 ADC1 mapping, attenuation and calibration |
| Motion driver | Adafruit onboard IMU through Nordic TWIM | External sensor through ESP32 I²C driver |
| Framework | Proposed Adafruit nRF52 core / SoftDevice | ESP-IDF baseline; pin release/toolchain in S0 |
| Power | Feather charger, JST battery, A6 divider and EN switch | USB bench first; new wearable power and monitoring design |
| Host connection | Proposed Feather USB CDC | DevKit USB-to-UART bench path; production transport qualified separately |
| Drawings | Rev A Feather pins and power | New ESP32 revision required |

The logical two-hand → BLE hub → computer topology remains planned. Wi-Fi and ESP-NOW are possible later choices, not part of this migration decision.

## Evidence does not transfer across MCUs

The [nRF52840 audit](../../simulation/simantic/capability-audit/nrf52/README.md) remains historical evidence. Its SAADC, TWIM, NVMC, watchdog and USB issues no longer gate the ESP32 controller. A successful nRF Zephyr BLE connection also does not qualify ESP32 BLE.

The [ESP32/full-drone assessment](../implementation-records/2026-09-16_esp32-full-drone-feasibility.md) records actual runtime results. Hardware selection and simulator support are separate decisions. Application mocks cannot qualify missing hardware paths.

## Migration checkpoints

- [x] Record ESP32-S3 controller/hub decision and USB bench target.
- [x] Update active architecture, controller guides, shopping guidance and inventory semantics.
- [x] Mark nRF-specific wiring, research and simulator requests as historical.
- [ ] Qualify ESP32-S3 runtime and real firmware framework.
- [ ] Confirm external sensor revision and required driver transactions.
- [ ] Publish/review the new ESP32 schematic revision and wearable power design.
- [ ] Implement acquisition, calibration, validity, two-hand communication and host commands.
- [ ] Pass S0–S3, then physical C0–C7, then integrated D1–D4.

The Gantt workbook uses generic controller/drone milestones and does not define MCU wiring. Its evidence gates remain applicable; the active BOM and this record supersede old part selections.
