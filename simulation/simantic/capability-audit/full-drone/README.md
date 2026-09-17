# Full-drone feasibility follow-up

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

This audit runs the **official ArduCopter 4.7.1 KakuteH7 ELF** in Simantic engine 0.5.7, using SDK 0.3.1 and the retrieved `STM32H743ZI` catalog model. It also measures a possible alternative motor-output mapping. It does **not** demonstrate a complete drone simulation or a qualified KakuteH7 board.

The controller's ESP32 migration is separate work. These tests preserve the earlier [STM32H7 capability audit](../stm32h7/README.md).

## Measured progress

**The unmodified flight firmware reached its vehicle loop.** Adding an explicit absent-OSD SPI fixture allowed normal initialization to proceed through barometer calibration and inertial-sensor startup. No firmware code or CPU return path was changed.

| Milestone | Virtual time / observation |
|---|---:|
| `Copter::init_ardupilot` | 3.660215 s |
| Optional OSD rejected; `Copter::init_rc_in` entered | 3.665531 s |
| `Copter::init_rc_out` | 3.697090 s |
| `AP_GPS::init` | 5.704167 s |
| `Compass::init` | 5.722718 s |
| `AP_Baro::calibrate` | 5.846175 s |
| Invensense v3 `hardware_init` / `check_whoami` | 7.481822 / 7.481823 s |
| First IMU `read_fifo` | 7.572610 s |
| First `AP_Vehicle::loop` | 8.099245 s |
| At 8.25 s | 1,345 FIFO function entries; 62 vehicle-loop entries |

The run captured **2,892 ICM42688P SPI frames**, including WHO_AM_I = `0x47` and repeated 16-byte FIFO payload reads, plus 319 barometer I2C frames. The loaded `Sensors.ICM42688P` backend was used; the barometer was an explicitly static SPA06-shaped register fixture. All sampled CFSR/HFSR fault registers were zero. The median measured interval between the 62 vehicle-loop entries was about 2.50 ms; this short window is not a scheduler qualification.

The requested 30 virtual seconds stopped at the 55-second wall budget after 8.25 virtual seconds (55.09 wall seconds). This is instrumented-run performance, not a real-time guarantee.

