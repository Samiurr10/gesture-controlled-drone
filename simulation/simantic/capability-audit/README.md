# ESP32-S3 and STM32H7 capability audit

**Controller: ESP32-S3 only. Drone: STM32H743 (STM32H7), later.**
The active priority is implementing and validating one hand before adding the
second hand, hub or drone.

Start with the [September 17 controller readiness record](../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md)
and [remaining Simantic requirements](SIMANTIC-REQUESTS.md).

| Test group | Evidence |
|---|---|
| ESP32-S3 boot, ADC, timing, GPIO and I2C diagnostics | [ESP32-S3 audit](esp32s3/README.md) |
| Corrected ADC and public ESP-IDF timer-driver tests | [Current readiness](../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md) |
| Later STM32H743 PWM, DMA, buses, ADC and firmware startup | [STM32H7 audit](stm32h7/README.md) |
| Later ArduCopter startup and alternate output routes | [Drone feasibility tests](full-drone/README.md) |

## Evidence boundaries

Recorded runtime: CLI/engine 0.5.7, Python SDK 0.3.1, macOS arm64. The ESP-IDF
follow-up uses v5.5.2 and the ADC PR overlay. Read each dated report's versions,
inputs and limitations before reusing a result. September 16 diagnostic failures
are preserved with links to corrected September 17 results.

The project supplies exact motion-sensor fixtures, flex voltages, fault traces,
controller logic and the integration application. A BME280 bus test is not
LSM6DS3TR-C/LIS3MDL driver coverage. No complete hand-controller, two-peer ESP BLE
or integrated drone qualification is claimed.

This package publishes reports and concise results. Test sources, setup scripts
and detailed traces referenced by the older reports remain local bench material;
their reproduction commands require that separate harness. Downloaded platforms,
ROMs, compiled images, runtime packages and credentials are excluded from Git.
