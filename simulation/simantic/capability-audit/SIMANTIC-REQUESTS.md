# Simantic requirements — ESP32-S3 controller, then STM32H7 drone

**Updated September 17, 2026.** The only hand-controller platform is ESP32-S3.
The later drone target is STM32H743 (STM32H7). The project supplies sensor inputs,
controller logic, transport integration, dynamics and display.
See the [current readiness record](../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md)
for versions, expected/observed values and evidence limits.

## ESP-01 — Integrate the tested ADC1 one-shot implementation

The corrected register probe and full ESP-IDF v5.5.2 public-driver application
pass with [ADC PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168).
At test time it was unmerged; stock engine 0.5.7 still lacks conversion behavior.
Integrate the change and rerun the ten-channel/four-attenuation matrix without
the temporary overlay. Five flex inputs use ADC1 channels 0/1/3/4/5.
The original probe omitted a SENS clock enable; that test bug was corrected.

The model uses an ideal synchronous voltage curve. Measured-voltage accuracy,
noise, calibration and conversion timing remain unqualified. Continuous/DMA
sampling is not required for the initial hand firmware.

## ESP-02 — Complete GPTimer/TIMG behavior when required

Public driver clock/reset/configuration succeeds, but no alarm callbacks occur
and `gptimer_get_raw_count` stalls waiting for snapshot UPDATE to clear.
`Timers.ESP32C3_Timg`, selected by the S3 platform, only stores the main-timer
registers. Implement counting, capture completion, alarm flags, interrupts and
routing; qualify any required watchdog behavior separately.

SYSTIMER-backed `esp_timer` and FreeRTOS work. Use those for initial hand
sampling, then measure deadlines/jitter. TIMG does not block that first step.

## ESP-03 — Correct high-bank GPIO behavior

GPIO43 SET/readback fails and host injection reports pin 43 out of range in
the diagnostic. GPIO1/2/4/5/6/7 input tests pass. GPIO43 is reserved for UART0,
whose byte transport passes; full pin-matrix routing still needs validation.
Use the [ESP32 diagnostic record](esp32s3/README.md) for the bounded results.

## Controller qualification still required

- Project: exact LSM6DS3TR-C/LIS3MDL fixtures and actual I2C driver transactions.
- Project: GPIO7 public driver/debounce, filters, calibration and fault handling.
- Qualify NVS persistence and watchdog reset/recovery with the selected firmware.
- Later: selected ESP BLE stack with two simultaneous hands and hub freshness.
- Qualify the host command transport and receiver expiry; native USB requires
  separate driver/model tests if selected.

These untested paths are not automatically confirmed simulator defects.

## Later STM32H7 output requirements

### SIM-03 — STM32 TIM1 complementary PWM outputs

**Observed:** Kakute candidate M1/M2 on PB0/TIM1_CH2N and PB1/TIM1_CH3N produce
no edges with CC2NE/CC3NE and BDTR.MOE enabled. M3/M4 on TIM2 pass. A control
configuration using main-channel enable bits produces edges on the fixture,
localizing the defect to complementary/output-enable semantics. Backend logs
identify unhandled complementary-enable and MOE bits.

**Need:** correct complementary channel routing, enables, main-output gate and
polarity for these pins. Include disabled/reset states.

**Acceptance:** four firmware-generated PWM signals have the specified periods
and high times at the actual configured output pins. See [H7 tests](stm32h7/README.md).

**Alternative now tested:** four main-channel PWM routes PB3/PB10/PA0/PA2 emit pulses in a new diagnostic, avoiding the original complementary channels. This could reduce the initial virtual-drone requirements if we deliberately remap its firmware; it is not an ArduCopter remap pass or a correction to the original Kakute wiring. See [alternate PWM evidence](full-drone/README.md).

### SIM-04 — Request-paced timer → DMAMUX → DMA transfers

**Observed:** enabling the tested memory-to-peripheral DMA stream exhausts
NDTR and writes all four values to TIM2_CCR2 **before TIM2 is started**.
TIM2 DIER.UDE is reported unhandled. A memory-to-memory positive control passes.

**Need:** DMA transfers gated by the selected peripheral requests, correct
DMAMUX routing, timer update/compare requests and required circular/reload/IRQ
semantics. This is necessary if we select DMA-generated DShot; using PWM for an
initial virtual aircraft deliberately avoids that particular requirement.

**Acceptance:** NDTR/data stay unchanged without a request; each request moves
the correct element; timed output reproduces the encoded motor frame. Transfer
completion by itself is not a passing DShot test.


### SIM-07 — Preserve voltage precision in STM32H7 ADC conversion

**Observed:** the input getter preserves supplied microvolts, but the conversion
results have 1 mV granularity. Inputs 500/999 microvolts return zero; inputs
1000/1500/1650/1999 microvolts all return 20; 2000/2500 return 40. These match
integer-millivolt truncation before 16-bit conversion. At 1650 microvolts the
ideal 3.3 V, 16-bit result is about 33. Larger quarter/half/full-scale tests pass.

**Need:** retain sufficient precision through conversion, or explicitly expose
and document this approximation if fine-resolution ADC validation is excluded.
The user's input generator already supplies precise values. The internal
code-level cause has not been inspected.

**Acceptance:** sweep sub-millivolt and multi-millivolt inputs against the stated
resolution/reference and declared rounding rule. [Precision sweep](stm32h7/README.md)


## Later complete-drone qualification

The [extended ArduCopter run](full-drone/README.md) reaches IMU/FIFO startup and
vehicle-loop execution with explicit fixtures. Sensor scaling/timing, estimator
health, command input, configured motor outputs and sustained feedback remain
open. Drone implementation is deferred while the hand controller is built.
