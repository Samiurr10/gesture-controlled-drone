# Simantic runtime capability audit

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

> **September 17 follow-up:** see the [current hand-controller readiness record](../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

**Executed September 16, 2026:** Simantic CLI/engine 0.5.7, Python SDK 0.3.1,
macOS arm64. This directory publishes reports and concise recorded runtime results for the controller and candidate drone MCU.

**Controller migrated to ESP32-S3 later the same day.** Nordic tests below are historical and remain unchanged as evidence. Start with the [ESP32/full-drone assessment](../../../docs/implementation-records/2026-09-16_esp32-full-drone-feasibility.md) for active blockers.

Start with the [audit record](../../../docs/implementation-records/2026-09-16_simantic-capability-audit.md)
and [requests to send to Simantic](SIMANTIC-REQUESTS.md).

| Test group | Evidence |
|---|---|
| ESP32-S3 selected runtime and firmware probes | [ESP32 audit](esp32s3/README.md) |
| Extended stock drone firmware and sensor-startup feasibility | [Full-drone assessment tests](full-drone/README.md) |
| Historical nRF52840 core, SAADC, TWIM, flash and reset | [nRF audit](nrf52/README.md) |
| STM32H743 core, PWM, DMA, buses, ADC and stock firmware boot | [H7 audit](stm32h7/README.md) |
| Historical nRF BLE, UART bridge and USB | [Transport audit](transport/README.md) |
| SDK time, inputs, output callbacks and scripted sensor buses | [SDK audit](sdk/README.md) |

## Scope and evidence rules

- The user owns flex/motion signal generation, sensor data/register responses,
  the command bridge, actuator decoding, physics and rendering. The fixtures
  here only establish how those can connect to Simantic.
- Tests exercise the current runtime, not just source code or catalog listings.
  The shipped TWIM and USB implementations are richer than the public upstream
  source inspected earlier; their remaining deficiencies are measured here.
- A passing register probe, a stock Zephyr example and stock ArduCopter startup
  are different evidence boundaries. None qualifies the complete application.
- Missing exact sensor models are not assigned to Simantic as mandatory feature
  requests. Existing scripted I2C/SPI slave hooks let the project supply them.
- One nRF peripheral suite covers common MCU mechanisms used by both Sense hand
  boards and the Express hub. It does not establish complete board behavior or
  two concurrent production BLE links.
- Binary downloads, generated ELFs, platform files, runtime packages and large
  logs live under ignored `tmp/simantic/`. Small result records, fixture URLs,
  hashes and source remain here. No credentials are included.

## Environment and reproduction

The `.venv-simantic` environment contains `simantic==0.3.1` and `pytest==9.1.1`.
`arm-none-eabi-gcc` 16.2.0 builds the diagnostic images. The recorded engine is
installed in `tmp/simantic/runtime/engine/0.5.7`; each group's README gives its
commands and fixture dependencies. Reproduction requires the authenticated
`NRF52840QIAA` and `STM32H743ZI` platform definitions at the recorded hashes.
The SDK's model resolver and CLI use the existing Simantic login; do not put
credentials in test files.

```sh
export SIMANTIC_HOME="$PWD/tmp/simantic/runtime"
export SIMANTIC_TELEMETRY=0
export DOTNET_BUNDLE_EXTRACT_BASE_DIR=/private/tmp/palmpilot-simantic-dotnet
```

Fresh engine installation can be performed with `python -m simantic install
engine` in the configured environment. It resolves the then-current release;
compare its version and hashes with the record before treating a rerun as the
same audit. The engine writes/locks its normal Renode configuration outside the
workspace. The initial sandbox denial of that lock was resolved by granting the
requested local test process access; it is not counted as a simulator failure.

Reported failures are expected on the audited release and are retained as
regression tests. Do not weaken assertions to produce a green run. After a
Simantic update, rerun the affected groups and save new versioned results.
