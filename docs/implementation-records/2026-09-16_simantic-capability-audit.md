# Simantic capability audit — September 16, 2026

**Evidence type:** compiled diagnostic MCU simulation, stock firmware boot and
runtime interface probes. **Milestones informed:** S0, S2/S3 transport and D1.
**Overall result:** partial support with reproducible failures. No complete
controller or drone milestone is accepted by this record.

## Environment and ownership

CLI/engine 0.5.7, SDK 0.3.1, ARM GCC 16.2.0, macOS arm64. The SDK engine was
downloaded into ignored project runtime storage and successfully loaded.
Authentication had already been completed. Test sources and individual records
retain model, firmware, fixture and source hashes.

The user will provide flex/motion inputs and the integration/dynamics/display
application. We tested the simulator mechanisms needed to connect those inputs
and observe outputs. Fixed bus fixtures here do not implement project sensors.

## Runtime findings

| Area | Observed result | Evidence |
|---|---|---|
| nRF CPU/UARTE/GPIO/clocks/timers/IRQ/PPI | Narrow positive tests pass; specific GPIOTE initialization issue remains | [nRF](../../simulation/simantic/capability-audit/nrf52/README.md) |
| nRF SAADC | Missing from tested platform; no enable/start/calibration completion | [nRF](../../simulation/simantic/capability-audit/nrf52/README.md) |
| nRF TWIM | Partly working DMA and STOP-separated transfers; driver-required start/last/suspend events and repeated-start path fail | [nRF](../../simulation/simantic/capability-audit/nrf52/README.md) |
| nRF watchdog/NVMC | Reset and ordinary programming work; reset-reason and flash protection/bit semantics fail | [nRF](../../simulation/simantic/capability-audit/nrf52/README.md) |
| H7 CPU/FPU/SysTick/timer interrupts | Pass in bare-metal diagnostic | [H7](../../simulation/simantic/capability-audit/stm32h7/README.md) |
| H7 PWM | Candidate M3/M4 pass; TIM1 complementary M1/M2 fail | [H7](../../simulation/simantic/capability-audit/stm32h7/README.md) |
| H7 DMA | Memory-to-memory passes; peripheral transfer runs before timer requests and fails pacing test | [H7](../../simulation/simantic/capability-audit/stm32h7/README.md) |
| H7 SPI4/I2C1/ADC | Fixture bus transactions and quarter/half/full-scale ADC input tests pass; precision sweep exposes 1 mV conversion granularity | [H7](../../simulation/simantic/capability-audit/stm32h7/README.md) |
| Stock ArduCopter 4.7.1 KakuteH7 | Reaches `main()` in bounded 2 s virtual run without hard fault; no complete sensor/control-loop claim | [H7](../../simulation/simantic/capability-audit/stm32h7/README.md) |
| BLE | Real Zephyr connection and GATT notifications pass; concurrent two-link/SoftDevice qualification remains open | [Transport](../../simulation/simantic/capability-audit/transport/README.md) |
| UART TCP | Host command and firmware response pass | [Transport](../../simulation/simantic/capability-audit/transport/README.md) |
| nRF USB | Direct register/host-pipe probes: Ready and IN payload/event pass; IN AMOUNT and bulk OUT path fail. No compiled USB-driver pass | [Transport](../../simulation/simantic/capability-audit/transport/README.md) |
| User-owned scripted bus inputs | Firmware I2C/SPI responses and mutable Python-provider boundary pass | [SDK](../../simulation/simantic/capability-audit/sdk/README.md) |
| Time and output observation | Explicit stepping, GPIO injection, UART records and underlying-engine GPIO output hooks pass within tested limits | [SDK](../../simulation/simantic/capability-audit/sdk/README.md) |

## What changed from the planning-only assessment

The earlier public-source reading underestimated the shipped TWIM and USB
implementations. TWIM is **incomplete, not entirely absent**; USB READY and an
IN transfer are implemented. The actual engine results supersede those guesses.
Conversely, timer and DMA class presence did not establish correct motor-output
behavior; direct timed tests found specific failures.

The engine already supports scripted SPI/I2C input devices and lower-level
output observation. Those facilities allow the project to own sensor data and
co-simulation code. A stable SDK wrapper would help but is not a prerequisite to
starting that adapter work. nRF SAADC remains a required model addition.

## Handoff and next checks

Use [SIMANTIC-REQUESTS.md](../../simulation/simantic/capability-audit/SIMANTIC-REQUESTS.md)
as the concrete vendor handoff. Prioritize SAADC and TWIM for the hand controller;
fix complementary PWM and request-paced DMA for the selected drone output path;
qualify USB if using the production USB stack in simulation. Keep firmware-stack
and two-link BLE tests distinct from confirmed model defects.

After fixes, run the retained probes against the new engine/model hashes, then
the chosen production drivers and full firmware. Physical calibration, RF,
power behavior, electrical timing and wearable fit remain physical tests.

## Limits

- No complete hand firmware, exact motion sensor driver, two-hand hub application,
  Adafruit SoftDevice application or full TinyUSB CDC stack was qualified.
- H7 is the candidate STM32H743ZI MCU configuration, not an exact validated
  Kakute board replica. Stock application startup is not stable flight control.
- No ESC firmware, physics, renderer, full sensor-feedback loop or physical
  hardware was implemented/tested here. These are project work, not automatic
  consequences of MCU support.
- The GPIO hook test does not establish sub-microsecond output timing fidelity
  or DShot decoding accuracy. UART trace records are line-buffered.
- Library configuration-lock sandbox errors were environmental and resolved;
  they are not counted as emulation failures.
