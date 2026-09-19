# ESP32-S3 ADC: same application on hardware and Simantic

This fixture uses the public ESP-IDF v5.5.2 one-shot and curve-fitting APIs.
The physical board and simulator run the same bootloader, partition table and
application binaries. The simulator additionally needs a ROM/flash wrapper ELF.
It tests ADC1 channels 0–9 (GPIO1–10); it does not drive these pins as outputs.

## Current status

- Physical ESP32-S3 revision v0.2 identified, with 8 MB flash and 8 MB PSRAM.
- Original flash backed up locally before flashing; backup is ignored and must
  not be published because it may contain the board owner's private data.
- Test firmware flashed successfully and its `info` and `ready` messages observed.
- Board identified from the user photo as Freenove ESP32-S3 WROOM. Its header
  label **1** is GPIO1 / ADC1 channel 0, verified against the
  [manufacturer pinout](https://github.com/Freenove/Freenove_ESP32_S3_WROOM_Board/blob/main/ESP32S3_Pinout.png).
- **Physical ground check passed: 256/256 reads**, 64 at each attenuation setting,
  on GPIO1 / ADC1 channel 0. Raw ranges were 0–45, 0–19, 0–9 and 0–6 counts for
  encodings 0, 1, 2 and 3. See the [physical record](evidence/physical-ground-2026-09-16/README.md).
  A USB power cycle resolved an initial silent serial session; its cause is unknown.
- **Physical nonzero-input check passed: 64/64 reads**, all raw 4095 at attenuation
  encoding 3 with GPIO1 connected to the board's nominal 3V3 rail. The rail was
  not measured with a meter. The ideal model predicts 3071 at exactly 3.3 V, so
  **silicon analog transfer fidelity remains unvalidated and differs at this
  nominal endpoint**. See the [rail record](evidence/physical-rail-2026-09-16/README.md).
- Full ESP-IDF application boots in Simantic 0.5.7 with the ADC implementation
  from [PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168)
  loaded as a namespace-only overlay. Expanded run: **120 batches / 960 successful reads**, covering ten channels,
  four attenuation settings and three input levels. A further nominal 3.3 V model
  run passed 40 batches / 320 samples against the ideal formula, yielding 3071
  at attenuation 3, confirming the nominal endpoint difference above.
  Those simulator dumps are **regenerable and not committed** - re-run
  `run_sim.py` to reproduce them. The physical captures under `evidence/` are
  committed, because they measure real hardware and cannot be regenerated.
- SDK `read_uart` duplicated/interleaved fragments in this run. Direct UART0
  `CharReceived` capture is clean and is used for assertions in `run_sim.py`.
  This isolates a capture-path issue; the cause within that path is not established.

## Build

Activate an ESP-IDF **v5.5.2** environment with the matching Espressif Xtensa
compiler, CMake and Ninja. From this directory:

```sh
idf.py -B /absolute/path/to/build -D IDF_TARGET=esp32s3 build
```

Use an out-of-tree `SDKCONFIG` too if you do not want a generated config here.
The configuration uses UART0 at 115200, one CPU, no PSRAM, DIO 40 MHz and a 4 MB
flash layout. An 8 MB board emits a harmless size warning and uses the configured
4 MB layout. A single-core application does not validate multicore behavior.

Before replacing existing firmware, identify the board/port and save its flash.
Use the generated `flash_args`/ESP-IDF flashing tools with the correct port.
The connected WCH USB-to-UART bridge needed manual download mode (BOOT + RESET)
and esptool `--before no_reset`; automatic reset initially failed without writing.
After flashing, verify the fixture identifier `palmpilot-adc-v1` over UART.

## Physical capture

Confirm the board pinout first. For a zero-input test connect **GPIO1 to GND**.
Do not substitute an Arduino D1 alias unless its mapping has been verified.
Keep other external circuits disconnected for this bench check.

```sh
python capture_serial.py --port /dev/cu.YOUR_PORT --channel 0 --attenuation 3 \
  --count 64 --input-mv 0 --note 'Verified GPIO1 connected to GND' \
  --elf /absolute/path/to/build/palmpilot_adc_validation.elf \
  --out /absolute/path/to/new-capture-directory
```

Requires PySerial. Opening some serial bridges can reset a board even when the
script requests inactive DTR/RTS. The script allows boot time and then queries
`info` before sending the measurement command. It preserves UART text and JSON
samples with firmware hash, input condition, timestamps and conversion statuses.
A complete batch requires the requested channel/attenuation, exact sample count,
ordered indices, matching batch IDs and successful reads. The 64-count ground
limit is a bench smoke-test criterion, **not an ESP32-S3 accuracy specification**.

Next physical stages: ground at all four attenuation settings; measured nonzero
voltages; channel switching; repeatability. Record the actual voltage with a
meter and the source wiring. Do not use an unknown or floating input as a known
voltage. Input voltage limits come from the silicon/board documentation, not the
model's ideal saturation formula. Full-scale model sweeps are not wiring advice.

## Simulation

Prepare the rendered S3 platform and PR overlay following the PR's
`tools/esp32s3_adc1_check/README.md`. Pack the exact flashed components with
esptool `merge_bin`, preserving offsets from `flash_args`. Then use mcu-lib's
`esp32s3_build_image.py` to package the merged image with Espressif's S3 ROM.
Record both source revisions and the resulting hashes.

```sh
python run_sim.py --platform /path/to/ESP32-S3-WROOM-1-N8R2.repl \
  --image /path/to/validation-sim.elf \
  --app-elf /path/to/palmpilot_adc_validation.elf \
  --overlay /path/to/S3AdcUnderTest.dll --out /path/to/new-simulation-directory
```

The matrix injects 0, 500000 and 900000 microvolts, exercises all ten ADC1
channels and all four attenuation settings, and takes eight samples per batch.
It checks completion and the PR's declared ideal transfer function. That is
**model-contract validation**, not proof of accurate silicon voltage readings.
Only voltage inputs are injected; result registers and firmware are not patched.
The N8R2 simulator and connected board differ in PSRAM capacity and chip revision;
PSRAM is disabled in this fixture. Simulated eFuse calibration is not the board's
factory calibration. A successful calibration API call does not establish
calibrated-voltage fidelity.

## Protocol and limits

Commands: `info`, `regs`, `read CHANNEL ATTENUATION COUNT`.
Attenuation is the ESP-IDF enum encoding 0–3; count is 1–1024.
JSON output includes configuration status, raw samples, calibration status/mV,
firmware timestamps and elapsed API time. The latter is observable output only:
the ADC model completes synchronously and does not validate conversion timing.

Register snapshots expose the force-power field and clock gate for checking the
TRM/driver discrepancy. ESP-IDF writes power encoding 3 for ON; the model follows
that driver. Hardware register readback shows encoding 3 with the ADC clock enabled,
followed by successful physical conversions. This supports the ON encoding; OFF
was not independently isolated on silicon. ADC2, DMA/continuous sampling, ADC interrupts, analog noise,
nonlinearity, self-calibration trims and full controller/drone firmware are outside
this validation.

## Next bench session

Use a multimeter to measure the actual ADC pin voltage relative to board GND.
A 10 kΩ potentiometer across the board's 3V3/GND, with its wiper connected to
GPIO1, provides adjustable input; establish the wiring with USB disconnected.
A small series resistor and a 100 nF capacitor at the ADC input can help protect
against accidental output configuration and reduce noise; document their values
when comparing results. Set and measure the voltage before each batch.

Start with approximately 0.2, 0.5 and 0.8 V at every attenuation setting, then
extend within the documented range for each setting. At attenuation 3, add about
1.5, 2.0 and 2.5 V. Record measured voltages, supply voltage, raw distributions,
calibrated output and firmware hashes. Inject those measured voltages into the
simulator, then quantify the difference. The currently used reference/attenuation
formula is explicitly ideal; a silicon-aligned curve requires evidence at more
than one voltage. Recheck the exact datasheet revision/ranges before extending
the sweep. Do not equate nominal rail voltage with a measured calibration point.

The user plans to obtain a multimeter; this is pending bench work, not a scheduled
or automatically executable test. Current board firmware is the ADC fixture,
and the most recently confirmed jumper connects GPIO1 to 3V3.
