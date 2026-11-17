# Contributing

Thanks for looking at PalmPilot. A few rules keep the project's results honest.

## Evidence first

Every result is one of **PASS**, **FAIL**, **BLOCKED**, **MOCKED-INPUT-ONLY** or
**NOT APPLICABLE**. A simulation PASS never marks a physical check passed, and the
reverse. Set numeric acceptance limits before running a test, and record the
engine, SDK and model versions, the ELF hash and the stimulus with the result.
Stimulus must go through the modelled driver: writing a value straight into the
firmware's memory is MOCKED-INPUT-ONLY, not driver coverage.

Write documentation the same way: say what was observed, its scope, and what it
does not establish.

## Firmware rules

- No floating point on the control path; use fixed-point milli-units (0–1000).
- Pace periodic work with `esp_timer`, not `vTaskDelay`.
- Never write flash from the live control path.
- Near-rail flex readings are faults, never clamped into a valid gesture.
- ENABLE is a permission request; it never arms, starts or resumes anything.
- The pin map in `CLAUDE.md` §2 is frozen.

Bench-only behaviour goes behind `CONFIG_PALMPILOT_BENCH`
([docs/bench-bringup.md](docs/bench-bringup.md)); the default build is what the
simulation suites test.

## Before a pull request

```sh
sh firmware/tests/run_all.sh                     # every simulation suite
python3 simulation/drone/test_quad_plant.py      # physics model
```

State in the pull request which suites you ran, on which engine version, and their
result. Changes to the gesture mapping update `docs/gesture-mapping.md` and the
suites that test it in the same pull request.

## Setting up

The toolchain (ESP-IDF 5.5.2, the Xtensa compiler, the Simantic engine and
platforms, the ESP32-S3 mask ROM, ArduCopter builds) lives in a gitignored `tmp/`
directory; `firmware/tools/env.sh` pins every path. See the README's "Getting
started" section for what is and is not reproducible from a clean clone today.
