# Requests for Simantic — PalmPilot runtime audit

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

> **September 17 follow-up:** see the [current hand-controller readiness record](../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

**Active controller changed to ESP32-S3 on September 16, 2026.** Use the [current ESP32/full-drone assessment](../../../docs/implementation-records/2026-09-16_esp32-full-drone-feasibility.md) first. **SIM-01, SIM-02, SIM-05 and SIM-06 below concern the retired nRF52840 design; they no longer block our controller.** SIM-03/SIM-04 remain relevant to the STM32 drone candidate. SIM-07 concerns ADC fidelity if that drone path uses it. The [ESP32 audit](esp32s3/README.md) and [extended drone tests](full-drone/README.md) contain the new runtime evidence.

## Active ESP32-S3 work

Target: `ESP32-S3-WROOM-1-N8R2`, CLI/engine 0.5.7. See the [ESP32 reproduction package](esp32s3/README.md) for exact source, model hashes, commands and assertion results.

### ESP-01 — Implement ADC conversion and channel stimulus

**Independently confirmed in the installed backend:** [ADC/input review](esp32s3/adc-review/README.md). SENS writes store register words; reads have no ADC conversion/DONE behavior. Read-only DONE/DATA incorrectly accept writes. No compatible per-channel analog input exists. The fresh CLI and SDK use the same backend assembly and reproduce the same firmware output; STM32 analog injection/conversion succeeds as a positive control. The earlier ADC probe did not inject explicit analog voltages, so it does not establish an accuracy failure.

The firmware selects the five ADC1 channels used by the hands (0, 1, 3, 4, 5). Control-register readback works, but conversion DONE never arrives and data remain zero in the bounded RTC-path test. The APB SARADC region is plain mapped memory rather than a converter.

Implement the ESP32-S3 ADC path required by the pinned ESP-IDF driver, conversion completion/data and channel selection, with a documented per-channel voltage API. Include attenuation/calibration behavior or explicitly document supported approximations. We supply voltages and sensor scenarios. Acceptance must use the real ADC driver across GPIO1/2/4/5/6, not digital pin reads or application-variable injection.

First implement **ADC1 RTC one-shot in SENS**, including read-only data/status semantics. Replacing the APB SARADC memory region alone will not implement this separate path. Continuous/DMA conversion is not a prerequisite for the first hand. The linked review defines the input and driver acceptance tests.

### ESP-02 — Qualify/fix TIMG0 snapshot and alarm behavior

The follow-up inspected the loaded `ESP32C3_Timg` implementation used by the S3 model: it stores registers and supplies RTC calibration responses, without the tested general-purpose timer counting/snapshot/alarm behavior. This is now an implementation-backed gap, not solely an ambiguous timeout. Required interrupt routing and the production framework's timer/watchdog behavior still need qualification after implementation.

The tightened TIMG0 probe follows the HAL divider-reset and UPDATE-wait sequence. Enable/configuration readback passes, but UPDATE bit31 stays set and the alarm flag remains zero. Since the snapshot never becomes ready, its zero count is not proof that the underlying counter never advances. The separate SYSTIMER snapshot/advancing-counter test passes. Investigate the exact reproduction, then qualify timer/interrupt/watchdog paths used by the actual ESP-IDF build. Do not interpret this as every timing source being absent.

### ESP-03 — Correct ESP32-S3 GPIO width and routing

GPIO43 output/readback fails, and host input injection reports GPIO43 out of range. High-bank GPIO input offset 0x40 is unhandled in the tested model. Low-bank GPIO1/2/4/5/6/7 injection succeeds. Correct S3 high-bank width/register semantics and verify GPIO matrix routes used by UART/I²C as part of board fidelity. A UART model's byte stream can pass while physical pin routing remains unqualified.

### ESP validation request — Production framework and two BLE peers

Bare-metal Xtensa diagnostic boot, UART echo, selected GPIO, SYSTIMER and repeated-start I²C pass. Full ROM/bootloader/ESP-IDF application boot, selected BLE stack with two simultaneous peers, NVS persistence and watchdog recovery have not been qualified. Provide or qualify a pinned reproducible ESP-IDF application image through these paths; untested stack compatibility is not an established radio defect.

## Earlier Nordic and STM32 audit requests

Tested release: **CLI/engine 0.5.7; SDK 0.3.1; macOS arm64**. Models:
`NRF52840QIAA` and `STM32H743ZI`; exact hashes and repro fixtures are in the
[audit groups](README.md). These requests come from runtime probes. They are
not a request to build our sensor-input generator, physics, UI or integration
application; those remain project-owned.

## 1. Historical nRF52840 hand-controller driver requests

### SIM-01 — Add/register the nRF52840 SAADC

**Observed:** the supplied platform has no SAADC. ENABLE reads zero, and
STARTED/CALIBRATEDONE do not arrive in the diagnostic.

**Need:** SAADC at `0x40007000`, input selection, conversion configuration,
START/SAMPLE/STOP/calibration tasks and events, EasyDMA result writes and counts,
and the interrupt/event behavior the selected driver uses. Provide a documented
way to assign each AIN voltage; we will generate those voltages ourselves.

**Acceptance:** run our actual driver sequence across the five finger inputs
and battery input, verify result values, completion order, event clearing and
DMA guard bytes. Details are in the [SAADC handoff](../../../docs/controller/simantic-saadc-handoff.md)
and [nRF runtime evidence](nrf52/README.md).

### SIM-02 — Complete TWIM/EasyDMA transaction lifecycle

**Correction:** TWIM is partially implemented in the shipped engine. Basic DMA
transfer/count and NACK/STOP handling exist; a wholly new I2C controller is not
the required change.

**Observed:** `TXSTARTED`, `LASTTX`, `RXSTARTED`, `LASTRX` and `SUSPENDED` stay
zero in the tested transactions. The SUSPEND/RESUME repeated-start register read
returns `0x00` where the fixed fixture returns `0x60` using STOP-separated
transactions. RXSTARTED/TXSTARTED reads produce unhandled-offset warnings.

**Need:** implement the relevant task/event/SHORTS state machine, repeated-start
and SUSPEND/RESUME behavior, including EasyDMA boundary/count semantics. Our
Adafruit Wire driver polls these events, so partial data movement is insufficient.

**Acceptance:** firmware performs write-register-pointer + repeated-start read,
multibyte RX with guard bytes, write/readback, NACK, STOP and event/IRQ clearing.
Use [the nRF probe](nrf52/README.md) and then the real Adafruit Wire driver.

## 2. Required for the selected drone output path

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

## 3. Historical Nordic USB/reset requests and STM32 ADC fidelity

### SIM-05 — Complete nRF USBD transfers used by CDC/TinyUSB

**Observed in direct register/host-pipe probes:** USB power-ready/enable events
and an exact 23-byte IN payload work; no compiled USB driver is qualified here.
`EPIN[2].AMOUNT` remains zero instead of 23. Host `ConnectEndpointWrite()` returns
null for every bulk OUT endpoint even after EPOUTEN configuration.

**Need:** correct transfer counts, usable bulk OUT path and the remaining
endpoint/event behavior needed by the selected USB stack. These tests do not yet
establish full enumeration or CDC class behavior.

**Acceptance:** real TinyUSB CDC enumeration, host-to-device and device-to-host
data, exact DMA counts and endpoint completion events. UART/TCP already works
as an integration transport while this is resolved. [USB evidence](transport/README.md)

### SIM-06 — Reset, GPIOTE and flash semantics

The nRF tests also reproduce:

- Watchdog reset occurs, but RESETREAS reports `0x1` rather than watchdog/DOG
  `0x2` in the isolated case.
- GPIOTE task-mode OUTINIT=0 does not clear a previously-high output.
- NVMC permits flash writes while in read-only mode and permits programming
  zero bits back to one without erasing.

These can give false confidence in recovery and calibration-storage tests.
Correct the semantics and preserve the positive cases for ordinary erase/write,
event clearing and reset. [nRF evidence](nrf52/README.md)

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

## 4. Validation requests, not established missing features

- **Historical nRF two-link/stack test:** one real Zephyr link
  passes. Three uniquely identified nodes start, but the supplied central fixture
  selects only one peripheral. Provide/run a central supporting at least two
  simultaneous peers; test S140/Adafruit SoftDevice if that remains our firmware
  choice for another project. Current results do not establish a BLE engine defect, nor do they qualify the new ESP32 BLE stack. ESP32 needs a separate two-peer test.
- **Complete ArduCopter operation:** the [extended run](full-drone/README.md) now reaches IMU initialization, FIFO transactions and repeated vehicle-loop execution with explicit fixtures. The optional OSD is rejected normally using a pulled-high absent-device response; no execution path is patched. Next qualify sensor scaling/timing, estimator health, command input, configured motor outputs and sustained feedback. These remaining tests are not a claim that the flight firmware cannot run.

## 5. Existing integration capabilities and useful API improvements

Already runtime-tested: controlled virtual-time steps; GPIO input injection;
UART DMA and TCP command/response; timestamped UART/frames; Python-scripted SPI
and I2C slaves; mutable input-provider data; H7 ADC microvolt injection; and
GPIO output hooks through the underlying Renode API.

We can build the integration layer using these. A documented stable SDK surface
for per-channel voltage input, scripted-bus attachment/state, and timestamped
pin transitions would reduce version-specific reflection. This is an API
maintenance request, not a request for Simantic to build our physics or UI.
