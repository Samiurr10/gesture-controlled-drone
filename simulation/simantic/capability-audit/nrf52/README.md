# nRF52840 runtime capability audit

> **Report snapshot:** this documentation package includes audit reports and concise results. Test sources, setup scripts and detailed traces referenced below remain local bench material; reproduction commands require that separate harness and are not runnable from this documentation checkout alone.

This is diagnostic firmware for Simantic 0.5.7, not PalmPilot controller firmware.
It tests observable register, DMA, interrupt and reset behavior on the downloaded
`NRF52840QIAA.repl`. The model name identifies the MCU; it does not assemble a
Feather Sense board or its sensors.

## Findings

The core paths below execute, but the present model cannot yet validate the full
hand controller. SAADC is absent from this model. TWIM has a working subset of
EasyDMA transfers, but required lifecycle events do not complete.

| Path exercised | Observed result | Scope / limitation |
| --- | --- | --- |
| Boot and UARTE0 EasyDMA TX | Pass | ELF boots and emits RAM-backed UART buffers. Host USB CDC is a separate path. |
| HFCLK / LFCLK | Pass | Start tasks produce their STARTED events. Frequency accuracy and clock switching are not measured. |
| GPIO | Pass | Output set/clear, output feedback through IN, input pull-up. |
| GPIOTE | Partial | Task toggling works from an explicitly cleared pin. Configuring OUTINIT=Low leaves a previously high P0.13 high (`0x2000`, expected `0`). |
| TIMER0 / NVIC | Pass | Compare event, event clearing and one IRQ8 delivery. |
| TIMER0 → PPI → GPIOTE | Pass | A timer event sets P0.13 through an actual PPI connection. |
| SAADC | Fail / missing registration | ENABLE reads `0` after writing `1`; STARTED and CALIBRATEDONE remain `0`. No analog stimulus was implemented. |
| Legacy TWI | Pass, limited | Absent address `0x7e` produces ERROR and address NACK; ERROR clears. |
| TWIM negative transaction | Pass, limited | ENABLE=`6` reads back; an absent slave produces ERROR and address NACK. |
| TWIM EasyDMA data transfer | Partial | BME280 fixture ID reads `0x60` when transactions are STOP-separated; register `0xf5` writes/reads `0xa0`; TX/RX AMOUNT and RX bounds guards pass. |
| TWIM lifecycle / repeated start | Fail | TXSTARTED, LASTTX, RXSTARTED, LASTRX and SUSPENDED remain `0`. The tested SUSPEND/RESUME repeated-start ID read returns `0x00`, expected `0x60`. |
| TWIM STOP / IRQ | Pass | STOPPED event, clearing and one IRQ3 delivery work. |
| NVMC erase/program path | Partial | Page erase, READY and an erase-then-program word work. A write incorrectly restores zero bits to one without erase; writes also succeed in read-only mode. Persistence across MCU reset or simulation restart is unverified. |
| WDT | Partial | Timeout actually resets and re-enters the ELF. RESETREAS reads `0x1`; the expected DOG bit `0x2` is absent. |

**Adafruit Wire compatibility is blocked by the observed TWIM lifecycle gaps.**
The current Wire implementation polls TXSTARTED and LASTTX, and waits for
SUSPENDED after `endTransmission(false)`. These bare-register probes exercise
that shape of transaction; **the full Adafruit application, Arduino core and
SoftDevice were not built or booted in this audit**. A bounded poll timeout in our
diagnostic lets later checks continue; it is not a production workaround.

The fixed-register BME280 is only a positive I²C bus fixture. It is **not** a model
of the Feather Sense LSM6DS3TR-C / LIS3MDL, and this audit does not generate hand
motion, flex, battery or other sensor input. The STOP-separated positive control
shows that TWIM is partially functional; it must not be classified as entirely
unsupported.

## Evidence and reproduction

- [results.json](results.json) records each assertion and observed/expected value,
  process completion, source/ELF/model/UART SHA-256 hashes and observation time.
- [register-diagnostics.json](register-diagnostics.json) preserves the relevant
  one-read-per-register SDK warnings. Specifically, `twi0` reports
  `Unhandled read from offset 0x14C.` and `Unhandled read from offset 0x150.`
  The other lifecycle events fail behaviorally without those warnings.
- Raw generated UART transcripts, traces, process output, ELF files, fixture
  platform and full SDK diagnostics are in `tmp/simantic/audit/nrf52/` and are not
  tracked. A zero CLI exit means the diagnostic ran, not that all assertions pass.

From the repository root, using the installed ARM GCC and authenticated/downloaded
model:

```sh
sh simulation/simantic/capability-audit/nrf52/build.sh
python3 simulation/simantic/capability-audit/nrf52/run.py
```

