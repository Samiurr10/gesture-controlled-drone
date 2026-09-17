# ESP32 migration and complete-drone feasibility

> **September 17 follow-up:** see the [current hand-controller readiness record](2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

Date: September 16, 2026. Scope: the accepted ESP32 controller change and actual Simantic tests toward the complete virtual drone. This record does not mark S0–S3, C0–C7 or D1–D4 complete.

## Decision and answer

**Subsequent double-check:** the [ADC/input review](../../simulation/simantic/capability-audit/esp32s3/adc-review/README.md) verifies the installed ADC and timer implementations directly, repeats CLI/SDK execution and checks voltage injection against a working STM32 positive control. The ADC gap is confirmed, but earlier zero data was not a calibrated analog-accuracy test. Full ESP-IDF driver qualification remains pending.

The controller now uses **ESP32-S3**, with an **ESP32-S3-DevKitC-1 / ESP32-S3-WROOM-1-N8R2** USB bench target for each hand and hub. Each hand adds an external **Adafruit #5543 LSM6DS3TR-C + LIS3MDL** motion-sensor board. The drone candidate remains **STM32H743/KakuteH7 with ArduCopter 4.7.1**.

**The complete drone simulation is not yet working.** Current evidence establishes selected MCU/peripheral mechanisms and stock firmware progress, not the chain from controller sensing through flight control, all four motor outputs, dynamics, sensor feedback and display.

The user owns flex/motion input generation, sensor response providers, integration, physics and display. Missing project components are distinct from missing or incorrect simulator behavior. A standalone visual drone or host-only flight model would not qualify the requested MCU simulation.

## Runtime evidence

Test environment: CLI/engine **0.5.7**, SDK **0.3.1**, macOS arm64. Exact model, fixture, firmware and source hashes belong to each test group.

| Boundary | Evidence location | Qualification requirement |
|---|---|---|
| ESP32-S3 selected model and executable diagnostic | [ESP32 runtime audit](../../simulation/simantic/capability-audit/esp32s3/README.md) | CPU/framework boot, ADC conversion, motion-driver I²C, timers, storage and communications |
| Stock STM32 drone firmware with sensor fixtures | [Extended drone audit](../../simulation/simantic/capability-audit/full-drone/README.md) | Healthy startup, steady sensor acquisition, command processing and changing motor outputs |
| STM32 timer/DMA/bus behavior | [Earlier H7 audit](../../simulation/simantic/capability-audit/stm32h7/README.md) | Four correctly routed outputs; request-paced DMA if DShot is selected |

## Work order

### What has passed so far

- **ESP32-S3 diagnostic firmware:** executable boot, advancing Xtensa cycle counter, UART transmit/receive echo, digital input injection on the five selected flex pins and GPIO7, SYSTIMER snapshots and an advancing counter. An I²C register read with repeated START returns the fixed BME280 fixture ID, with STOP/completion, event clearing and absent-slave NACK behavior.
- **STM32 stock firmware:** ArduCopter now reaches IMU initialization, reads the ICM42688P FIFO and enters `AP_Vehicle::loop()`. The instrumented run records 1,345 FIFO-read function entries, 2,892 IMU SPI frames and 62 vehicle-loop entries by 8.25 virtual seconds, with no sampled CPU fault flags. Barometer transactions and startup MAVLink heartbeat output also work. This establishes firmware scheduling and sensor-driver progress, not estimator health, successful arming or a closed flight-control/dynamics loop.
- **Four alternate STM32 PWM outputs:** the diagnostic observes PB3/TIM2_CH2, PB10/TIM2_CH3, PA0/TIM5_CH1 and PA2/TIM5_CH3 with respective 1100/1300/1500/1700 µs pulses. The measured period is 19,999 µs for a nominal 20,000 µs. This is an alternative virtual pin configuration, not the original four Kakute outputs or a tested ArduCopter remap.

### Established limits

- **ESP32 ADC:** the selected RTC conversion sequence never reports DONE; the APB SARADC region is plain mapped memory. Digital input injection on ADC-capable pins is not analog conversion coverage.
- **ESP32 TIMG0:** after matching the HAL divider-reset and snapshot-wait sequence, enable/configuration readback passes but UPDATE never reports a ready snapshot and the alarm flag stays zero. The zero sampled count is not a valid proof that the underlying counter never advances. SYSTIMER passes its narrow counter test.
- **ESP32 high GPIO bank:** GPIO43 does not behave correctly and injection reports an out-of-range pin. The selected flex/button pins are in the tested low bank. Peripheral UART success does not establish the GPIO matrix/physical pin routing.
- **Production ESP framework and links:** ROM/bootloader/ESP-IDF application, BLE two-peer stack, flash/NVS and watchdog recovery remain unqualified. The bare-metal diagnostic is not that application.
- **Original STM32 motor configuration:** complementary TIM1 outputs fail in the earlier probe. The alternate four-main-channel PWM route needs a deliberate firmware configuration and end-to-end test; DShot additionally needs request-paced DMA.
- **Whole project:** no completed controller application, actuator-to-mechanics adapter, closed sensor-feedback loop or rendered integrated demonstration exists yet.

The final ESP diagnostic contains 32 assertions (23 pass, 9 fail), plus 8 SDK input/output checks (7 pass, 1 fail). These counts include repeated channel checks and are not counts of unique defects. Independent register-sequence review added ADC idle waiting, timer divider reset and snapshot-ready waiting; the affected cases were rerun. Exact versions and source snapshots are retained in the ESP audit.

### Drone startup configuration that made progress possible

The successful extended run attaches the engine's ICM42688P model and an explicitly simplified SPA06 barometer startup fixture. An unattached optional OSD bus initially returned zero and led ArduCopter into a long display-font initialization path. A scripted absent-device fixture returning pulled-high `0xFF` lets the unmodified firmware reject the optional OSD and proceed normally. No CPU hook skips flight-firmware code. Separate SD-card attachment experiments do not establish filesystem or logging qualification.

IMU hardware initialization begins near 7.4818 virtual seconds, FIFO reads near 7.5726 seconds and the vehicle loop near 8.09925 seconds. The instrumented run reaches its 55-second wall-time budget at 8.25 virtual seconds. That is a diagnostic observation, not a real-time performance guarantee; output/trace overhead and synchronization need separate measurement before live controller integration.

## Next implementation sequence

1. Qualify and fix the ESP32-S3 runtime and required MCU peripherals. First prove one ADC channel through the intended driver, then all five flex channels and the external IMU transactions.
2. Implement ESP-IDF sensing, calibration, acquisition timestamps, sequence/identity, validity and enable logic. Test sensor faults before adding the second hand.
3. Qualify the selected ESP32 BLE stack with two simultaneous peers and serial host output. Complete S0–S3 before claiming a fully simulated controller.
4. Build on the stock STM32 vehicle-loop result: qualify realistic sensor values, estimator health, configuration/storage and command input. Select and validate the four motor routes, then demonstrate changing flight-firmware outputs under deterministic inputs.
5. Connect four decoded motor outputs to the project-owned dynamics. Feed that state back through the same virtual sensor interfaces on a documented simulation timeline.
6. Integrate the qualified physical controller and display. Record command, sensor, motor and motion traces together and pass D1–D4.

Drone feasibility tests are authorized now, while the delivery priority remains the controller. The full wearable ESP32 schematic, power subsystem and production firmware remain open tasks.

## Documentation changed

The root checklist, architecture, controller BOM/build/firmware/validation guides and Simantic inventory now target ESP32-S3. The September 17 cleanup replaces the mixed historical inventory with active ESP32-S3 and STM32H7 entries only. Retired controller simulations and model requests were removed. Original Rev A drawings remain archived source material, outside the simulation configuration.

The existing Gantt workbook contains generic controller/drone stages without MCU-specific part or pin assignments. Its schedule remains applicable; the schedule README links the additional ESP32 migration checkpoints. No dates or completed milestone claims were invented.

## Verification of this update

- Documentation check passed: 355 local links across 49 Markdown files; the historical 142 connection records and 11 SVG sheets retain their structural checks.
- Audit JSON parses; Python audit sources compile; whitespace checks pass.
- New ESP and extended-drone recorded source hashes match the retained files. ESP boot/I²C and revised ADC/timer probes identify their exact source snapshots.
- Runtime failures remain recorded as failures. These repository checks do not turn incomplete controller/drone qualification into a pass.
