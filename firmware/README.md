# PalmPilot firmware workspace

Active ESP32-S3 controller firmware and its build/simulation harness.
Constraints, pin map and evidence rules: [`CLAUDE.md`](../CLAUDE.md).
Work packages: [`docs/controller/firmware-plan.md`](../docs/controller/firmware-plan.md).
Simulation gates: [`docs/controller/simantic-plan.md`](../docs/controller/simantic-plan.md).

This directory holds tooling and firmware sources only. **No milestone is
completed by anything here**; S0–S3 and C0–C7 require passing tests against the
[controller validation checklist](../docs/controller/validation.md).

## Layout

```
firmware/
  tools/env.sh        pinned toolchain paths, single source of truth
  tools/palmpilot.py  build / pack / sim driver
  tools/harness.py    reusable Simantic wrapper (importable as `harness`)
  tools/selftest.py   end-to-end chain check against the ADC reference app
  apps/               ESP-IDF projects (one per target: hand, hub, ...)
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
attenuation 3 on GPIO1/2/4/5/6 — the same values recorded in the
[controller simulation plan](../docs/controller/simantic-plan.md).

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
from harness import FLEX, PalmPilotSim, ideal_raw

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

The wrapper exists to encode three bench findings so they are not rediscovered:

- **ADC needs the PR #168 overlay.** Stock engine 0.5.7 stores ADC registers
  without converting. The overlay is namespace-only, so the platform's
  `Miscellaneous.ESP32S3_Sens` is rewritten to `AdcUnderTest.ESP32S3_Sens` into
  a per-run copy of the `.repl`. Pass `adc=False` to skip it.
- **`Sim.read_uart` is unreliable** on engine 0.5.7 / SDK 0.3.1 — it duplicates
  and interleaves fragments. The harness captures the Renode `CharReceived`
  event instead. Assert against `sim.records()`, never `read_uart`.
- **ADC injection is not in the SDK.** `set_flex_uv` / `set_channel_uv` go
  through Renode interop (`IADCExtensions.SetVoltage`).

`ideal_raw(microvolts, attenuation)` is the model's **declared ideal** transfer
function, `min(4095, uV × 4095 × (4−atten) ÷ 4400000)`. Matching it validates
the model contract and nothing about silicon: no noise, no conversion latency,
no factory calibration. Silicon and model already disagree at the nominal 3V3
endpoint (4095 measured vs 3071 ideal).

## Firmware and tests

`apps/hand` is the hand-node firmware. It samples five flex channels at 100 Hz
through `esp_timer`, classifies open/short faults, captures and validates a
calibration profile, normalises finger curl, and runs the control state machine
with the safety interlocks from
[`gesture-mapping.md`](../docs/controller/gesture-mapping.md).

UART commands: `info`, `sample`, `stats`, `control`, `motion`, `packet`,
`stream N`, `stall SWEEPS`, `profile`, `reboot`, and `cal extended | curled |
neutral | finish | reset | save | load | erase | corrupt`.

```sh
sh firmware/tests/run_all.sh          # every suite
```

| Suite | Covers |
|---|---|
| `tools/selftest.py` | toolchain chain, ADC injection on all five channels |
| `tests/s1a_acquisition.py` | channel identity, calibrated mV, fault classification, ENABLE debounce |
| `tests/s1b_calibration.py` | capture, travel/stability/inversion rejection, curl normalisation |
| `tests/s1c_control.py` | state machine, throttle-low interlock, latched faults, stalled acquisition |
| `tests/s1d_motion.py` | LSM6DS3TR-C + LIS3MDL identity, config, data-ready gating, burst decode |
| `tests/s1e_attitude.py` | tilt mapping, deadband, saturation, slew, PRECISION, HOLD |
| `tests/s1f_persistence.py` | NVS save and reload; reboot/erase/CRC are blocked |
| `tests/s1g_packet.py` | hand→hub packet framing, counters, bounds, frozen-sampling case |
| `tests/s1h_watchdog.py` | watchdog serviced only after real work; timeout is blocked |

Motion stimulus comes from `tests/fixtures/`: two register fixtures plus a
shared `imu_state` module a test mutates directly. They are register fixtures,
not sensor models — no ODR timing, filtering, FIFO, interrupts or noise.

### Probes

`probes/` holds minimal deterministic reproducers for model defects. Each has a
README stating what it does and does not establish. They are **not** part of
`run_all.sh`, because two of them are expected to fail.

| Probe | Finding |
|---|---|
| `probes/fpu` | first Xtensa FPU instruction aborts the engine |
| `probes/reset` | `esp_restart()` aborts the engine |
| `probes/nvs` | `nvs_erase_key` never returns in a multi-task app |

`stall N` skips N acquisition sweeps. It is a deliberate fault-injection hook
for the FW-04 stalled-acquisition case, not production behavior.

## Constraints that bite in firmware

- **No floating point.** The first Xtensa FPU instruction aborts the engine
  ([record](probes/fpu/README.md)).
  All control arithmetic is fixed-point milli-units. `firmware/probes/fpu` is
  the regression probe.
- **Pace periodic work with `esp_timer`, not `vTaskDelay`.** Task delays run
  materially long on this model; a `vTaskDelay`-paced control task lagged the
  sampled data by a full query interval.
- **Never write flash from the live control path.** A real flash write suspends
  the scheduler; `cal save` and `cal erase` are refused while `permitted`.
- **The task watchdog cannot fire here.** TWDT is Timer-Group-backed and TIMG
  has no execution behavior in this model; `ESP_TASK_WDT_USE_ESP_TIMER` is a
  hidden symbol forced off for ESP32-S3, so the backend cannot be swapped. The
  feed discipline is verified through a counter; timeout, panic and reset are
  physical-only at C2.
- **Do not use GPTimer.** `gptimer_*` setup returns `ESP_OK`, but no alarm
  callbacks fire and `gptimer_get_raw_count` hangs — a confirmed model gap in
  `Timers.ESP32C3_Timg`. Use `esp_timer` (SYSTIMER-backed), which is verified.
- The platform models **two CPU cores** while our `sdkconfig` sets
  `CONFIG_FREERTOS_UNICORE=y`. The engine warns about non-deterministic
  cross-core execution; for repeatable runs pass a scenario with
  `serialExecution: true`.
- Reserved pins: GPIO19/20 (native USB), GPIO43/44 (UART0 bridge),
  GPIO0/3/45/46 (strapping). GPIO10 stays disconnected.
- No IMU coverage exists yet. The BME280 I2C fixture proves a bounded bus path,
  not the LSM6DS3TR-C/LIS3MDL driver. Those register fixtures are project-owned
  work and are the next hard dependency for S1.
- NVS persistence, watchdog recovery and ESP BLE are **unqualified**. Do not
  assume them in a design that has to pass a gate.

## The toolchain is fragile

Everything the build depends on lives in gitignored `tmp/simantic/` (~3.5 GB)
and is **not reproducible from a clean checkout**: ESP-IDF v5.5.2, the Xtensa
compiler, the Simantic engine, the platform `.repl`, the Espressif mask ROM and
the unmerged ADC overlay DLL. Deleting `tmp/` destroys the ability to build or
simulate. `env.sh` fails loudly rather than silently picking up a different
toolchain; if it reports a missing path, stop and restore it rather than
substituting another version.
