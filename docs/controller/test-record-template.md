# Controller test record

Copy this file for each test and hardware/firmware variant. Leave measurements blank until observed. Use **NOT RUN**, **PASS**, **FAIL**, or **BLOCKED**; only mark the corresponding checklist after a supported PASS. Store supporting captures and logs in the repository with relative links and avoid committing credentials or BLE bonding secrets.

## Identity and setup

| Field | Recorded value |
|---|---|
| Test ID / title (for example, CTRL-010) | |
| Date / operator | |
| Status | NOT RUN |
| Applicable checklist / procedure link | |
| Drawing revision / connection-list revision | |
| Left / right / hub board model and PCB revision | |
| Device identities / hand sides (nonsecret identifiers) | |
| Firmware commit / build target | |
| Board package / compiler / library versions | |
| Calibration version / file | |
| Pocket model / hardware / EdgeTX version | |
| Radio model export / hash | |
| Power source / battery identity and initial voltage | |
| Test instrument / probe / sample rate | |
| JP301 state / radio connected? | |
| Aircraft present? If applicable: props removed / motor output inhibited | |
| As-built photograph / setup diagram | |

## Procedure and acceptance limits — complete before testing

| Field | Recorded value |
|---|---|
| Preconditions / prior tests required | |
| Exact stimulus or fault injection | |
| Expected state and output | |
| Numeric pass limits / timing origin / endpoint | |
| Test duration / repetitions / worst-case load | |
| Stop condition / restoration procedure | |

## Measurements and evidence

| Measurement / observation | Expected limit | Actual result | Evidence link |
|---|---|---|---|
| | | | |
| | | | |
| | | | |
| | | | |

For loss/transfer tests, include failure onset, hand sample age, hub detection time, TR5 transition, last TR6 change, radio authority change and observed endpoint transition as applicable. State the clock/instrument used; do not subtract unrelated clocks without synchronization. For battery tests include both battery voltage and local `3V`, ADC values and load.

## Decision and restoration

| Field | Recorded value |
|---|---|
| Pass / fail / blocked reason | |
| Unresolved limitation / issue link | |
| Corrective change | |
| Retest ID / evidence | |
| Final restored state (JP301, power, radio model, test wiring) | |
| Reviewed by / date | |

**Completion rule:** missing evidence or an unmeasured limit is not a PASS. A successful wiring/firmware review does not replace the physical test.
