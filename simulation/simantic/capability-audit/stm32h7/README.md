# STM32H7 runtime capability audit

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

Tested September 16, 2026 with Simantic CLI/engine **0.5.7**, Python SDK
**0.3.1**, and the retrieved `STM32H743ZI` model. This is a candidate MCU
configuration for the virtual drone, not a complete Kakute board model.

**Result: basic firmware and several I/O paths work. Two reproduced timer/DMA
limitations prevent claiming support for the historical four-motor output path.**
The official ArduCopter ELF also reaches `main`, but a working flight-control
loop has not been demonstrated.

See [machine-readable results](results.json), the
[diagnostic transcript](firmware-transcript.txt), and the
[main-output control transcript](main-output-control-transcript.txt).
Source, model and ELF hashes are retained in the results.

## What actually ran

| Check | Observed result | Scope |
|---|---|---|
| Cortex-M7 and hardware floating point | Pass: calculated floating-point result | Minimal bare-metal ELF, not full application coverage |
| SysTick and TIM2 interrupt delivery | Pass: 70 ticks at approximately 70 ms; seven TIM2 update interrupts | Reset SYSCLK uses 64 MHz for SysTick; timer and DWT clocks are separately declared by the model |
| UART3 | Pass: firmware output and host-injected `A` command | Register-level transmit/receive; no USB or CRSF claim |
| Kakute candidate M3/M4 | Pass: PB3/PB10 GPIO loopback captures 1500/1750 µs pulses, approximately 10 ms periods | TIM2_CH2/CH3; output edges reach separate GPIO inputs |
| Kakute candidate M1/M2 | **Fail: zero edges** with TIM1 complementary outputs enabled | PB0/TIM1_CH2N and PB1/TIM1_CH3N |
| DMA memory-to-memory | Pass: four words copied in AXI SRAM | Positive control; does not establish peripheral pacing |
| Timer-paced DMA | **Fail: transfer completed before timer start** | DMAMUX request 22, DMA1 stream 0, TIM2 update to CCR2 |
| SPI4 | Pass: transmitted `0xA5`, received `0xA5` | Attached `SPI.SPILoopback` fixture; one-byte controller transaction |
| I²C1 | Pass: register write, repeated start, read and AUTOEND | Attached `I2C.BME280` at `0x76`, identity read `0x60` |
| ADC1 | Pass at 0, 0.825, 1.65 and 3.3 V | Channel 10, single software-triggered conversion; codes 0, 16384, 32768, 65535 |
| Official ArduCopter 4.7.1 | Partial boot: clock initialization, HAL, ChibiOS and `main` reached | Two virtual seconds; no aircraft sensor/SD slaves attached |

The BME280 is a known bus-test fixture, **not a substitution for the proposed
SPA06**. SPI and I²C results establish controller transactions without depending
on the user's future sensor models or integration application.

## Confirmed Simantic work

### 1. TIM1 complementary-output and output-enable semantics

The firmware sets `CC2NE`, `CC3NE`, complementary polarity and `BDTR.MOE`.
The expected PB0/PB1 pulses never appear. Backend warnings explicitly identify
`CC2NE`, `CC3NE` and `MOE` as unhandled.

A separate control binary enables the main `CC2E`/`CC3E` outputs. The same GPIO
routes then produce inverted pulses, proving that those loopback routes can
carry timer output. Enabling the main channels is a diagnostic control; it is
not presented as a valid fix for the board's complementary motor outputs.

### 2. Timer request generation and paced DMA

The correct DMAMUX request ID for TIM2 update is 22. The firmware prepares four
words and enables DMA while the timer is stopped. Before `TIM2.CEN` is set,
`NDTR` is already zero and `CCR2` already contains the last word. Backend logs
also identify `DIER.UDE` as unhandled.

This must be resolved before using a transfer-complete flag as evidence of
DShot waveform timing. The audit does not generate or decode a DShot frame;
it tests a prerequisite that currently fails. Timer compare requests, DMA
bursts, bidirectional DShot and ESC telemetry remain unqualified.

## Working stimulus and observation APIs

The loaded engine provides these mechanisms even though the convenient Python
session wrapper does not expose every operation:

- Locate the public runtime machine through
  `EmulationManager.Instance.CurrentEmulation.Machines`, then use
  `machine["sysbus.adcM1S2"]`.
- `IADCExtensions.SetVoltage(adc, UInt32(microvolts), Int32(channel))` changes
  the actual ADC model input. The firmware then triggers conversion and reads
  the result; the host does not inject an already converted ADC count.
- SPI and I²C transactions appear in `Sim.frames()` with virtual timestamps.
- `Sim.send_bytes()`, UART records, memory reads, model logs and symbol traces
  were exercised by these diagnostics.
