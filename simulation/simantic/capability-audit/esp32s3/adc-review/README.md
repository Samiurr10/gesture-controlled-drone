# ADC test and input review

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

> **September 17 follow-up:** see the [current hand-controller readiness record](../../../../../docs/implementation-records/2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

Reviewed September 16, 2026, after the user asked whether our test or its inputs caused the failure. This review distinguishes a completion probe from a voltage-accuracy test and inspects the **installed implementation**, rather than inferring support from a model name.

## Conclusion

**Source confirmation:** the [authenticated repository review](../SOURCE-REVIEW.md) traces the actual release/current dependency chain and confirms that S3 external ADC conversions remain unimplemented in those revisions. The N8R2 variant exists; changing variants or updating to the inspected CLI main does not supply the missing conversion logic.

**ESP32-S3 ADC conversion support is missing in the tested engine 0.5.7 implementation.** Confidence now comes from implementation inspection, an independent read-only-register test, identical fresh CLI/SDK runs and a working STM32 voltage-input positive control. This is a claim about the recorded build, not every Simantic version.

The prior test was a **bounded register-level completion probe**, not a complete ESP-IDF ADC driver or calibrated analog-input test. No explicit analog voltages were injected in that earlier probe. Its zero raw readings alone cannot prove an accuracy failure. We should have emphasized this distinction more clearly.

## What “conversion does not complete” means

A flex divider supplies a voltage. Firmware selects its ADC channel and starts a measurement. The ADC must sample that input, publish a digital result, and report completion. The driver waits for that completion before using the result.

For S3 ADC1 RTC one-shot reads, Espressif's pinned driver checks idle, pulses START from 0 to 1, polls DONE and then reads DATA. Our test uses the same channel/start/DONE addresses and masks. DONE is bit16 at `0x6000880c`: masked completion should read `0x00010000`, while the observed result remains `0x00000000`. Firmware emits its final READY marker, so these are executed assertions, not checks abandoned by the CLI timeout.

Sources: [ESP-IDF v5.5.2 one-shot HAL](https://github.com/espressif/esp-idf/blob/v5.5.2/components/hal/adc_oneshot_hal.c), [S3 low-level ADC functions](https://github.com/espressif/esp-idf/blob/v5.5.2/components/hal/esp32s3/include/hal/adc_ll.h), [S3 register definitions](https://github.com/espressif/esp-idf/blob/v5.5.2/components/soc/esp32s3/register/soc/sens_reg.h).

## Independent checks

| Check | Expected | Observed / conclusion |
|---|---|---|
| Channel selection | GPIO1/2/4/5/6 map to ADC1 channels0/1/3/4/5 | Correct in the firmware and board plan |
| Driver handshake | Idle check, START 0→1, DONE polling, DATA read | Addresses/masks match official S3 LL functions; completion fails on all five channels |
| Fresh SDK run | Diagnostic finishes and records every channel | Finished by 0.2 virtual seconds; all five DONE checks fail |
| Fresh installed CLI run | Same model/ELF gives matching assertions | One virtual second; UART output byte-identical to SDK run |
| CLI/SDK implementation | Same backend for a meaningful comparison | `Infrastructure.dll` SHA-256 identical; hash in results |
| Explicit ESP analog inputs | Attach 0, 1.0, 1.5, 2.0, 2.5 V to the five channels | All bindings rejected; no compatible ADC input interface. Accuracy sweep is **blocked**, not failed |
| Same API on STM32 | Known injected voltages reach the firmware ADC driver | 0/0.825/1.65/3.3 V produce 0/16384/32768/65535 with conversion completion; all expected results pass |
| Read-only S3 DONE/DATA | Software writes cannot manufacture a hardware result | Directly writing `0x1007b` reads back `0x1007b`, incorrectly setting DONE and DATA=123 without conversion |

The STM32 positive control uses its own configured **16-bit** ADC; those counts are not expected ESP32 values. Digital GPIO high/low injection is also not an analog-voltage test. No result register is modified in the firmware reruns; the separate read-only test is deliberately labeled as a direct backend diagnostic.

## Installed implementation inspection

`inspect_backend.py` examines the actual loaded CLR method bodies and runtime interfaces:

- `ESP32S3_Sens.WriteDoubleWord` stores the supplied value in a `UInt32[]`.
- Its read method returns that stored value, with a separate temperature-sensor special case at offset `0x50`. There is no ADC START handler, sampling calculation or scheduled DONE update.
- The class exposes no ADC channel/voltage interface. The APB SARADC region is `Memory.MappedMemory`.
- `ESP32C3_Timg`, used by this S3 platform, stores registers in a dictionary and handles RTC calibration special cases. Its inspected register methods do not implement the tested general-purpose counter, snapshot or alarm behavior.

This explains why ADC/timer control readback passed: storing a control word is not carrying out its operation. It also makes the ADC conclusion independent of omitted full analog initialization in the diagnostic. Increasing a wait limit cannot add conversion behavior to this implementation.

Full decoded method inspection remains in ignored `tmp/simantic/audit/adc-review/backend-inspection.json`; [results.json](results.json) stores the compact findings, source/assembly hashes, expected values and input-binding errors. [adc-uart.txt](adc-uart.txt) preserves the actual firmware output.

## Remaining test limitations

**Bring-up correction:** while preparing [ADC1 PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168), the original diagnostic was found to omit `SENS.SARADC_CLK_EN` at offset `0x104`, bit 30. Its power value `3` follows ESP-IDF v5.5.2 S3 `sar_ctrl_ll_set_power_mode`, although TRM v1.8 labels the force-power values oppositely. The PR follows the shipping driver and explicitly requests silicon review of that discrepancy. A new fixture calls the actual LL power/ADC functions: all 45 observations match the patched model, while the identical corrected ELF still never sets DONE in original 0.5.7. Thus the missing-conversion conclusion remains supported; the older handwritten probe alone should not be treated as complete hardware initialization evidence. Historical source/ELF hashes above are preserved.

The diagnostic is still bare metal, with the second CPU parked. It does not run the complete ESP-IDF reset/ROM/RTOS path, pad initialization, analog calibration, or the intended high-attenuation setup. Matching its basic handshake to LL source does not qualify the entire production driver.

After Simantic implements ADC1, the required acceptance test must run a pinned ESP-IDF application using `adc_oneshot_new_unit`, `adc_oneshot_config_channel` and `adc_oneshot_read`. Test actual analog input values and the agreed conversion/calibration model. Use the selected ESP32-S3 reference/attenuation contract when calculating expected raw counts. [Espressif driver guide](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32s3/api-reference/peripherals/adc_oneshot.html)

## Simantic bring-up request

1. Implement S3 ADC1 RTC one-shot channel selection, clocks/power/controller selection, START behavior, result and DONE semantics. Keep read-only bits read-only; resetting/restarting must not reuse stale completion/data.
2. Provide a documented per-channel voltage input, with units and input-update timing. The project supplies flex voltages; Simantic performs their conversion through the emulated peripheral.
3. State the implemented attenuation, reference, 12-bit quantization, saturation, inversion and calibration behavior. Preserve any existing temperature-sensor behavior when extending SENS.
4. Run a real ESP-IDF one-shot fixture across all five hand channels. Exercise zero/mid/high inputs, alternating channels, changing values over time, restart/reset and invalid configuration. Judge voltage accuracy against declared model tolerances.
5. Implement only the additional digital/DMA ADC modes actually required later; the first hand controller needs ADC1 one-shot reads. An APB ADC region upgrade alone does not automatically fix the separate SENS RTC path.

For timers, implement the S3-required TIMG counter/divider, UPDATE latch/self-clear, alarm and interrupt behavior, then validate the actual framework's timer/watchdog use. Keep SYSTIMER's existing narrow passes separate.

## Reproduce

Use the existing authenticated model/ELF/runtime from the [parent audit](../README.md). No credentials are stored here.

```sh
.venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/adc-review/inspect_backend.py
.venv-simantic/bin/python simulation/simantic/capability-audit/esp32s3/adc-review/recheck.py
SIMANTIC_HOME="$PWD/tmp/simantic/runtime" SIMANTIC_TELEMETRY=0 \
  .venv-simantic/bin/python simulation/simantic/capability-audit/stm32h7/sdk_adc_probe.py
```

The CLI confirmation uses the unchanged parent ADC ELF/model with `--timeout 1`, saves UART output and compares the extracted engine assembly hash. Runtime tests require normal access to Renode's user configuration lock. An initial sandbox lock denial was resolved for the test; it was not counted as a simulator defect.