The runner invokes `~/bin/sim` with local `--repl` and `--elf`, a **one-second
virtual timeout** and a **40-second wall timeout per probe**. It sets
`SIMANTIC_TELEMETRY=0` and the .NET extraction directory. Renode must have normal
access to its user configuration lock; a sandbox denial for that lock is an
environment failure, not a peripheral result. Every firmware polling loop is
bounded. Each probe starts in a fresh simulation process.

Individual cases can be built/run without changing the rest:

```sh
sh simulation/simantic/capability-audit/nrf52/build.sh 7:twim_positive
python3 simulation/simantic/capability-audit/nrf52/run.py twim_positive
```

The optional diagnostic uses SDK 0.3.1 with the separately installed 0.5.7 engine:

```sh
SIMANTIC_HOME="$PWD/tmp/simantic/runtime" SIMANTIC_TELEMETRY=0 \
  .venv-simantic/bin/python \
  simulation/simantic/capability-audit/nrf52/inspect_register_logs.py
```

After a reviewed rerun, copy generated `results.json` here to refresh the checked-in
snapshot. `run.py` merges selected cases, so use a complete build and run when
refreshing the entire snapshot. Exact source hashes are per case.

## Probe design / register provenance

Register structures, addresses and field encodings come from Nordic's pinned
[nrf52840.h](https://github.com/NordicSemiconductor/nrfx/blob/v3.14.0/mdk/nrf52840.h)
and [nrf52840_bitfields.h](https://github.com/NordicSemiconductor/nrfx/blob/v3.14.0/mdk/nrf52840_bitfields.h).
The diagnostic has its own reset/vector table and linker script; it does not
depend on a vendor firmware SDK. The Adafruit compatibility comparison uses
[Wire_nRF52.cpp](https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/libraries/Wire/Wire_nRF52.cpp).

| Block | Register locations used |
| --- | --- |
| CLOCK / POWER | Base `0x40000000`; HFCLKSTART `+0x000`, LFCLKSTART `+0x008`, STARTED `+0x100/+0x104`, RESETREAS `+0x400` |
| GPIO / GPIOTE | GPIO0 OUT `0x50000504`, IN `0x50000510`, PIN_CNF `0x50000700`; GPIO1 IN `0x50000810`; GPIOTE base `0x40006000`, CONFIG[0] `+0x510` |
| TIMER0 / PPI | Bases `0x40008000` / `0x4001f000`; TIMER COMPARE0 `+0x140`, PPI EEP/TEP[0] `+0x510/+0x514` |
| SAADC | Base `0x40007000`; ENABLE `+0x500`, START `+0x000`, CALIBRATEOFFSET `+0x00c`, STARTED `+0x100`, CALIBRATEDONE `+0x110` |
| TWI / TWIM0 | Base `0x40003000`; ERROR `+0x124`, ERRORSRC `+0x4c4`, ENABLE `+0x500`, ADDRESS `+0x588` |
| TWIM lifecycle | STOPPED `+0x104`, SUSPENDED `+0x148`, RXSTARTED `+0x14c`, TXSTARTED `+0x150`, LASTRX `+0x15c`, LASTTX `+0x160` |
| TWIM EasyDMA | RXD PTR/MAXCNT/AMOUNT `+0x534/+0x538/+0x53c`; TXD PTR/MAXCNT/AMOUNT `+0x544/+0x548/+0x54c` |
| NVMC | Base `0x4001e000`; READY `+0x400`, CONFIG `+0x504`, ERASEPAGE `+0x508`; reserved test page `0x000f0000` |
| WDT | Base `0x40010000`; START `+0x000`, RUNSTATUS `+0x400`, CRV `+0x504`, RREN `+0x508`, CONFIG `+0x50c` |

Public RAM symbols `probe_gpio0_in`, `probe_gpio1_in` and `probe_ticks` support
separate host-side observation. UART uses UARTE0 (`0x40002000`) EasyDMA with buffers
in RAM, not flash. WDT uses a retained RAM cookie to prove that reset re-entered
the executable. Its reset marker appears about 0.10 virtual seconds after arming
CRV=3277; cycle-accurate timing is not asserted.

## Next acceptance gate

Complete SAADC separately, then rerun the TWIM lifecycle and repeated-start
checks against a corrected model. After those pass, boot the actual selected
Adafruit/Bluefruit firmware and verify its exact sensor-driver sequence. Board
sensors, USB enumeration, BLE/SoftDevice, RTC, all peripheral instances and
external QSPI storage are **not covered by this nRF probe suite**; see the overall
capability audit for other agents' results. NVMC write restrictions, WDT reset
reason and GPIOTE initialization need fidelity fixes before using those paths for
fault-handling acceptance tests. The NVMC probe does not qualify the complete
calibration-storage path: reset/restart persistence and the application's selected
storage backend still require validation.
