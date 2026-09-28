# Simantic model candidates

These are two simulator models this project needs that are not yet in a Simantic engine release. They are loaded as overlays on engine 0.5.14 by default (`firmware/tools/env.sh`). Each is an exact copy of an open upstream PR. The only change is the namespace of the SYSTIMER copy (`SystFixed`), because the engine already contains classes with those names.

| Directory | Upstream | What it fixes |
|---|---|---|
| `systimer-work-en/` | [renode-infrastructure #257](https://github.com/simantic-dev/renode-infrastructure/pull/257) | The SYSTIMER re-armed the periodic FreeRTOS tick on every `CONF` write of `WORK_EN=1`. ESP-IDF rewrites that bit on every esp_timer re-arm, so the tick died: `vTaskDelay` blocked forever, NVS erase hung, and the interrupt watchdog panicked healthy firmware. |
| `s3-mwdt/` | [renode-infrastructure #258](https://github.com/simantic-dev/renode-infrastructure/pull/258), wiring in [mcu-lib #229](https://github.com/simantic-dev/mcu-lib/pull/229) on [#222](https://github.com/simantic-dev/mcu-lib/pull/222) | `ESP32S3_Timg` stored the main-watchdog registers but never ran it, so the IDF task and interrupt watchdogs could not fire. |

Build them into `tmp/simantic/upstream-candidates/` (gitignored):

```sh
. firmware/tools/env.sh
export DOTNET_ROOT="$PWD/tmp/simantic/dotnet-sdk" DOTNET_CLI_HOME="$PWD/tmp/simantic/dotnet-home"
"$DOTNET_ROOT/dotnet" build simulation/simantic/model-candidates/systimer-work-en/SystFixed.csproj
"$DOTNET_ROOT/dotnet" build simulation/simantic/model-candidates/s3-mwdt/S3MwdtUnderTest.csproj
```

To run the engine's own models instead, set `PALMPILOT_SYSTIMER_OVERLAY=` and/or `PALMPILOT_S3_MWDT_OVERLAY=` (empty). Delete a candidate once an engine release contains its PR, and re-run `firmware/tests/run_all.sh`.

## Evidence, recorded 2026-09-27

Each item is a before/after on the same firmware.

- **SYSTIMER, measured by `firmware/probes/systick` (`multichip.py`)**, as ticks and `vTaskDelay(10 ms)` loops per second:
  - ESP32-S3, ESP32-C3, ESP32-C6 and ESP32-P4: 0 / 0 on the shipped model, 100 / 100 with the candidate.
  - Also committed upstream as sim-fixtures#314. With the same 0.5.14 engine rebuilt with and without the fixes, all 130 ESP fixtures give identical outcomes.
- **MWDT, measured by `firmware/probes/mwdt`:** 4/11 on the shipped model (nothing fires), 14/14 with the candidate.
- **Interrupt watchdog in the hand application** (production settings), measured by `firmware/tests/run_all.sh`: 7 of 8 hand suites panicked on the shipped SYSTIMER. With the candidate, 0 panics and all suites pass.

These results validate the simulator's models. They do not qualify anything on silicon.
