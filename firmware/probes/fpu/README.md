# FPU model gap — ESP32-S3 in Simantic

**Finding, 2026-09-18:** executing the **first Xtensa single-precision FPU
instruction** aborts the simulation engine. The guest does not fault and the
firmware reports no error; the host call raises:

```
simantic.mcu.SimError: Collection was modified; enumeration operation may not execute.
```

Deterministic, not a scheduling race — it reproduced identically on every run.

## Why this probe exists

This is the reason PalmPilot firmware uses **fixed-point milli-units** and
contains no floating point on the control path. Keep the probe: it is the
regression test for any engine upgrade, and a passing run is the precondition
for reconsidering floating point in this firmware.

```sh
python3 firmware/tools/palmpilot.py run firmware/probes/fpu firmware/probes/fpu/run.py
```

## Environment

- Simantic CLI/engine 0.5.7, Python SDK 0.3.1, ESP-IDF v5.5.2.
- Platform `ESP32-S3-WROOM-1-N8R2`, ADC overlay **not** loaded.
- `CONFIG_FREERTOS_UNICORE=y`, PSRAM disabled, single-core application.

## Observed output

The probe prints a stage marker before each operation, so the failing
instruction is identifiable:

```json
{"type":"ready","fixture":"palmpilot-fpu-probe"}
{"type":"stage","name":"int_to_float"}
ENGINE ABORTED: Collection was modified; enumeration operation may not execute.
```

The aborting statement is `volatile float a = (float)s_numerator;` in
`app_main` — an integer-to-float conversion on a volatile int. Nothing beyond
`int_to_float` runs, so `float_divide`, `float_multiply`, `float_compare` and
`float_print` are **untested and their status is unknown**.

## Interpretation, and its limits

The error shape is consistent with the **lazy coprocessor-enable path**: on
Xtensa the first FPU instruction in a task raises a Coprocessor Disabled
exception, which FreeRTOS services by reassigning coprocessor ownership. A host
collection appears to be enumerated while that bookkeeping mutates it.

This is inference from the error text and the isolation point, **not** a
diagnosis confirmed against engine source. No engine source was inspected.

Established: a plain FPU instruction, in ordinary single-core ESP-IDF firmware,
aborts the run. **Not** established: which component is at fault, whether other
coprocessor paths behave the same, whether other platforms or engine versions
are affected, or how the physical board behaves — **silicon was not tested.**
The ESP32-S3 has a real FPU and this record says nothing about it.

## Effect on the controller

Curl normalisation, deadband rescaling and all gesture mapping are integer-only
in milli-units (0–1000). That is a sound embedded choice for a fixed-rate
control loop independently of this defect, and it removes a dependency on an
unqualified model path.

ESP-IDF's own `adc_cali_raw_to_voltage` continues to work and is used
unchanged, so whatever arithmetic it performs does not reach this path.

## Follow-up

| Item | Owner | Action |
|---|---|---|
| Engine abort on FPU use | Simantic | Reproduce with this probe; identify the mutated collection |
| Remaining FP operations | Project | Unknown — only `int_to_float` was reached; retest later stages once fixed |
| Physical FPU behavior | Project | Untested. Run the same probe on the Freenove board at C1 |
| Controller arithmetic | Project | **Done** — fixed-point, no FP on the control path |
