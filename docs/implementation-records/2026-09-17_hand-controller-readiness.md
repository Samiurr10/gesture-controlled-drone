# ESP32-S3 hand-controller readiness — September 17, 2026

## Decision

Start **one-hand firmware** using ESP-IDF, the ADC model from
[PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168),
SYSTIMER-backed `esp_timer`/FreeRTOS, GPIO7 ENABLE and UART diagnostics.
Production hand-controller firmware is not implemented yet. The complete
controller is not qualified; S0–S3 remain open. Defer drone implementation until
this controller works. The later drone target is **STM32H743 (STM32H7)**.

## Environment and evidence boundary

- Simantic CLI/engine 0.5.7; Python SDK 0.3.1; ESP-IDF v5.5.2.
- Simulation platform: ESP32-S3-WROOM-1-N8R2. Physical ADC bench board:
  Freenove ESP32-S3 WROOM, silicon v0.2, 8 MB flash / 8 MB PSRAM.
  Validation firmware uses one CPU and disables PSRAM; multicore and PSRAM
  operation are not established by these results.
- ADC PR at run time: open/unmerged, head
  `46e1d296afbdca9e7f1d80900def2b53ed9dfdc0`. Tests load a namespace-only
  SENS overlay; the installed engine is unchanged.
- Infrastructure source inspected:
  `204b580155d1a18ff4e3f640fbe38e68c1a0bf60`; MCU catalog source:
  `167bf7ae24298e72e3e87d864a766cf829cf7d20`.

This is a published summary of local bench evidence. Disposable test apps,
compiled firmware, full sample logs, ROM downloads and flash backups are not
part of this documentation package. September 17 rerun and timer evidence is
retained locally in `tmp/simantic/rerun-2026-09-17/` and
`tmp/simantic/hand-setup-review/`; physical ADC evidence remains in the local
`simulation/simantic/hardware-validation/esp32s3-adc/` bench directory.
The historical September 16 audit records remain published separately.

## ADC: distinguish a probe bug from a missing converter

The original register-level probe omitted `SENS.SARADC_CLK_EN` at SENS + 0x104,
bit 30. A separately built copy adds that clock enable. The original probe still
fails on both models; the corrected probe fails on stock 0.5.7 and passes with
the ADC overlay. No result registers were injected.

| Check | Result |
|---|---|
| Corrected original suite, stock engine | 23 pass / 9 fail |
| Corrected original suite, ADC overlay | 28 pass / 4 fail |
| ADC assertions within corrected overlay suite | 15 / 15 pass |
| Planned five flex inputs, GPIO1/2/4/5/6 | Injected 0.2/0.4/0.6/0.8/1.0 V; expected and observed raw 186/372/558/744/930 at attenuation encoding 3 |
| Fresh full ESP-IDF public ADC-driver rerun | 120 batches / 960 reads pass across ten channels, four attenuations and 0/0.5/0.9 V |
| Separate SDK I/O checks | 7 pass / 1 fail; GPIO43 input remains out of range |

Remaining register-suite failures concern TIMG0 snapshot/counter/alarm and
GPIO43 output. GPIO43 is reserved for UART0 in our design; it is not a planned
flex/ENABLE input. UART byte transport passes, but this does not qualify full
physical GPIO-matrix behavior.

### Physical ADC checks completed September 16

The same ADC application binaries were used on hardware and with a simulator
ROM/flash wrapper. GPIO1 tied to GND returned 256 successful readings: 64 at
each attenuation, raw ranges 0–45, 0–19, 0–9 and 0–6 respectively. GPIO1 tied to
the board's nominal 3V3 rail returned 64 readings of 4095 at attenuation 3.
The rail was **not measured**. The ideal model returns 3071 at exactly 3.3 V;
this nominal endpoint differs and does not establish silicon voltage accuracy.

Measured intermediate voltages, channel switching and repeatability checks
remain pending. The model is ideal and synchronous: noise, conversion latency,
factory calibration, ADC2 and continuous/DMA sampling are not validated.
Successful completion is not a claim of analog accuracy.

## Timer: public-driver test confirms a model gap

A new application uses unmodified public ESP-IDF `esp_timer_*`, `gptimer_*`
and FreeRTOS APIs on the original platform, without the ADC overlay.

- `esp_timer` create/start/stop/delete succeed. A requested 10,000 µs period
  produces 19 callbacks over 190,013 µs of firmware-reported elapsed time.
  Task delay returns. The requested task delay was 120 ms; the longer observed
  interval is not a latency/jitter qualification.
- GPTimer creation, callback registration, a 1 MHz APB counter, repeating
  50,000-count alarm, enable and start all return `ESP_OK`. No alarm callbacks
  occur; `gptimer_get_raw_count` does not return within two simulated seconds.
- PC 0x4037d334 resolves to IDF `timer_ll_trigger_soft_capture`,
  `timer_ll.h:194`. UPDATE bit 31 at 0x6001f00c stays set; interrupt RAW is zero.

The selected `Timers.ESP32C3_Timg` model stores main-timer/watchdog registers
and implements RTC calibration responses, but creates no running main timer
and exposes no alarm IRQ outputs. The public driver performs clock/reset and
timer setup; adding only a platform interrupt wire cannot resolve this gap.
Implement counting, snapshot completion, alarm/interrupt behavior and any used
watchdog behavior, then rerun public-driver tests. Initial hand acquisition can
use the verified `esp_timer` path in the meantime.

## Remaining hand-controller work

| Item | Next action / owner |
|---|---|
| ADC model integration | Simantic: integrate/release the ADC change; rerun without the temporary overlay |
| Acquisition firmware | Project: five flex channels, timestamps, filtering, validity and UART records |
| ENABLE | Project: public GPIO driver, debounce, held-at-boot and recovery tests; register-level GPIO7 input already passes |
| Motion sensors | Project: supply LSM6DS3TR-C/LIS3MDL register fixtures and test actual initialization, burst reads and errors on GPIO8/9 |
| Timing | Project: use `esp_timer` initially and measure deadlines; Simantic: complete TIMG if GPTimer/watchdog is required |
| Calibration/NVS | Project: implement and qualify persistence, integrity and fault handling |
| Watchdog recovery | Qualify the used driver/model and restart behavior; successful boot is insufficient |
| BLE and hub | Later controller stage: qualify the selected ESP stack and two simultaneous hand links |

The BME280 I2C fixture proves a bounded bus path, not the selected IMU driver.
Untested NVS/BLE behavior is not automatically a simulator defect. Sensor
stimulus, motion traces, controller logic and the integration interface remain
project-owned. Follow the [controller plan](../controller/simantic-plan.md) and
[full implementation checklist](../../README.md#full-implementation-checkpoints).
