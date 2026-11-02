# Simulation plan

The whole system runs in Simantic before anything is built. That means both hand
controllers, the hub and the drone's flight controller. Later the physical
controller replaces the simulated hands and hub one board at a time. The drone
stays simulated for good.

One rule holds throughout: **the drone on screen moves only because the simulated
flight controller's motor outputs moved it.** Nothing turns a gesture straight into
drone motion.

## What runs

```text
LEFT hand  ESP32-S3 ─┐                               real hand firmware (apps/hand)
RIGHT hand ESP32-S3 ─┤ BLE (one simulated medium)
                     └─> HUB ESP32-S3                real hub firmware (apps/hub)
                           │ UART0, one JSON command line per 20 ms
                           v
                     bridge: rc_link.py + gcs_peer.py (host side, Python)
                           │ MAVLink RC_CHANNELS_OVERRIDE every 20 ms, SERIAL1
                           v
                     ArduCopter 4.7.1 on an emulated flight controller:
                     Matek F405-Wing (STM32F405, default) or Pixhawk 6X (STM32H753)
                           │ motor PWM read from the timer compare registers
                           v
                     quad_plant.py: rigid-body quad X
                           │ IMUs, barometer (and on the F405 the SD card)
                           └─> back into ArduCopter
```

| Piece | What it is | Where |
|---|---|---|
| Hand, hub | The same bootloader, partition table and application binaries that will be flashed on the boards. Only the mask-ROM wrapper differs | `firmware/apps/hand`, `firmware/apps/hub` |
| Stand-in hand | A hand's BLE peripheral that sends packets a test script supplies, for exact hub inputs | `firmware/apps/replay` |
| ESP32-S3 model | Stock engine 0.6.6 platform plus one model candidate: RNG (renode-infrastructure #271, so a reset gives new session ids) | `simulation/simantic/model-candidates/` |
| Drone firmware | ArduCopter 4.7.1. Pixhawk 6X: built from the release commit with `BRD_IO_ENABLE 0` as its only built-in default, because no IOMCU is modelled and the stock release stops at boot without one. F405: the stock release, unmodified | `simulation/drone/pixhawk6x/build.sh`, `fetch_arducopter.sh` |
| Drone board | `PALMPILOT_DRONE=f405` (default): STM32F405 with the sim-fixtures Matek board. `h7`: mcu-lib Pixhawk6X with sim-fixtures' pixhawk6x board (three ICM-45686, BMP388, F-RAM, SD) | private sim-fixtures checkout in `tmp/` |
| Bridge | Turns the newest hub command into RC channels and sends them as a ground station would. Stops sending on an invalid command or when no fresh command has arrived for 100 ms, using its own clock | `simulation/drone/rc_link.py`, `gcs_peer.py` |
| Physics and sensors | Integrates the airframe from the four motor pulses and answers the flight controller's sensor bus reads | `simulation/drone/quad_plant.py`; H7 `imu45686_plant.py`, `fram_peer.py`; F405 `imu_plant.py`, `baro_plant.py`, `sd_card.py` |

`python3 firmware/tools/palmpilot.py system <script>` builds and starts all four
machines. `python3 firmware/tools/palmpilot.py drone <script>` starts the flight
controller alone, as in the laptop demo (`ControllerSim(hands=False)`).
`firmware/tools/controller.py` (`ControllerSim`) is the test-facing API.

The drone target is the **Matek F405-Wing (STM32F405)**, chosen for speed; the
Pixhawk 6X (STM32H753) stays selectable with `PALMPILOT_DRONE=h7`. On engine 0.6.6
both fly the same gesture flight and land, with the same estimate error (mean
0.95–1.07°, worst 2.6–3.0°; for each airframe the H7 and F405 means are within
0.01°). The four-machine system runs about 3.7× slower than real time with the F405
and about 11× with the H7. `ControllerSim.setup_drone` does each board's bench setup
over MAVLink.

## What a test controls

| Input | How it enters | Notes |
|---|---|---|
| Flex sensors | Voltage on each ADC1 channel, read by the firmware's own `esp_adc` driver | Calibrated mV within ±5 mV of the injected value. This is the model's contract and says nothing about silicon noise |
| Hand motion | Register-level LSM6DS3TR-C and LIS3MDL fixtures on I2C0 | No ODR timing, FIFO, interrupts or noise |
| ENABLE, CALIBRATE | GPIO7 level | |
| Exact BLE packets | `set <hex>`, `freeze`, `mute` on the stand-in hand's UART | S3-B |
| Drone sensors | Computed from the plant state. IMU noise follows the datasheet (`PALMPILOT_IMU_NOISE=0` turns it off) | No GPS, compass or battery model |

Renode resets injected ADC voltages and GPIO levels when a chip resets
(simantic-core#561). `harness.ExternalInputs` drives them again, as real sensors
would.

## Physics, in two steps

1. **Our own model first.** `quad_plant.py` is a provisional 1 kg, 5-inch-class quad.
   It uses ArduPilot's thrust curve (`MOT_THST_EXPO` 0.65, spin min/max 0.15/0.95),
   so ArduCopter's default hover estimate fits it.
   `python3 simulation/drone/test_quad_plant.py` checks it against closed-form
   results, with limits fixed before the first run: free fall with drag, hover,
   thrust curve, motor signs, coordinated tilt, rate integration, ground contact,
   terminal climb and ISA pressure. Currently 27/27.
2. **ArduPilot's physics as the final check.** `PALMPILOT_AIRFRAME=ardupilot` swaps in
   `ardupilot_frame.py`, a port of SITL's `SIM_Frame`/`SIM_Motor` default quad (3 kg,
   0.35 m). The same gesture flight then runs twice:
   - in Renode: real hands and hub, ArduCopter on the emulated F405;
   - in native ArduPilot SITL: `sitl_reference.py` replays the same hub commands
     through the same bridge mapping.

   The two are compared phase by phase. The last comparison agreed within about
   0.4° and 0.05 m/s. Acceptance limits for a qualifying run are not set yet.

ArduCopter settings every drone run needs, all sent over MAVLink by the host:

- `FRAME_CLASS=1`, `FRAME_TYPE=1` (quad X).
- `ARMING_SKIPCHK=0xFFFFE`, because the board model has no compass and no
  accelerometer calibration.
- `FLTMODE_CH=0`, because the bridge holds ch5 at 1500 µs.
- `RC1..4_MIN=1000`, `RC1..4_MAX=2000`. The default 1100–1900 inflates stick inputs
  by about 25%.
- AltHold (mode 2). Arming is a host action; ENABLE never arms.

## Stages

| Stage | What is simulated | Tests |
|---|---|---|
| S1 | One hand: acquisition, calibration, control state, motion, attitude, persistence, packet, watchdog | S1-A to S1-H |
| S2 | Both hands and the hub over BLE: link, mapping, interlocks, faults, reboot recovery, CALIBRATE | S2-A, S2-B |
| S3 | Controller into ArduCopter: hub commands arrive as RC, and expiry stops them | S3-A (real hands), S3-B (scripted packets checked against an independent model) |
| D2 | Closed loop: motor PWM → physics → sensors → ArduCopter, with gesture flight | `test_quad_plant.py`, `fly.py`, `sitl_reference.py` |
| D3/D4 | Physical hub on a laptop driving the simulated drone, with a 3D view | [demo plan](demo.md); not built yet |

The order of execution, the commands and the pass criteria are in the
[test plan](test-plan.md).

## Known limits and open items

- **Engine stall with four machines.** A lock-order deadlock between ESP32-S3 core
  threads can stop a run with the host idle. The fix is open as
  renode-infrastructure #340. On the stall tests, 19 of 205 stock runs stalled and
  0 of 204 with the fix. Until it ships, long or repeated four-machine runs need
  the locally built fixed engine, or serial execution (`PALMPILOT_SERIAL=1`), which
  is much slower.
- **Attitude estimate drift.** After a manoeuvre, ArduCopter's estimate is off by
  1–3° and the vehicle drifts slowly, by the same amount on the emulated F405 and
  H7. Native SITL does not show this. Ruled out so far: physics, sensor signs, scale
  and rate, dropped samples, noise, parameters, the CPU/FPU (ArduPilot's Replay tool
  reproduces the estimate exactly from the log) and, now, the flight-controller
  model. Still open.
- **H7 F-RAM framing.** The engine ends a scripted SPI device's transaction at every
  STM32H7 SPI end of transfer, so ArduPilot's parameter writes were lost on reboot
  (simantic-core#658, fix PR #659). `simulation/drone/fram_peer.py` keeps the F-RAM
  framed until the fix ships.
- **Runs are time-limited.** `palmpilot.py` stops a run that idles below 5% of a core
  for 120 s (the deadlock above) or that passes 60 minutes.
- **S2-B reset-to-invalid.** The time from a hand reset to an invalid command is
  bimodal, 120 or 160 ms, on both the stock and the fixed engine. The provisional
  limit is 150 ms. Whether to raise it is open.
- **Speed.** On an M4 laptop, fly.py's four machines run about 3.7× slower than real
  time with the F405 and about 11× with the H7. The demo simulates only the flight
  controller: the F405 alone runs flight at 1.47 s of wall time per simulated second
  (`demo_speed.py`, two runs, 2026-11-01), so the demo drone moves about 1.5× slower
  than real time. See [demo.md §4](demo.md#4-visualisation).
- **One BLE medium per simulation.** Scenarios with several separate BLE media did
  not link. This is not investigated, and nothing in the plan needs more than one.
- **Not modelled:** RF range or interference (the BLE medium is lossless), ADC noise,
  the GPIO matrix (SDA/SCL pin choice is untested), battery and power, GPS and
  compass, and the reset-reason hint after a panic (a C3 RTC_CNTL model gap).

A simulation PASS is evidence about the firmware against these models. It says
nothing about the physical boards, and it does not show that the drone could fly.

## Toolchain

`firmware/tools/env.sh` pins every path. ESP-IDF v5.5.2, the Xtensa compiler, the
Simantic engine, the platforms, the mask ROM, ArduCopter and the ArduPilot SITL
build all live in gitignored `tmp/`. None of it can be rebuilt from a clean
checkout. Do not delete `tmp/`. [CLAUDE.md](../CLAUDE.md) section 3 has the
details.
