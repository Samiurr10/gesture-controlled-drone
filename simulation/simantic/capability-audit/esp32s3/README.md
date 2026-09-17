# ESP32-S3 runtime audit

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

> **September 17 follow-up:** see the [current hand-controller readiness record](../../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

**Follow-up:** the [independent ADC/input review](adc-review/README.md) now confirms the installed SENS ADC path stores registers without implementing conversions, and the timer-group model lacks the tested general-purpose timer behavior. Fresh CLI/SDK results agree; explicit ESP analog-input attachment is blocked, while the same input API works in a STM32 positive control. The earlier firmware suite below remains a completion/register probe, not a calibrated voltage sweep or full ESP-IDF test.

**Result: useful MCU paths execute, but a complete ESP32 hand controller is not
yet validated.** This audit ran compiled Xtensa firmware on Simantic CLI/engine
0.5.7 and SDK 0.3.1. It is a register-level diagnostic, not an ESP-IDF, Arduino,
BLE or Wi-Fi application.

Both `ESP32-S3-WROOM-1-N8R2` and `ESP32S3FN8` were fetched through the installed
SDK's normal authenticated model resolver. Execution used the unmodified N8R2
catalog model, with a BME280 bus fixture appended only for the I²C test. The model
instantiates successfully. A catalog entry alone was not counted as a pass.

## Observed behavior

| Path | Result | What was actually checked |
| --- | --- | --- |
| Xtensa execution / UART0 | Pass | Real GCC-built ELF enters C, emits boot/ready markers, advances CCOUNT, and echoes SDK-injected UART bytes. UART FIFO flow control is used. |
| Selected GPIO inputs | Pass as digital inputs | GPIO1, 2, 4, 5, 6 and GPIO7 follow individual high/low SDK injection as read by firmware. This does **not** prove ADC sampling on those pins. |
| GPIO4 output | Pass | OUT set/clear register behavior. External pin mux routing is untested. |
| SYSTIMER | Pass, limited | Unit0 snapshot-valid handshake and advancing counter. Alarm/CPU interrupt delivery and RTOS scheduling are untested. |
| I²C0 | Pass, limited | Command-FIFO repeated-start read of fixed BME280 ID `0x60`, transaction completion, STOP command DONE, interrupt-flag clearing and absent-slave NACK. |
| ADC1 RTC single conversion | **Partial / conversion blocked** | Channels 0/1/3/4/5 (GPIO1/2/4/5/6) accept channel/control writes and reach the idle-state check. After explicit bus/SAR clock and power enable, DONE remains `0` for every channel and observed data is `0`. |
| TIMG0 general-purpose timer | **Failed snapshot/alarm probe / needs model investigation** | After the HAL divider-reset sequence, enable readback passes, but snapshot UPDATE never clears and the alarm flag stays `0`. The sampled count is therefore not valid evidence that the counter itself stopped. SYSTIMER works separately. |
| GPIO43 | **Model fidelity gap** | Output SET stays `0`; injected input stays `0` and logs `GPIO input 43 out of range`. High-bank GPIO registers are unhandled. This pin is reserved for UART0 in the current design; it is not one of the flex/button input checks. |

ADC control readback is a positive control: e.g. channel 0 returns `0x800c0000`
as expected. Do not describe the whole ADC register block as missing or ignore
this partial behavior. The APB digital ADC block at `0x60040000` is instantiated
as plain `Memory.MappedMemory`; the separate RTC `ESP32S3_Sens` object accepts
register values but did not complete the tested conversion sequence.

The BME280 is a fixed-register positive I²C fixture, not the controller's motion
sensor. No gesture-input generator, integration application, simulator fix or
production controller firmware was implemented.

## Evidence

- [results.json](results.json): four completed CLI probes, individual observed /
  expected values, source/ELF/model/UART hashes and timestamps.
- [sdk-result.json](sdk-result.json): actual UART echo and per-pin input results,
  selected register diagnostics and deduplicated relevant model warnings.
- [platform-instantiation.json](platform-instantiation.json): instantiated CPU and
  peripheral types, observed without running firmware in that inspection step.
- [provenance.json](provenance.json): model download hashes, official toolchain
  archive URL/hash, pinned Espressif register-source URLs/hashes and exact
  source-snapshot mapping for each tested revision.

Raw ELF files, compiler, catalog platforms, UART transcripts, traces and process
output live under ignored `tmp/simantic/audit/esp32s3/`. A zero process exit means
the probe completed; inspect its assertions to assess hardware behavior.
GPIO43-clear and TIMG0-alarm-clear read zero, but their earlier set/alarm checks
failed, so those zero values do not qualify the complete paths.

The small firmware bypasses ROM/bootloader startup and uses the call0 ABI. The
catalog model starts two CPUs at the ELF entry point; diagnostic assembly parks
the second CPU using its configured PRID. It therefore does **not** test SMP
scheduling, inter-core synchronization or the engine's parallel-core fidelity.

## Reproduce

The existing `.venv-simantic` and authenticated SDK are prerequisites. From the
repository root:

```sh
.venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/fetch_models.py
.venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/fetch_headers.py
.venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/fetch_toolchain.py
sh simulation/simantic/capability-audit/esp32s3/build.sh
python3 simulation/simantic/capability-audit/esp32s3/run.py

SIMANTIC_HOME="$PWD/tmp/simantic/runtime" SIMANTIC_TELEMETRY=0 \
  .venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/audit_sdk.py
SIMANTIC_HOME="$PWD/tmp/simantic/runtime" SIMANTIC_TELEMETRY=0 \
  .venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/inspect_platform.py
```

The standalone official compiler is Xtensa GCC 14.2.0, release
`esp-14.2.0_20251107`, pinned through ESP-IDF v5.5.2's manifest. Its 169 MB download
and approximately 1.11 GB expanded files stay in the temporary audit directory;
the full ESP-IDF framework was not installed. The fetcher checks expected size
and SHA-256 before extraction.

Each CLI case has a one-second virtual timeout and a 40-second wall timeout.
Firmware polling is bounded. Renode needs normal access to its user
configuration lock. The runner checks that all requested ELF files exist; only
run after `build.sh` succeeds. Rebuild/rerun the complete suite before replacing
the checked-in snapshot so source hashes stay consistent.

The recorded boot/I²C and SDK results retain their already-tested ELF files.
Only the affected core/ADC cases were rebuilt and rerun after adding the bounded
ADC idle wait, TIMG divider reset and snapshot-ready wait. The earlier complete
source is preserved in `evidence/probe-before-adc-timer-review.c`; the SHA-256
mapping in `provenance.json` identifies the exact source for every result.

## Register and driver references

Source offsets are pinned to
[Espressif ESP-IDF v5.5.2 S3 registers](https://github.com/espressif/esp-idf/tree/v5.5.2/components/soc/esp32s3/register/soc).
The ADC sequence follows channel selection, start and DONE fields in
[adc_ll.h](https://github.com/espressif/esp-idf/blob/v5.5.2/components/hal/esp32s3/include/hal/adc_ll.h).
I²C commands follow the actual
[i2c_ll.h](https://github.com/espressif/esp-idf/blob/v5.5.2/components/hal/esp32s3/include/hal/i2c_ll.h)
opcodes (RESTART=6, WRITE=1, READ=3, STOP=2, END=4), which differ from the generated
register-header prose.
TIMG divider reset and snapshot-ready behavior follow
[timer_ll.h](https://github.com/espressif/esp-idf/blob/v5.5.2/components/hal/esp32s3/include/hal/timer_ll.h)
and [timer_group_struct.h](https://github.com/espressif/esp-idf/blob/v5.5.2/components/soc/esp32s3/register/soc/timer_group_struct.h).
The divider-reset field is CONFIG bit12, omitted from the generated register
header but present in the official struct/HAL. The final probe includes it.

| Block | Important tested addresses |
| --- | --- |
| UART0 | Base `0x60000000`; FIFO `+0x00`, STATUS `+0x1c`, CONF0 `+0x20`, clock `+0x78` |
| GPIO | Base `0x60004000`; OUT/SET/CLEAR `+0x04/+0x08/+0x0c`, high-bank equivalents `+0x10/+0x14/+0x18`, IN `+0x3c`, high-bank IN `+0x40` |
| SYSTIMER | Base `0x60023000`; CONF `+0x00`, UPDATE/VALID `+0x04`, sampled low count `+0x44` |
| TIMG0 | Base `0x6001f000`; CONFIG `+0x00`, count `+0x04`, snapshot `+0x0c`, alarm `+0x10/+0x14`, load `+0x18/+0x1c/+0x20`, interrupt RAW `+0x74`, CLEAR `+0x7c` |
| ADC1 RTC | SENS base `0x60008800`; reader `+0x00`, channel/control/START/DONE/data `+0x0c`, mux `+0x10`, SAR power/clock `+0x3c` |
| I²C0 | Base `0x60013000`; CTRL `+0x04`, FIFO config `+0x18`, DATA `+0x1c`, interrupt RAW/CLEAR `+0x20/+0x24`, command array `+0x58` |

## Remaining acceptance gates

1. Complete ADC conversions and establish a supported per-channel analog input
   interface; then prove the selected ESP-IDF/Arduino ADC driver.
2. Investigate the TIMG0 sequence and high-bank GPIO coverage. Preserve the
   positive SYSTIMER and selected low-pin GPIO evidence.
3. Boot a pinned real ESP-IDF/Arduino application with the correct ROM,
   bootloader/flash/cache configuration. Validate the chosen board's PSRAM,
   pin mux, motion driver and battery backend where used.
4. Test the selected hand-to-host transport and complete fault behavior.
   **BLE, Wi-Fi, ESP-NOW, USB enumeration, NVS persistence, watchdog recovery,
   production two-hand firmware and a complete drone simulation were not tested
   by this suite.** Their model registrations do not establish compatibility.
