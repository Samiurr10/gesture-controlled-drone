# Bench tests: the simulation suites on real boards

Each simulation suite in `firmware/tests/` gets a bench procedure here: what to wire, what to flash,
what to send on the console and what must come back. Start with one hand, one finger, and add a
part at a time. Every part goes into the hole it has on the finished hand, so each bench only adds
to the one before.

A bench PASS is a physical result and a simulation PASS is not; keep them separate (CLAUDE.md
section 7). Nothing here has been run on hardware yet. Each procedure is a plan until someone does.

## Order

| bench | what | simulation suite | test plan | board | wiring |
|---|---|---|---|---|---|
| [00](00-board-check/README.md) | bare board, ADC reference app | A0 (toolchain self-test) | B0 | LEFT | one jumper, removed after |
| [01](01-s1a-one-flex/README.md) | one flex channel, thumb | S1-A (part) | B1 | LEFT | new: thumb circuit, rails |
| [02](02-s1a-five-flex/README.md) | five flex channels | S1-A | B2 | LEFT | adds 4 fingers |
| [03](03-s1d-motion/README.md) | external motion module | S1-D | B2 | LEFT | adds #5543 |
| [04](04-s1b-calibration/README.md) | calibration | S1-B | B2 | LEFT | none |
| [05](05-s1c-enable-control/README.md) | ENABLE, control states | S1-A, S1-C | B3 | LEFT | adds ENABLE |
| [06](06-s1e-attitude/README.md) | tilt mapping, gestures | S1-E | B3 | LEFT | none |
| [07](07-s1f-persistence/README.md) | calibration persistence | S1-F | B3 | LEFT | none |
| [08](08-s1g-packet/README.md) | hand packet | S1-G | B3 | LEFT | none |
| [09](09-s1h-watchdog/README.md) | task watchdog | S1-H | B3 | LEFT | none |
| [10](10-right-hand/README.md) | the RIGHT hand | S1-A to S1-H | B4 | RIGHT | full RIGHT hand |
| [11](11-s2a-link/README.md) | two hands linked to the hub | S2-A | B5 | all three | hub |
| [12](12-s2b-controller/README.md) | the whole controller | S2-B | B5 | all three | none |
| [13](13-s3-host/README.md) | hub to the laptop | S3-A, S3-B | B6 | HUB | none; partly BLOCKED |

Calibration comes after the IMU on the bench (simulation runs S1-B before S1-D) because `cal finish`
needs a neutral orientation from the motion module.

## You need

- Three ESP32-S3-DevKitC-1 boards labelled LEFT, RIGHT, HUB, and a data-capable USB cable each.
- Two full (830-hole) breadboards and one half (400-hole), jumper wires.
- Per hand: five flex sensors (Adafruit #1070), five 47k, five 100nF, one Adafruit #5543.
  LEFT and HUB each add one 10k, one 100nF, one 1k and a normally-open push button.
- A multimeter. An oscilloscope helps for debounce and settling; a logic analyser is optional.

**Board variant:** the diagrams use genuine DevKitC-1 header positions. CLAUDE.md records the actual
ADC bench board as a **Freenove ESP32-S3 WROOM**, whose headers differ. On that board wire by **GPIO
number** (the silkscreen), not by header position, and record the mapping you used. The firmware is
built without PSRAM, so the Freenove's 8 MB PSRAM does not change it.

## Build and flash

The toolchain is the pinned one in `tmp/simantic/` (CLAUDE.md section 3). Plug into the DevKit port
marked **UART**; on macOS it shows up as `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial-*`.

```sh
python3 firmware/tools/palmpilot.py build hand:left      # or hand:right, hub
python3 firmware/tools/palmpilot.py pack  hand:left      # prints the app ELF sha256: record it
. firmware/tools/env.sh
"$IDF_PYTHON_ENV_PATH/bin/python" -m esptool --chip esp32s3 -p $PORT -b 460800 \
    write_flash 0x0 tmp/palmpilot/hand-left/flash.bin    # hand-right/, hub/
```

`flash.bin` is the same bootloader, partition table and application the simulator runs; only the
simulator's ROM wrapper differs (firmware/README.md). If esptool cannot connect, hold BOOT, tap RESET,
release BOOT and try again. The bench board's WCH USB-to-UART bridge needed exactly that, plus
`--before no_reset`, when the ADC reference app was flashed on 2026-09-16
(`simulation/simantic/hardware-validation/esp32s3-adc/README.md`).

## Console and logs

```sh
"$IDF_PYTHON_ENV_PATH/bin/python" firmware/tools/bench.py $PORT
```

Type commands; every reply is printed and saved with the host time to `tmp/bench/<time>-<port>.log`.
`--send CMD` (repeatable) and `--for SECONDS` script a short run. Then:

```sh
python3 firmware/tools/bench_summary.py tmp/bench/<log>     # per-channel mV / raw, or hub rate and steps
python3 firmware/tests/packet_decode.py <hex>               # a hand `packet` reply
```

Hand commands: `info`, `sample`, `stats`, `control`, `motion`, `packet`, `link`, `stream N`,
`stall N`, `profile`, `reboot`, `cal extended | curled | neutral | finish | reset | save | load |
erase | corrupt`. Hub commands: `status`. The hub prints a `command` line every 20 ms by itself.

## Reading the wiring tables

Holes are `<column><row>`: `45e` is column 45, row e. Rows a-e of one column are one strip; f-j another.
The rails are the + and - rows along the top and bottom; any hole of a rail is the same connection,
so "by column 47" says where the part sits, not which hole it must use. Each hand's 3V3 and GND go to
the bottom rails and two jumpers at the right end carry them to the top rails.

## Rules

- USB power only; no battery until a reviewed power design exists. GPIO10 stays disconnected.
- Never put 5 V or a battery on any ADC pin.
- Unplug USB before changing wiring.
- One board's supply per breadboard; no wire between boards.
- Set every numeric limit in the test record before the run. Limits marked PROVISIONAL come from the
  firmware and the simulation suites and are not qualified.
- Record for each run: board identity, the app ELF sha256, the log, meter readings, a photo, and
  PASS / FAIL / BLOCKED per step.

## Regenerating

The wiring files come from `docs/wiring/gen_wiring.py` (`BENCH`); the pictures are rendered
with pinplanner as described in `docs/wiring/README.md`.
