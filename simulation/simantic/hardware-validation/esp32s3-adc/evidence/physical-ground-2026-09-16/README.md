# Physical ADC1 ground check — 2026-09-16 America/New_York

**256 / 256 public ESP-IDF ADC reads completed successfully** on the Freenove
ESP32-S3 WROOM (S3 revision v0.2, 8 MB flash / 8 MB PSRAM; PSRAM disabled).
The same application ELF used for the simulator matrix was flashed to this board.

Input: GPIO1 (header label **1**) connected directly to GND, confirmed by the
user after identifying the board using its photo and the manufacturer's pinout.
This checks channel 0 only on hardware. No meter-based voltage measurement was
made. The four settings use enum encodings 0–3.

| Attenuation encoding | Samples | Raw minimum | Raw maximum | Raw mean |
|---|---:|---:|---:|---:|
| 0 | 64 | 0 | 45 | 4.781 |
| 1 | 64 | 0 | 19 | 3.109 |
| 2 | 64 | 0 | 9 | 1.406 |
| 3 | 64 | 0 | 6 | 0.156 |

The predefined ground smoke-test limit was 64 raw counts, not a silicon accuracy
specification. Real measurements show noise/offset; the ideal simulator returns
exactly zero. This evidence does not establish nonzero-voltage gain, linearity,
calibrated millivolt accuracy, conversion timing or other physical ADC channels.

All four register snapshots report `power=0x60000000` (FORCE_XPD_SAR=3),
`clock=0x40000000` (SARADC clock enabled), and ADC reset deasserted. Successful
reads following those snapshots support the shipping ESP-IDF ON encoding used
by the patch despite the conflicting TRM label. This does not independently test
the OFF encoding: the driver's OFF operation also disables the clock.

`adc_cali_create_scheme_curve_fitting` and per-sample conversion returned success.
Ground-only calibrated values do not validate the simulated factory trims or
nonzero-voltage conversion curve. Recorded `read_us` values are API elapsed time,
not isolated ADC conversion latency.

The initial serial session went silent even though the USB bridge remained
visible. Automatic reset, manual EN/RST and removal of the jumper did not restore
output. Unplugging/reconnecting USB restored normal boot and command responses;
no firmware change was made. The cause of that communication failure is unknown.

See `summary.json` and each `attenuation-N/results.json` / `uart.txt` for samples,
registers, timestamps and the common firmware hash. The original flash backup
is intentionally local-only and is not included. Next: measured nonzero inputs
and physical channel switching. The subsequent [rail check](../physical-rail-2026-09-16/README.md) changes
the bench wiring to GPIO1-to-3V3.