- `STM32_Timer.Connections` exposes GPIO output objects. This audit observes
  motor outputs through explicit GPIO loopbacks and firmware timestamps.

A follow-up ten-point sweep confirms a precision limitation in the observed
conversion path: all results match truncating the input to integer millivolts
before conversion. `GetVoltage` retained every input exactly in microvolts, so
the discrepancy occurs after stimulus storage. The model source was not
inspected to assign a code-level cause.

| Input µV | Observed code | Ideal 16-bit code at 3.3 V |
|---:|---:|---:|
| 0 | 0 | 0 |
| 500 | 0 | 10 |
| 999 | 0 | 20 |
| 1000 | 20 | 20 |
| 1500 | 20 | 30 |
| 1650 | 20 | 33 |
| 1999 | 20 | 40 |
| 2000 | 40 | 40 |
| 2500 | 40 | 50 |
| 10000 | 199 | 199 |

The earlier zero/quarter/half/full-scale checks remain passed. Fine-resolution
ADC fidelity is not established. Rerun `adc_precision_probe.py` with the same SDK
environment to reproduce this bounded 0.12-second virtual run. ADC scan, DMA,
oversampling, calibration, analog settling and fault behavior need separate
checks if the application uses them.

SPI logs also mark software chip-select fields `SSM` and `SSI` unhandled.
The loopback result does not qualify external chip-select, sensor data-ready,
FIFO, interrupt or DMA behavior.

## Official flight-firmware boot

The official `KakuteH7` ArduCopter **4.7.1** ELF, commit
`dbe792162d06cab66c3475fd5556bf7a120f119e`, loads at its native application
address **0x08020000**. Simantic inferred that vector address correctly.
The trace reaches `Reset_Handler`, `__early_init`, `stm32_clock_init`, `halInit`,
`chSysInit`, then `main`. At the final two-second sample, fault registers remain
zero and PC resolves to ChibiOS `__idle_thread`.

An idle-thread sample is not proof of a stalled system. There was no UART3 text.
Repeated SPI1/SD, DMA, clock/cache/flash and ADC3 sequence warnings remain;
peripheral attachment and isolated follow-up are necessary to interpret them.
No sensor initialization, arming, estimator, flight loop or motor output from
this stock firmware is qualified by this boot check. No actual ICM-42688-P,
SPA06, GNSS, compass or SD-card model was attached to that run.

## Reproduce the diagnostics

From the repository root, with the previously downloaded model and SDK engine:

```sh
python3 simulation/simantic/capability-audit/stm32h7/build.py
python3 simulation/simantic/capability-audit/stm32h7/run_cli.py
SIMANTIC_HOME="$PWD/tmp/simantic/runtime" SIMANTIC_TELEMETRY=0 \
  .venv-simantic/bin/python simulation/simantic/capability-audit/stm32h7/sdk_adc_probe.py
```

The builder accepts `--model PATH`. It copies the source model into an audit
fixture and appends four GPIO wires, an SPI loopback and the known I²C device.
It does not change the retrieved source model or Simantic. Two one-second CLI
runs have independent 30-second wall-clock bounds. Exit zero means the process
completed; check the named PASS/FAIL assertions and results.

For the optional stock-firmware boot check, obtain `arducopter.elf`,
`firmware-version.txt` and `git-version.txt` from the
[official KakuteH7 directory](https://firmware.ardupilot.org/Copter/stable/KakuteH7/)
under `tmp/simantic/audit/stm32h7/ardupilot/`, then verify its version and SHA-256
against `results.json`. The stable directory can change. Run
`ardupilot_boot_probe.py` with the same SDK environment; it takes at most twenty
0.1-second steps and stops scheduling new steps after 20 wall-clock seconds.
The recorded run was additionally enclosed by a 30-second subprocess timeout.

After all recorded runs exist:

```sh
python3 simulation/simantic/capability-audit/stm32h7/summarize.py
```

The summarizer checks expected passes, the reproduced failures, control-case
results, ADC observations and boot milestones before rewriting compact evidence.
Raw CLI/SDK traces and downloaded binaries remain under the ignored `tmp/`
directory. No full project firmware or Simantic fix is included.

## Register and board references

- [Pinned KakuteH7 hardware definition](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_HAL_ChibiOS/hwdef/KakuteH7/hwdef.dat): candidate motor pins and boot layout.
- [ST DMA request definitions](https://github.com/STMicroelectronics/stm32h7xx-hal-driver/blob/master/Inc/stm32h7xx_hal_dma.h): TIM2 update request 22.
- [Current project drone scope](../../../../docs/drone-simulation.md): a working MCU-to-actuator-to-dynamics feedback loop is still required.
