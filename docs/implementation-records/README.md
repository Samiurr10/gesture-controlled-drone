# Implementation evidence

**Latest tests:** [September 17 hand-controller readiness](2026-09-17_hand-controller-readiness.md): corrected ADC probe, full ESP-IDF ADC and timer tests, physical ADC limits and remaining one-hand work.

**Earlier decision and tests:** [ESP32 controller migration and complete-drone feasibility](2026-09-16_esp32-full-drone-feasibility.md). The earlier nRF52840 audit is historical controller evidence; its passes and failures do not qualify ESP32. STM32 drone findings remain relevant to the current virtual candidate.

Scope: **controller simulation → physical hand-controller prototype → virtual drone hardware/MCU, mechanical simulation and display**. No physical drone build or flight results are required. The [September 16 runtime audit](2026-09-16_simantic-capability-audit.md) records passing diagnostic paths and specific model failures. Complete controller/flight firmware qualification and physical prototype results remain pending.

For each checkpoint, create a dated Markdown record using the [test record template](../controller/test-record-template.md). Include the milestone (S0–S3, C0–C7 or D1–D4) and exact test/scenario ID from [controller validation](../controller/validation.md) or the [drone simulation plan](../drone-simulation.md). Example: `YYYY-MM-DD_S1_CTRL-010_simulated-flex.md`.

## Separate the evidence types

| Evidence type | Required context | What it establishes |
|---|---|---|
| Application/host test | Code revision, fixed inputs, assertions and expected limits | Behavior of tested application logic; not peripheral compatibility |
| Controller MCU simulation | Firmware build, Simantic CLI/engine/SDK, model source/version/hash, simulated peripherals, traces and virtual timing | Tested firmware behavior against the modeled hardware only |
| Physical controller test | Board/circuit revision, firmware, calibration, instruments, settings and measurements | Actual sensing, power, BLE, fit and host-interface behavior tested |
| Integrated virtual drone | Controller evidence, drone firmware/model, output decoder, dynamics/renderer versions, model parameters and synchronized traces | MCU-output-driven mechanical response and screen behavior |

Record every result as **pass**, **fail**, **blocked** or **mocked-input-only**, with expected versus observed behavior. Identify substitutes and unmodeled effects. Never turn a simulation pass into a physical hardware pass or a mock into a verified peripheral test. Each checked [project milestone](../../README.md#full-implementation-checkpoints) must link to its evidence.

Save failures and successful retests. Set numeric acceptance limits before running tests. For virtual runs, record coordinate frames, time units, simulation step/quantum, seed, stimulus trace and relevant clock synchronization. For prototype runs, record actual hardware, sampling/communication delays, battery operating range and measured calibration.

Keep small reproducible logs and configurations beside their record. Reference large recordings by stable URL and checksum. Exclude credentials, disposable renders and virtual environments from Git.

After changes to pins, firmware, packet format, mapping, calibration, power, model/peripheral implementation, dynamics parameters or time synchronization, identify and rerun affected checks before reusing a qualification claim. Optional legacy trainer tests remain separate from the required controller and virtual-drone evidence.
