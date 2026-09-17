# ESP32-S3 source review

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

> **September 17 follow-up:** see the [current hand-controller readiness record](../../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

Reviewed September 16, 2026 through authenticated, read-only GitHub access. This supplements the [runtime audit](README.md) and [ADC test review](adc-review/README.md); no simulator implementation was changed and no new firmware execution was needed for this source comparison.

## Conclusion

**Implementation follow-up:** [draft Simantic PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168) adds ADC1 RTC one-shot voltage conversion. An isolated model build passes 41 NUnit cases and 45 compiled Xtensa observations using unmodified ESP-IDF v5.5.2 low-level headers. The identical corrected ELF on original engine 0.5.7 reports no DONE in all 45 observations. This draft has not been merged or shipped; full ESP-IDF initialization/calibration and engine integration remain unvalidated. The implementation uses an explicitly ideal, synchronous analog model.

**The board definition exists, but external ESP32-S3 ADC conversions have not been implemented in the engine revisions inspected.** This is not a missing N8R2 variant, an incorrect board selection, or simply an old local CLI. Existing CPU/UART/I²C/digital-GPIO passes remain valid within their recorded scope.

### What the variant provides

The [N8R2 variant](https://github.com/simantic-dev/mcu-lib/blob/167bf7ae24298e72e3e87d864a766cf829cf7d20/models/ESP32S3/variants/ESP32-S3-WROOM-1-N8R2.replx#L1-L15) imports the common S3 platform and adds 2 MB quad PSRAM. It does not supply a separate ADC implementation. The FN8 variant also imports the common platform; switching between these variants will not supply ADC behavior.

The [common S3 definition](https://github.com/simantic-dev/mcu-lib/blob/167bf7ae24298e72e3e87d864a766cf829cf7d20/models/ESP32S3/ESP32S3.replx#L122-L130) maps SENS to `Miscellaneous.ESP32S3_Sens` at `0x60008800`. Its [APB SARADC definition](https://github.com/simantic-dev/mcu-lib/blob/167bf7ae24298e72e3e87d864a766cf829cf7d20/models/ESP32S3/ESP32S3.replx#L186-L188) is plain memory at `0x60040000`.

### Why firmware waits forever

In the actual engine dependency, [ESP32S3_Sens.cs](https://github.com/simantic-dev/renode-infrastructure/blob/204b580155d1a18ff4e3f640fbe38e68c1a0bf60/src/Emulator/Peripherals/Peripherals/Miscellaneous/ESP32S3_Sens.cs#L39-L82):

- Writes only store a register value in an array.
- Reads return the stored value, except for internal temperature-sensor readiness at offset `0x50`.
- No external ADC channel input, START conversion handler, result calculation or DONE update exists.

Consequently, our firmware can select a flex channel and write START, but no converter consumes the input or produces DONE. This matches the earlier installed-assembly inspection and the fresh CLI/SDK completion failures. The source history contains the initial temperature-sensor addition on August 28 and a size correction that day; the examined revision has no later S3 external-ADC implementation.

## Release comparison

| Layer | Revision inspected |
| --- | --- |
| `mcu-lib` main | `167bf7ae24298e72e3e87d864a766cf829cf7d20` |
| `simantic-cli` main | `59b6b181c00a2834a25b7bd602c5ab2a1e239260` |
| CLI `v0.5.7` tag, dereferenced | `e22b565339d16aa17ec368049753f9d033fc67ac` — matches installed version |
| Core referenced by CLI main | `175f73dc050ac8b760acf07cffdd85c0cc9b3158` |
| Core referenced by CLI `v0.5.7` | `bf40f71a6c67b40dde9c49f7cb757d29277466e7` |
| Independently inspected core main | `48cdeff9fc84f682ed18c55757190681a5234a6b` |
| Renode referenced by all three core revisions | `0cb4d77cc4a41aa05c0c489bf490ef42470cc135` |
| Infrastructure referenced by that Renode | `204b580155d1a18ff4e3f640fbe38e68c1a0bf60` |
| Catalog submodule in release core | `b4ddf842d188b499e8b612bce31ca1de92222537` |

The released CLI and current CLI/core source therefore select the **same engine dependency** for these peripherals. Do not inspect only the infrastructure repository's default branch: the build uses a pinned submodule revision. The SENS, TIMG and GPIO source blobs match between the release and current dependency checks. Source snapshots and dependency metadata remain under ignored `tmp/simantic/audit/source-review/`; private repository contents are not vendored into this project.

## Existing C3 ADC is useful reference, not a drop-in S3 fix

[ESP32C3_SarAdc.cs](https://github.com/simantic-dev/renode-infrastructure/blob/204b580155d1a18ff4e3f640fbe38e68c1a0bf60/src/Emulator/Peripherals/Peripherals/Analog/ESP32C3_SarAdc.cs#L17-L60) implements C3 APB one-shot conversions, raw channel injection and a simplified DMA path. Its `SetChannelValue` API supplies raw counts, not calibrated voltage conversion.

C3 one-shot firmware uses APB `ONETIME_SAMPLE` and interrupt/result registers. The S3 RTC one-shot driver uses the separate SENS register path. Merely replacing the S3 APB memory region with the C3 class will not satisfy the S3 driver. Shared input storage or conversion helpers may be reusable, but S3 register semantics must be implemented and tested independently.

An ADC PR search found merged C3 work ([infrastructure #92](https://github.com/simantic-dev/renode-infrastructure/pull/92), [catalog #114](https://github.com/simantic-dev/mcu-lib/pull/114)); it did not identify an S3 ADC bring-up PR in the searches performed. This is not proof that no developer has work on an unpublished branch.

## Other source-confirmed limits

| Area | Source finding | Controller consequence |
| --- | --- | --- |
| TIMG | [Timer model](https://github.com/simantic-dev/renode-infrastructure/blob/204b580155d1a18ff4e3f640fbe38e68c1a0bf60/src/Emulator/Peripherals/Peripherals/Timers/ESP32C3_Timg.cs#L24-L30) implements RTC calibration; main timers/watchdog configuration are stored without counter/alarm/watchdog firing behavior | Bring up the timer/watchdog paths used by the selected firmware. SYSTIMER is separate and has limited runtime passes. |
| GPIO above 21 | [S3 platform explicitly documents the limitation](https://github.com/simantic-dev/mcu-lib/blob/167bf7ae24298e72e3e87d864a766cf829cf7d20/models/ESP32S3/ESP32S3.replx#L101-L105) and instantiates the C3 GPIO model | Explains GPIO43 failure. Lower priority for our GPIO1/2/4/5/6 flex inputs and GPIO7 button. UART byte transport passing does not prove GPIO43 pin-mux behavior. |
| IO_MUX | S3 platform maps it as plain memory | Pin configuration readback does not qualify actual signal routing. |

These findings are not an exhaustive list of all S3 limitations or a claim that complete ESP-IDF/BLE applications fail. Production framework boot, our two-hand BLE topology, watchdog behavior and full sensor drivers still require application-level acceptance tests.

## Minimal bring-up handoff

1. In `renode-infrastructure`, implement the **S3 ADC1 RTC one-shot path** in or alongside `ESP32S3_Sens`, preserving the existing temperature-sensor behavior. Cover channel selection, required power/clock configuration, START, read-only DATA/DONE and reset/restart semantics.
2. Expose documented per-channel analog input with explicit units, attenuation/reference, quantization, saturation, calibration assumptions and sampling time. Our project supplies changing flex voltages; the simulator supplies ADC behavior.
3. If the peripheral type or connections change, update the shared S3 definition in `mcu-lib`; another variant file alone is insufficient.
4. Add a real ESP-IDF `adc_oneshot_read` fixture for ADC1 channels **0, 1, 3, 4, 5**, including changing inputs, repeated reads, channel switching and reset. Compare counts against declared model tolerances, not an invented full-scale voltage.
5. Publish the updated dependency chain: infrastructure → Renode → core → CLI/SDK engine, with the catalog update where required. Rerun our existing diagnostics and the full driver fixture against the shipped build.

Full details and test limitations are in the [ADC review and bring-up request](adc-review/README.md#simantic-bring-up-request). ADC is the immediate controller blocker; timer/watchdog bring-up and production application validation follow.
