# ESP32-S3 ADC voltage-response diagnosis — September 18, 2026

**Follow-up implementation:** a selectable, factory-calibration-compatible
behavioral approximation now passes the voltage regressions. See
[candidate fix and validation](#candidate-fix-and-validation) below. The original
ideal mode still has the mismatch described in the initial diagnosis.

## Finding

The raw-count mismatch is reproducible on the simulator side using the known
GPIO1/GPIO2 measurements. No GPIO4 measurement is used in this diagnosis.
The existing PR implements an explicitly ideal voltage-to-count formula; it
does not model the same analog response as the measured, calibrated board.
Its simulated calibration data and transfer function are also not mutually
consistent at the higher attenuation settings.

This establishes conversion functionality, not analog-fidelity acceptance.
Different chips can legitimately produce different raw counts because their
factory calibration differs. The stronger model check is whether its own
calibrated result agrees with the injected voltage within a declared tolerance.

## Controlled evidence

Physical board: Freenove ESP32-S3 WROOM N8R8. Firmware: ESP-IDF v5.5.2 ADC fixture.
Simulation: engine 0.5.7, SDK 0.3.1, N8R2 platform, ADC PR #168 overlay.
Read-only esptool verification matched the board's bootloader, partition table
and application to the corresponding bytes in the simulator's flash image.
The simulator ELF's flash segment was also compared byte-for-byte. No reflashing
was needed; the later local ELF rebuild is not the executed image.

User measured **0.849 V**, steady on a Keysight 34460A. GPIO1: five batches of 64
reads at each attenuation, 1280 physical and 1280 simulated reads. GPIO2: one
batch of 64 at each attenuation, 256 reads on each platform. All conversions
and calibration calls completed successfully. The meter report is manual,
rounded and not time-synchronized; instantaneous ADC noise remains present.

| Attenuation | GPIO1 raw mean | Simulated raw | Simulated calibrated mV | Injected mV |
|---|---:|---:|---:|---:|
| 0 dB | 3625.97 | 3160 | 839 | 849 |
| 2.5 dB | 2715.65 | 2370 | 838 | 849 |
| 6 dB | 1898.15 | 1580 | 790 | 849 |
| 12 dB | 1006.95 | 790 | 747 | 849 |

Physical calibrated averages were 847.89, 846.24, 844.23 and 841.97 mV.
GPIO2 raw means differed by less than 0.5% from these GPIO1 means at this point.
At the earlier approximately 1.69 V input, attenuation 3 returned a physical
raw mean of 2051.19 and calibrated mean of 1689.36 mV; the model returned 1572
and 1460 mV. The subsequent 1.697 V meter report was not simultaneous with that
first batch, so it must not be used for a precise error estimate.

## Source-level cause

1. `ESP32S3_Sens.StartAdc1Conversion` uses
   `floor(Vin_uV * 4095 * (4 - attenuation) / (4 * 1100000))`, capped at 4095.
   At attenuation 3, 849000 µV therefore produces **790** exactly. Input binding,
   unit conversion and channel selection do not explain this raw-count result.
2. The platform uses `ESP32C3_Efuse`. Its default BLOCK2 readback is
   `[0, 0, 0, 0, 1, 0, 0, 0]`: calibration version 1, zero calibration deltas.
   ESP-IDF decodes ADC1 reference counts of **3200, 2400, 1700, 900** at 850 mV.
   These are not the board's factory calibration profile.
3. ESP-IDF converts counts using those reference counts plus its per-attenuation
   polynomial correction. Reproducing its integer arithmetic exactly explains
   the simulator's reported millivolts in every recorded sample tested.
4. The hardware-trim path writes DREF and initial calibration codes via internal
   analog I2C. The analog-register model stores those bytes, but the ADC's
   conversion formula does not consume them. The diagnostic observed default
   initial codes 1850, 1940, 1940 and 2010 reaching that register storage.
   Their physical effect is not modeled; its magnitude is not isolated here.

The board's ADC1 software-calibration reference counts can be uniquely inferred
as **3630, 2723, 1909, 1013** from 1600 captured raw/calibrated-value pairs using
the pinned IDF arithmetic. These are inferred from output pairs, not a direct
physical eFuse read. Calibration register words or keys were not read from or
written to the physical board during this investigation.

## Simulator-only causal tests

Same unchanged firmware, channel 0, two input levels (849000 and 1690000 µV),
four attenuations and eight samples per case: **192 conversions completed**.
The diagnostic fixtures alter only simulator properties/eFuse storage, never
firmware result registers, firmware code, or the physical board.

| Case at 849 mV, attenuation 3 | Raw | Calibrated mV |
|---|---:|---:|
| Original PR model and default simulated calibration | 790 | 747 |
| Only substitute inferred board software-calibration fields | 790 | 666 |
| Only change model reference to 958822 µV, fitted to attenuation 0 | 906 | 853 |

Copying calibration data alone leaves all raw values unchanged and does not fix
the mismatch. A single adjusted reference matches attenuation 0 raw at this
point, but still misses attenuation 3 raw by about 10%; it also makes the
attenuation 0 calibrated result 959 mV for an 849 mV input. Neither is a valid
universal fix. These experiments do not establish an exact silicon transfer
curve or independently validate the inferred board calibration fields.

## Required model work

- Do not add a correction multiplier or tune a reference to these measurements.
  Establish the S3's per-attenuation analog behavior and its relationship to
  hardware trim, then supply consistent simulated factory-calibration data.
- Specify which internal hardware-trim effects are implemented or approximated.
- Retain the register/protocol regression tests, then add independent voltage
  round-trip checks through the public calibration API over a voltage sweep.
  Checking only the same ideal formula used by the model cannot establish
  analog fidelity.
- Validate against additional independent measured input points. The available
  evidence does not establish the exact physical transfer function or an exact
  implementation of the missing hardware-trim effects. ADC2/DMA remain outside
  this one-shot PR.

No new ADC model coefficients or PR source changes were made in the initial
diagnosis. The physical board was not accessed during that simulator-only phase.
GPIO4's reported 1.93 V remains an unresolved separate observation; it does not
invalidate the verified GPIO1/GPIO2 evidence or explain the simulator formula.

## Follow-up: other MCU implementations and input-path recheck

No correction multiplier was added. The earlier reference-adjustment experiment
above was a rejected diagnostic, not a source change or a proposed fix.

| Model inspected | Input and conversion behavior | Relevance to S3 |
|---|---|---|
| `ESP32C3_SarAdc` | `SetChannelValue` injects raw 12-bit counts; attenuation does not change them | Tests software transactions, not voltage-to-count fidelity |
| `ESP32P4_Adc` | Boot support: DONE bits and register storage; no sample conversion | No analog transfer behavior to reuse |
| Legacy `STM32_ADC` | `FeedSample` queues raw counts | Also bypasses voltage conversion |
| `STM32H7_ADC` / `STM32_ADC_Common` | IADC voltage sources, configured reference and resolution; calibration completes immediately without changing the transfer | S3 already uses the same IADC input mechanism, but needs S3-specific analog behavior |

Fresh runtime checks against engine 0.5.7:

- **C3: 32 register-level conversions passed**, using two channels, four injected
  raw values and all four attenuation encodings. Returned raw values always
  equaled the injected counts. This was a peripheral test, not a C3 firmware run.
- **H7: eight firmware-command conversions passed** on the H743 fixture using
  `Analog.STM32H7_ADC`, ADC channel 10, 16-bit resolution and a 3.3 V reference.
  0.849 V returned 16860; 1.65 V returned 32768; 3.3 V returned 65535.
  A separate precision limitation was reproduced: 849000 and 849999 microvolts
  both returned 16860 because `GetSampleFromChannel` divides an integer voltage
  by 1000 before conversion. Input readback itself preserves microvolts.
- **S3: 256 unchanged-firmware conversions passed** across channels 0/1,
  four attenuations and inputs 849000, 849999, 850000 and 1690000 microvolts.
  All input readbacks exactly matched the requested microvolts. Results matched
  the existing declared ideal formula, including its mismatch with hardware.
  These are interface/regression passes, not analog-accuracy passes.

The H7's rounding instead of truncation would change an S3 result by at most
one count. Using 4096 instead of 4095 changes scale by about 0.024%. Neither
explains the measured 13–22% raw-count deficit at 0.849 V. Copying the H7's
millivolt truncation would discard precision. Copying C3 raw injection would
bypass the voltage response under investigation. No applicable bring-up change
from these models fixes the S3 discrepancy.

## Follow-up: is the physical fluctuation expected?

Some ADC noise is expected, but these captures do not prove that all observed
outliers are normal or within specification. Espressif documents S3 ADC noise
sensitivity and recommends input bypass capacitance and multisampling where
needed. The bench had no input bypass capacitor. The meter photograph showed a
10 PLC aperture, so its steady display averages over a longer interval than an
individual ADC conversion; it does not rule out shorter disturbances.

At the user-reported steady 0.849 V, the existing captures show:

| Capture | Samples per attenuation | Standard deviation of calibrated readings, across the four settings |
|---|---:|---:|
| GPIO1, five batches | 320 | 13.8–16.3 mV |
| GPIO2, one batch | 64 | 2.4–6.8 mV |

These are population standard deviations, not measurement uncertainty or a
datasheet acceptance limit. At attenuation 3, GPIO1 individual readings ranged
790–947 mV, while its five 64-sample batch means ranged 839.6–844.2 mV. GPIO2
was quieter in its shorter capture; this does not isolate the cause to a pin,
wiring, supply noise or settling. Its mean raw count still agreed with GPIO1
within 0.5%. Hardware noise therefore does not explain the simulator's stable
790 counts versus the board's approximately 1002–1007 counts at this setting.

The simulator produces deterministic samples for a fixed input; noise and
source-impedance/settling effects are not implemented. Its independent failure
is that **849 mV injected becomes 747 mV through the public calibration API** at
attenuation 3. A raw count need not match every individual chip, but the model
must be consistent with its own exposed calibration data. The exact analog
effect of DREF/initial-code settings remains unquantified, so attributing the
entire deficit to one missing register effect would be premature.

## Candidate fix and validation

The user authorized failing tests, further source research and a necessary fix.
The candidate adds `CalibrationEfuse` to the S3 SENS model. Connecting it to the
same eFuse object read by firmware selects a calibrated-operating-state
approximation. Without that explicit connection, existing platforms retain the
original ideal TRM formula.

```repl
sens: Miscellaneous.ESP32S3_Sens @ sysbus 0x60008800
    CalibrationEfuse: efuse
```

Add the property to the existing declaration; `efuse` is the existing peripheral
at 0x60007000. The capitalized property name is required. In the local validation
overlay, only the SENS namespace changes to `AdcUnderTest`.

### Basis and limitation of the fix

The new mode decodes the actual simulated S3 ADC1 reference fields and inverts
Espressif's published smooth per-attenuation calibration characteristic to
produce a raw code. Firmware continues to execute its own integer calibration
API. The model does not patch firmware, bypass ADC registers, fit a correction
multiplier, or use this board's readings as default coefficients.

This repairs the **voltage/calibration inconsistency for firmware simulation**.
It assumes the driver has established the normal hardware-calibrated state.
It does not implement the physical effect of arbitrary DREF or initial-code
changes, calibration transients, noise, input impedance or sampling-time
effects. A complete trim-register transfer equation was not found in the
reviewed public sources. This must not be presented as full electrical ADC
bring-up or used to validate alternate hardware-calibration sequences.

Sources reviewed included S3 TRM v1.8 §39.3.5, datasheet v2.2 §5.5, the S3 errata
summary, Espressif hardware/software calibration documentation, the ADC range
extension description and the pinned ESP-IDF v5.5.2 LL/calibration/eFuse sources.
The published ADC erratum concerns ADC2 DMA, not this ADC1 RTC one-shot case.

### Independent read-only factory-data capture

After the user reconnected the board, only the ADC-related eFuse shadow words
were read. No flash or eFuse programming occurred; the board was reset back to
its existing firmware. Factory calibration version is 1; ADC1 voltage deltas
are 107/114/96/113, giving reference codes **3630/2723/1909/1013** at 850 mV.
This independently confirms the prior inference from raw/calibrated pairs.
Initial-code deltas are 91/38/26/35; ESP-IDF decodes 1941/2069/2095/2200.
The `espefuse adc_info` display applies its own scaling/sign presentation;
the recorded raw fields and pinned IDF decoder were used for the model fixture.

### Tests and results

- Four new NUnit voltage acceptance cases failed on the original model. Their
  bounds come from the independent ESP-IDF integer calibration calculation and
  datasheet error limits, not the original model's formula.
- The original full firmware also failed all four 849 mV acceptance cases:
  errors were 10/11/59/102 mV versus allowed 5/6/10/50 mV.
- The candidate passes **51 NUnit cases**, including the existing protocol tests,
  voltage bounds, monotonic response, saturation, factory profile selection,
  reset preservation and rejection of unsupported calibration versions.
- The unchanged full ESP-IDF firmware completed **2480 reads in 310 batches**:
  channels 0/1/3/4/5, all four attenuations, both default and physical factory
  profiles, and voltage points spanning each datasheet effective range.
  **Zero voltage-acceptance failures; worst calibrated error 3 mV.** These
  round-trip checks establish model/driver consistency, not independent silicon
  accuracy. The manufacturer curves also inform the firmware calibration.

| Input / attenuation | Original model raw | Candidate, default factory raw / mV | Candidate, board factory raw / mV | Earlier physical raw mean |
|---|---:|---:|---:|---:|
| 849 mV / 0 | 3160 | 3196 / 847 | 3626 / 848 | 3625.97 |
| 849 mV / 1 | 2370 | 2398 / 848 | 2720 / 848 | 2715.65 |
| 849 mV / 2 | 1580 | 1698 / 848 | 1907 / 848 | 1898.15 |
| 849 mV / 3 | 790 | 901 / 847 | 1014 / 847 | 1006.95 |
| Approximately 1690 mV / 3 | 1572 | 1822 / 1689 | 2051 / 1689 | 2051.19 |

These earlier physical samples were not used to fit the curve. The higher point
has an approximate, non-simultaneous meter reading and supports only a limited
comparison. Noise and full-range silicon accuracy still require controlled
physical validation. No new physical voltage-sweep readings were taken here.

This remains an opt-in candidate in ADC PR #168. Engine 0.5.7 and existing
mcu-lib platform declarations do not enable it automatically. The local test
platform explicitly sets the property. The full Infrastructure build and CLI
release integration are still outstanding; the tested assembly is an overlay.
The PR remains limited to its model, focused NUnit tests and one model document.
The candidate was pushed to the existing draft PR as commit `59fd3468`.

Local evidence is in `tmp/simantic/adc-transfer-review/fix/`: read-only factory
capture, before/after test logs, `firmware-before/results.json` and
`firmware-after-r2/results.json`. The first candidate firmware attempt stopped
before boot due to lowercase property spelling; the corrected second run is the
reported successful result. Raw captures and temporary runners stay local.

## Reproduction and source references

Detailed local captures and temporary scripts remain outside the published
package in `tmp/simantic/measured-adc-2026-09-18/` and
`tmp/simantic/adc-transfer-review/`.

- [ADC PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168), tested head `46e1d296afbdca9e7f1d80900def2b53ed9dfdc0`.
- [ESP-IDF v5.5.2 curve-fitting implementation](https://github.com/espressif/esp-idf/blob/v5.5.2/components/esp_adc/adc_cali_curve_fitting.c).
- [ESP-IDF v5.5.2 S3 factory-calibration decoding](https://github.com/espressif/esp-idf/blob/v5.5.2/components/efuse/esp32s3/esp_efuse_rtc_calib.c).
- [ESP-IDF v5.5.2 S3 correction coefficients](https://github.com/espressif/esp-idf/blob/v5.5.2/components/esp_adc/esp32s3/curve_fitting_coefficients.c).
- [ESP-IDF v5.5.2 noise guidance](https://docs.espressif.com/projects/esp-idf/en/v5.5.2/esp32s3/api-reference/peripherals/adc_calibration.html#minimize-noise).
- Follow-up local evidence: `tmp/simantic/adc-transfer-review/model-comparison.json`, `s3-input-recheck/results.json` and `noise-analysis.json`.
- [Controller implementation plan](../controller/simantic-plan.md).