UART2 emitted CRC-valid MAVLink 2 HEARTBEAT frames. They identify a quadrotor using ArduPilot, in `MAV_STATE_BOOT`, with the armed flag clear. **Those heartbeats preceded vehicle-loop entry**; a ready/healthy post-startup heartbeat was not observed before the bound. UART3 also emitted GPS autodetection/configuration commands. Values and raw frames are in [results.json](results.json), interpreted using the [official MAVLink definitions](https://mavlink.io/en/messages/common.html#HEARTBEAT).

Only initial motor pin levels and a falling transition on PB3/PB10 at 8.117534 s were observed. No arming command was sent, and no stock-firmware motor pulse train or commanded output change was demonstrated. That is an untested output/arming boundary, not a new claim that ordinary PWM fails.

This establishes real firmware startup, actual sensor-driver bus activity, and repeated vehicle-loop execution. It does not establish valid sensor scaling or physics, estimator health, motor control, arming, or closed-loop flight. SPI/DMA/cache warnings remain; the observed successful path does not qualify every peripheral mode.

### Optional OSD gate

In an initial 5-second run without the absent-OSD fixture, `init_rc_in`, motor allocation, inertial-sensor initialization, and the vehicle loop had not been reached. The first uncompleted observed stage was the optional MAX7456 OSD initialization on SPI2. No MAX7456 was attached.

The pinned [MAX7456 driver source](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_OSD/AP_OSD_MAX7456.cpp) resets the device, waits 1 ms, and reads its mode register. A zero response starts programming up to 256 font characters. Each character's busy poll can wait 10,000 × 15 ms. Thus a short run with a default zero SPI response can falsely appear to find a device and enter lengthy optional initialization.

`absent_spi.py` is an explicit **negative-probe fixture**: its MISO returns `0xFF`, representing an absent optional device with a pull-up. It is not a MAX7456 implementation. `--absent-osd` succeeded: actual SPI frames show reset `00 02` → `FF FF` and mode-register read `80 00` → `FF FF`. The unmodified driver rejected the optional device, skipped font programming through its normal conditional, and continued. No CPU return value or code path was patched.

## Four alternate PWM outputs

A separate bare-metal ELF drove the candidate board's M3–M6 routes using ordinary main timer outputs:

| Candidate output | Route | Measured pulse width |
|---|---|---:|
| M3 | PB3 / TIM2 CH2 | 1100 µs |
| M4 | PB10 / TIM2 CH3 | 1300 µs |
| M5 | PA0 / TIM5 CH1 | 1500 µs |
| M6 | PA2 / TIM5 CH3 | 1700 µs |

Each route produced five complete observed pulses in 120 ms. The GPIO state-change callbacks provide the measurements. All widths matched within 0.01 µs. A nominal 20,000 µs timer period measured **19,999 µs**, so exact period fidelity failed by one timer tick. The report keeps that discrepancy explicit; feasibility assertions allow 1.01 µs period error.

This suggests a first virtual vehicle could remap four motors to M3–M6 and use ordinary PWM. The actual ArduPilot parameter mapping, configured timer clocks, arming behavior and closed-loop output remain to be tested. This does not resolve the earlier complementary TIM1 output or DMA-paced DShot failures.

## Reproduce

Run from the repository root. Prerequisites are the previously retrieved model and official ELF, installed engine 0.5.7/SDK, and `arm-none-eabi-gcc`/`nm` on PATH. Commands use the same ignored runtime directory as the earlier audit. `fetch_inputs.py` verifies existing inputs or restores missing ones using the authenticated SDK model resolver and official firmware URL. It refuses changed hashes. Its existing-cache path was checked; a fresh network restoration was not needed in this run. The model-render helper is from the pinned SDK 0.3.1 implementation.

```sh
export SIMANTIC_HOME="$PWD/tmp/simantic/runtime"
export SIMANTIC_TELEMETRY=0
.venv-simantic/bin/python simulation/simantic/capability-audit/full-drone/fetch_inputs.py
.venv-simantic/bin/python simulation/simantic/capability-audit/full-drone/run_probe.py --seconds 5 --name imu-baro-stage --imu --baro
.venv-simantic/bin/python simulation/simantic/capability-audit/full-drone/run_probe.py --seconds 30 --name osd-absent --imu --baro --absent-osd
.venv-simantic/bin/python simulation/simantic/capability-audit/full-drone/pwm_alternative.py
python3 simulation/simantic/capability-audit/full-drone/summarize.py
```

The runtime loop checks a 55-second wall budget after each 0.25-second virtual step; the final step can exceed the budget slightly. Raw platform files, frames, logs and timing evidence remain in `tmp/simantic/audit/full-drone/`. Compact results and source/model/ELF hashes are checked in here. C++ entry points use CPU address hooks resolved from `nm -C` because Simantic's public symbol-name tracer did not resolve the tested C++ names. These hooks observe execution only.

## Sources and remaining qualification

The ELF was fetched from the [official KakuteH7 stable directory](https://firmware.ardupilot.org/Copter/stable/KakuteH7/). Its SHA-256 pins the tested artifact despite that URL being mutable. Target commit: `dbe792162d06cab66c3475fd5556bf7a120f119e`.

- [KakuteH7 board definition](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_HAL_ChibiOS/hwdef/KakuteH7/hwdef.dat): MCU configuration and motor/sensor routes.
- [Copter startup sequence](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/ArduCopter/system.cpp): ordering of OSD, RC, motor, barometer calibration and inertial startup.
- [SPL06/SPA06 driver](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_Baro/AP_Baro_SPL06.cpp): the narrow barometer fixture contract.
- [Invensense v3 driver](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_InertialSensor/AP_InertialSensor_Invensensev3.cpp): ICM42688P register/FIFO contract. Startup and repeated reads passed; sample scaling, timing and estimator use still require validation.

A complete result still needs controlled sensor-value and timing validation, healthy estimator startup, validated ArduPilot motor mapping, telemetry/control input, arming and failsafe behavior, and a causally connected motor → user-owned physics → sensor loop. Native model names alone do not establish any of these.
