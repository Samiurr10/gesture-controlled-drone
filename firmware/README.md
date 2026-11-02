# PalmPilot firmware workspace

Hand and hub firmware, and the harness that builds and simulates it.
Constraints and the pin map: [`CLAUDE.md`](../CLAUDE.md). The order to run the
tests in: [test plan](../docs/test-plan.md). What the simulation covers:
[simulation plan](../docs/simulation.md).

## Layout

```
firmware/
  tools/env.sh        pinned toolchain paths, single source of truth
  tools/palmpilot.py  build / pack / sim driver
  tools/harness.py    reusable Simantic wrapper (importable as `harness`)
  tools/controller.py both hands + hub (+ drone) as one simulation: ControllerSim
  tools/selftest.py   end-to-end chain check against the ADC reference app
  apps/               ESP-IDF projects: hand (left/right), hub, replay
  tests/              simulation suites S1-S3 and run_all.sh
  probes/             engine-defect reproducers, drone flight scripts
```

Build output goes to `tmp/palmpilot/<app>/` and is gitignored.

## Verify the toolchain

Run this first in any new session, and after touching anything under `tmp/`:

```sh
python3 firmware/tools/palmpilot.py run \
  simulation/simantic/hardware-validation/esp32s3-adc \
  firmware/tools/selftest.py
```

Expected: **8/8 checks passed**, with raw counts 186/372/558/744/930 at
attenuation 3 on GPIO1/2/4/5/6.

## Commands

```sh
python3 firmware/tools/palmpilot.py env            # show resolved pinned paths
python3 firmware/tools/palmpilot.py build <app>    # idf.py build
python3 firmware/tools/palmpilot.py pack  <app>    # merge_bin + ROM wrapper
python3 firmware/tools/palmpilot.py sim   <app> <script> [args...]
python3 firmware/tools/palmpilot.py run   <app> <script> [args...]
```

`<app>` is an ESP-IDF project directory, resolved against `firmware/apps/` or
taken as a path. `pack` prints the app-ELF and sim-ELF SHA-256 — record both in
any test record.

The physical board and the simulator run the **same** bootloader, partition
table and application binaries; only the mask-ROM wrapper differs. Preserve
that property, because it is what lets a bench result and a simulator result be
compared at all.

## Writing a simulation script

Scripts run under `.venv-simantic/bin/python` with `firmware/tools` on
`PYTHONPATH` and `PALMPILOT_SIM_ELF` / `PALMPILOT_OUT` set.

```python
from harness import FLEX, PalmPilotSim

with PalmPilotSim() as sim:
    sim.wait_ready()
    sim.set_flex_uv("thumb", 200000)        # microvolts, through the modeled ADC
    sim.set_enable(True)                    # GPIO7, active low
    mark = len(sim.stream)
    sim.send_line("read 0 3 4")
    sim.wait_for_type("end", since=mark)
    print(sim.records(mark))
```

`uart.txt` and `logs.json` are always written to the output directory, even on
failure.

## Harness behavior worth knowing

The wrapper encodes these findings so they are not rediscovered:

- **One simulator model candidate loads by default** (`env.sh`): RNG
  (renode-infrastructure #271), from `simulation/simantic/model-candidates/`. Set
  `PALMPILOT_RNG_OVERLAY=` (empty) to run the engine's own model.
- **Runs are time-limited.** `palmpilot.py` stops a simulation that stays under 5% of a
  core for `PALMPILOT_STALL_S` (120 s), saving the engine's stacks to
  `stall-stacks.txt`, or that passes `PALMPILOT_MAX_WALL_S` (3600 s).
- **The drone board** is `PALMPILOT_DRONE=f405` (Matek F405-Wing, default) or `h7`
  (Pixhawk 6X, about 3× slower to simulate).
- **`palmpilot.py drone <script>`** runs the flight controller without the three
  ESP32-S3 machines (`ControllerSim(hands=False)`), as the laptop demo will.
- **ADC1 is upstream since engine 0.5.14** (PR #168), in its calibrated-state
  mode: raw counts are die-specific, so tests assert calibrated millivolts.
- **`Sim.read_uart` is unreliable** with the SDK — it duplicates
  and interleaves fragments. The harness captures the Renode `CharReceived`
  event instead. Assert against `sim.records()`, never `read_uart`.
- **ADC injection is not in the SDK.** `set_flex_uv` / `set_channel_uv` go
  through Renode interop (`IADCExtensions.SetVoltage`).

`ADC_MV_TOLERANCE` (±5 mV) bounds the calibrated millivolts against the
injected voltage. Matching it validates the model's calibrated contract and
nothing about silicon: no noise, no conversion latency, not the bench board's
own eFuse.

## Firmware and tests

`apps/hand` is the hand firmware, built per side (`hand:left`, `hand:right`).
It samples five flex channels at 100 Hz through `esp_timer`, classifies
open/short faults, calibrates, normalises curl and tilt, runs the per-hand state
machine, and notifies one packet per 20 ms to the hub over BLE.

UART commands: `info`, `sample`, `stats`, `control`, `motion`, `packet`, `link`,
`stream N`, `stall SWEEPS`, `profile`, `reboot`, and `cal extended | curled |
neutral | finish | reset | save | load | erase | corrupt`.

`apps/hub` connects both hands and applies the mapping and interlocks from
[`gesture-mapping.md`](../docs/gesture-mapping.md) in
`components/palmpilot_core/hub_core.c`. It prints one `command` line per 20 ms
on UART0 (`valid`, `reason`, `roll`, `pitch`, `yaw`, `throttle`, `hold`,
`precision`), and answers `status`. GPIO7 is CALIBRATE: it captures neutral on
both hands and inhibits output while held.

```sh
sh firmware/tests/run_all.sh                                    # every suite
python3 firmware/tools/palmpilot.py system firmware/tests/s2b_controller.py
```

| Suite | Covers |
|---|---|
| `tools/selftest.py` | toolchain chain, ADC injection on all five channels |
| `tests/s1a_acquisition.py` | channel identity, calibrated mV, fault classification, ENABLE debounce |
| `tests/s1b_calibration.py` | capture, travel/stability/inversion rejection, curl normalisation |
| `tests/s1c_control.py` | state machine, throttle-low interlock, latched faults, stalled acquisition |
| `tests/s1d_motion.py` | LSM6DS3TR-C + LIS3MDL identity, config, data-ready gating, burst decode |
| `tests/s1e_attitude.py` | tilt mapping, deadband, saturation; HOLD/PRECISION flagged, not applied |
| `tests/s1f_persistence.py` | NVS save and reload; reboot/erase/CRC are blocked |
| `tests/s1g_packet.py` | hand→hub packet framing, counters, bounds, frozen-sampling case |
| `tests/s1h_watchdog.py` | watchdog serviced only after real work |
| `tests/s2a_link.py` | both hands linked to the hub, MTU, 50 Hz, no rejected packets |
| `tests/s2b_controller.py` | whole controller: mapping, slew, HOLD, PRECISION, deadman, faults, latch, hand reboot, hub CALIBRATE |
| `tests/s3a_drone.py` | hands + hub drive ArduCopter: RC reported back, expiry on a cut hub line |
| `tests/s3b_replay.py` | scripted packets (`apps/replay`) → hub → bridge → ArduCopter, against an independent model |

Motion stimulus comes from `tests/fixtures/`: two register fixtures plus a
shared `imu_state` module a test mutates directly. They are register fixtures,
not sensor models — no ODR timing, filtering, FIFO, interrupts or noise.

### Probes

`probes/` holds minimal reproducers for simulator model defects that are still
open, plus the drone flight scripts. They are not part of `run_all.sh`. Probes for
defects fixed in the pinned engine were removed; they are in git history.

| Probe | Finding |
|---|---|
| `probes/rngreset` | RNG replays after `esp_restart()`, fixed by the #271 candidate (`run.py`; `PALMPILOT_RNG_OVERLAY=` for stock) |
| `probes/drone-outputs` | ArduCopter motor outputs observed at the timer registers |
| `probes/drone-flight` | `fly.py` gesture flight; `shake`/`tilt`/`spin` single-axis checks; `soak`/`stress` long runs; `loop_rate`, `params_dump` |

`stall N` skips N acquisition sweeps. It is a deliberate fault-injection hook
for the FW-04 stalled-acquisition case, not production behavior.

## Constraints that bite in firmware

- **Fixed-point control path.** All control arithmetic is in milli-units. The FPU
  gap that forced this (the first Xtensa FPU instruction aborted engine 0.5.7) no
  longer reproduces on engine 0.6.3 and later, so this is now a design choice, not a
  simulator limitation.
- **Pace periodic work with `esp_timer`, not `vTaskDelay`.**
- **Never write flash from the live control path.** A real flash write suspends
  the scheduler; `cal save` and `cal erase` are refused while `permitted`.
- **The interrupt watchdog is on** (`CONFIG_ESP_INT_WDT=y`, 300 ms), as in
  production. `run_all.sh` fails any suite whose UART shows a firmware panic.
- Use `esp_timer` rather than GPTimer.
- The platform models **two CPU cores** while `sdkconfig` sets
  `CONFIG_FREERTOS_UNICORE=y`. For deterministic runs set `PALMPILOT_SERIAL=1`
  (serial execution; much slower).
- Reserved pins: GPIO19/20 (native USB), GPIO43/44 (UART0 bridge),
  GPIO0/3/45/46 (strapping). GPIO10 stays disconnected.
- The IMU fixtures are register fixtures, and the GPIO matrix is not modelled, so
  the SDA/SCL pin choice is untested in simulation.

## The toolchain is fragile

Everything the build depends on lives in gitignored `tmp/simantic/` (~3.5 GB)
and is **not reproducible from a clean checkout**: ESP-IDF v5.5.2, the Xtensa
compiler, the Simantic engine, the platform `.repl`, the Espressif mask ROM, the model candidates
and ArduCopter. Deleting `tmp/` destroys the ability to build or
simulate. `env.sh` fails loudly rather than silently picking up a different
toolchain; if it reports a missing path, stop and restore it rather than
substituting another version.
