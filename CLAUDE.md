# PalmPilot — working constraints for Claude

Read this before changing anything. It records constraints that are **already
decided and evidenced** in this repository. Where a value is marked UNSET, it is
genuinely unfrozen — do not invent one.

## 1. Scope — what is and is not being built

**We physically build the hand controller. The drone is simulated and moves on a
computer screen. No physical drone, airframe, motor, ESC, propeller or flight
test is in scope.** Scope pivot dated 2026-09-16; it supersedes the earlier
physical-aircraft plan, the aircraft portions of the original BOM, and the
aircraft sheets of the Rev A schematics.

Execution order, strictly:

| Phase | Gate | Meaning |
|---|---|---|
| Goal 1A | **S0–S3** | Controller simulated in Simantic |
| Goal 1B | **C0–C7** | Physical hand-controller prototype |
| Goal 2 | **D1–D4** | Virtual drone MCU → dynamics → screen |

Current position: **S0 in progress.** No S, C or D checkbox is complete.
Drone feasibility probes are authorized in parallel but never mark a controller
milestone complete.

The display must never move the drone directly from a gesture. Displayed motion
has to pass through the simulated drone MCU's motor outputs and the mechanical
model. A gesture-driven animation does not satisfy Goal 2.

## 2. Hardware baseline

**Controller MCU: ESP32-S3** (replaced Feather nRF52840 on 2026-09-16).
Three boards: LEFT hand, RIGHT hand, HUB (BLE central).

| Target | Board |
|---|---|
| Simulation reference | ESP32-S3-DevKitC-1 / **ESP32-S3-WROOM-1-N8R2** (8 MB flash, 2 MB quad PSRAM) |
| Physical ADC bench board (actual) | **Freenove ESP32-S3 WROOM**, silicon rev v0.2, 8 MB flash / **8 MB** PSRAM |

The two differ in PSRAM and chip revision. Validation firmware runs **single-core
with PSRAM disabled**; multicore and PSRAM operation are not established.

### Pin map — frozen, use exactly

| Function | GPIO | ADC1 ch | Notes |
|---|---|---|---|
| Thumb flex | GPIO1 | CH0 | each hand |
| Index flex | GPIO2 | CH1 | each hand |
| Middle flex | GPIO4 | CH3 | each hand |
| Ring flex | GPIO5 | CH4 | each hand |
| Little flex | GPIO6 | CH5 | each hand |
| ENABLE | GPIO7 | — | **LEFT only**, active low, external pull-up |
| CALIBRATE | GPIO7 | — | **HUB only**, active low |
| Motion SDA | GPIO8 | — | each hand, configure explicitly |
| Motion SCL | GPIO9 | — | each hand, 100 kHz initially |
| Battery sense | GPIO10 | CH9 | **RESERVED, LEAVE DISCONNECTED** |

Reserved / forbidden: **GPIO19/20** native USB, **GPIO43/44** UART0 bridge,
**GPIO0/3/45/46** strapping. GPIO3 is deliberately skipped in the flex sequence.
Header position numbers are not GPIO numbers.

Flex circuit per channel: `own-board 3V3 → flex → ADC node`, with **separate
parallel 47 kΩ and 100 nF** branches from the node to own-board GND.
Button circuit: `3V3 → 10 kΩ → GPIO7`, plus `100 nF` to GND, plus
`1 kΩ → NO button → GND`.

Motion sensor: **Adafruit #5543 LSM6DS3TR-C + LIS3MDL** breakout, external.
I2C addresses **0x6A** (accel/gyro) and **0x1C** (mag). Breakout has its own
pull-ups. Leave `3Vo` and interrupt pins unconnected initially.

Hands share nothing but BLE. Never join supplies across boards.

## 3. Firmware/toolchain baseline — pinned

| Item | Pinned value |
|---|---|
| Framework | **ESP-IDF v5.5.2** |
| Compiler | xtensa-esp-elf-gcc **14.2.0** (crosstool-NG esp-14.2.0_20251107) |
| Simantic CLI/engine | **0.5.20** (0.5.14 and 0.5.7 kept in `tmp/simantic/runtime/engine/` for comparison runs) |
| Simantic Python SDK | **0.3.1** |
| IDF python env | 3.12.14 |
| Config | UART0 @115200, `FREERTOS_UNICORE=y`, no PSRAM, DIO 40 MHz, 4 MB layout |

Arduino-ESP32 / Adafruit libraries are an **optional later adapter** needing
their own version and driver tests. Adafruit nRF52 firmware is not portable by
board-name substitution.

### Toolchain lives in gitignored `tmp/` — treat as fragile

Everything below is real, working, and **not reproducible from a clean
checkout**. ~3.5 GB, unversioned. Do not delete `tmp/simantic/`.

```
IDF_PATH             tmp/simantic/adc-s3-validation/esp-idf-5.5.2
IDF_TOOLS_PATH       tmp/simantic/esp-idf-tools
IDF_PYTHON_ENV_PATH  tmp/simantic/esp-idf-python
Xtensa toolchain     tmp/simantic/audit/esp32s3/toolchain/xtensa-esp-elf/bin
SIMANTIC_HOME        tmp/simantic/runtime
SIMANTIC_ENGINE_DIR  tmp/simantic/runtime/engine/0.5.20
Platform .repl       tmp/simantic/platform/ESP32-S3-WROOM-1-N8R2-0.5.20.repl  (stock, as served 2026-10-05)
Drone platform       tmp/simantic/platform/STM32F405RG-0.5.20.repl + Matek board from
                     tmp/simantic/sim-fixtures (private checkout, not copied into this repo)
ArduCopter ELF       tmp/drone/matekf405-wing-arducopter.elf (simulation/drone/fetch_arducopter.sh)
ESP32-S3 mask ROM    tmp/simantic/esp-idf-tools/esp32s3_rev0_rom.bin
Model candidates     tmp/simantic/upstream-candidates/{systimer-work-en,s3-mwdt}/  built from
                     simulation/simantic/model-candidates/ (committed; see its README)
RISC-V toolchain     tmp/simantic/esp-idf-tools/tools/riscv32-esp-elf  (C3/C6/P4 probe only)
C3/C6 mask ROMs      tmp/simantic/roms  (SHA-256 pinned as in the CLI)
mcu-lib packers      tmp/simantic/packers  (esp32c3/c6/p4_build_image.py)
Image packer         tmp/simantic/audit/source-review/esp32s3_build_image.py
Simantic venv        .venv-simantic/  (has simantic + pytest; use its python)
```

Use `firmware/tools/env.sh` and `firmware/tools/palmpilot.py` rather than
re-deriving these paths.

### Build → simulate pipeline

1. `idf.py build` → `bootloader.bin`, `partition-table.bin`, `<app>.bin`
2. `esptool merge_bin` @ `0x0 / 0x8000 / 0x10000` → flash image
3. `esp32s3_build_image.py --rom <mask rom> --flash <flash.bin> --out sim.elf`
   (packs IROM @0x40000000, DROM @0x3FF00000, flash @0x30000000, entry 0x40000400)
4. `Sim(repl=..., elf=sim.elf, uart='uart0')` on the stock platform, with the
   model candidates in `simulation/simantic/model-candidates/` loaded for every
   run (env.sh): BLE radio (#270), RNG (#271) and STM32 UART TX DMA, none
   released yet. SYSTIMER (#257) and S3 MWDT (#258) shipped in 0.5.15+.
   The whole controller runs as three machines (`palmpilot.py system`), each
   with its own factory MAC in eFuse. Without one, all three chips share one
   Bluetooth address.
   `sim --flash` still refuses ESP32-S3 on CLI 0.5.14, so the ROM wrapper stays.

The physical board and simulator run the **same bootloader/partition/app
binaries**; only the ROM wrapper differs. Keep it that way.

## 4. Simulator capability — verified status

Do not re-litigate these; they are measured, with evidence in
`docs/controller/simantic-plan.md`.

| Capability | Status | Detail |
|---|---|---|
| ESP-IDF v5.5.2 boot, FreeRTOS, UART0 | **WORKS** | full app boots via ROM/flash |
| ADC1 one-shot, public `esp_adc` driver | **WORKS, stock 0.5.14** | calibrated mV within ±5 mV of injection on all five flex channels |
| `esp_timer` (SYSTIMER-backed) | **WORKS** | create/start/stop/delete; periodic callbacks fire |
| **FreeRTOS tick (SYSTIMER)** | **WORKS on stock 0.5.20 (#257 shipped); broken on 0.5.14** | stock `ESP32C3_Systimer` re-arms the periodic tick on every `CONF` write of `TARGET0_WORK_EN=1`; IDF rewrites it unchanged on every esp_timer re-arm, so the hand app's 100 Hz esp_timer froze `xTickCount` at 2 (tick-driven waits and NVS erase block forever). With the candidate: exactly 100 Hz, one tick per ISR. This was the cause of "task delay runs long". Same bug and fix on ESP32-C3 and ESP32-P4 firmware (`firmware/probes/systick`). Still pace periodic work with `esp_timer` |
| GPIO1/2/4/5/6/7 digital input | **WORKS** | register-level injection followed |
| I2C0 via `i2c_master` driver | **WORKS** | LSM6DS3TR-C + LIS3MDL fixtures pass identity, config, status gating and burst reads. GPIO-matrix routing is NOT modeled, so SDA/SCL pin choice is untested |
| Scripted I2C/SPI slaves in Python | **WORKS** | `I2C.ScriptedI2cSlave` with a `file:` in the `.repl` |
| GPTimer / TIMG0 | **WORKS with candidate `ESP32S3_Timg`; BROKEN on stock 0.5.14** | stock wires the C3 register stub: no alarm callbacks, `gptimer_get_raw_count` hangs. Upstream `ESP32S3_Timg` (merged #236, wired by open mcu-lib #222) fires alarms: probe completes with 10 alarms. Prefer `esp_timer` until #222 ships |
| GPIO43 | **BROKEN** | high-bank GPIO unhandled; reserved for UART0 anyway |
| NVS read + `set_blob` | **WORKS** | init, open, get, set and commit all return; 29 consecutive saves pass |
| NVS `erase_key` | **WORKS with candidates** | erase then load reports MISSING; a corrupted blob is rejected with the CRC status; asserted in S1-F. It had hung whenever the tick was dead: the erase yields with `vTaskDelay`. The multi-task phase of `firmware/probes/nvs`, once inconclusive, now completes |
| `esp_restart` | **WORKS** | software reset (reason 3); calibration restores after reboot, asserted in S1-F. The superseded local TIMG overlay hung it. Aborted on 0.5.7 |
| Task watchdog (TWDT) | **WORKS on stock 0.5.20 (#258 + mcu-lib #229 shipped)** | `firmware/probes/mwdt` 14/14 (stage-0 interrupt at 200.015 ms for 200 ms on both groups, feed, write-protect, system reset with reasons 7/8); S1-H trips. Stock 0.5.14 never fires: `ESP32S3_Timg` leaves MWDT store-only and the platform still wires the C3 stub. Not a firmware gap |
| Interrupt watchdog (IWDT) | **WORKS on stock 0.5.20; ENABLED in the hand build** | production settings (`CONFIG_ESP_INT_WDT=y`, 300 ms). The old "expires on healthy firmware" finding was the dead tick: the IWDT is fed from the tick hook. `run_all.sh` fails any suite whose UART shows a panic; with the stock SYSTIMER 7 of 8 hand suites panic, with the candidate none do. `firmware/probes/iwdt`: panics 286 ms after interrupts are disabled |
| Reset-reason hint after a panic | **BROKEN — model gap** | IDF stores it in S3 `RTC_CNTL_STORE6` (+0xC8); the platform's C3 RTC_CNTL model has STORE4-7 at 0xB8-0xC4, so a panic reboot reports `ESP_RST_SW`, not `INT_WDT`. Addressed by draft renode-infrastructure #245 (S3 RTC_CNTL) |
| ESP32-S3 BLE, hub holding both hands | **WORKS with candidate BLE radio (#270); stock 0.5.20 cannot hold the second link** | NimBLE peripheral per hand, central on the hub; 50 Hz packets from both hands, zero rejected (S2-A, S2-B). The stock radio model holds one link per radio: a second link never establishes and packets cross between links (model-candidates README). Lossless medium: no RF, range or coexistence claim |
| Hardware RNG across a reset | **WORKS with candidate RNG (#271); stock 0.5.20 still replays** | stock model replays the same values after every chip reset, so a rebooted hand reused its session |
| Pin inputs across an MCU reset | **bench re-applies them** | Renode resets injected ADC voltages and GPIO levels with the chip (simantic-core#561); `harness.ExternalInputs` re-drives them, as real sensors would |
| Drone: stock ArduCopter 4.7.1, STM32F405 (Matek F405-Wing model) | **WORKS with candidate STM32 UART (renode-infrastructure #325)** | boots to standby in ~9 s virtual; RC arrives as MAVLink RC_CHANNELS_OVERRIDE on SERIAL1 and ArduCopter reports it back exactly (S3-A). Stock 0.5.20's STM32_UART never runs TX DMA, so no telemetry leaves. Disarmed, no vehicle physics yet |
| ADC2, DMA/continuous, ADC interrupts | **OUT OF SCOPE** | not modeled |

The ADC fix is **PR #168**, merged into `simantic-main` on 2026-09-26 and
shipped in engine 0.5.14. The stock platform wires `CalibrationEfuse: efuse`,
so the model returns the raw count a die with the modeled eFuse would report,
and ESP-IDF's curve-fitting calibration turns it back into millivolts. Raw
counts are therefore **die-specific, as on silicon** — never assert them
against the ideal TRM line. Tests assert calibrated mV (`ADC_MV_TOLERANCE`,
±5 mV, model contract) and compare captures with live acquisition. The model
is synchronous and noise-free; it validates neither silicon accuracy nor the
bench board's own eFuse.

### SDK API surface (`simantic.Sim`, 0.3.1)

`close, expect, frames, heap, inject_can, inject_gpio, inject_radio, interrupts,
logs, read_memory, read_u32, read_uart, run_for, send, send_bytes, symbol,
symbol_trace, threads, time, uart_records`

- `Sim(elf=, repl=, mcu=, overlay=, scenario=, machine=, uart='uart0', ...)`
- `inject_gpio(peripheral: str, pin: int, state: bool)`
- ADC voltage injection is **not** in the SDK — use Renode interop:
  `IADCExtensions.SetVoltage(machine['sysbus.sens'], UInt32(microvolts), Int32(channel))`
- **`read_uart` duplicates/interleaves fragments** in this engine/SDK pair.
  Capture UART via the Renode `CharReceived` event instead, for any assertion.
- For repeatable multicore runs set `serialExecution: true` in a `--scenario`.

## 5. Command and control contract

Transport-independent record; **serialization, rates and limits are UNSET** and
must be frozen in S3 from measured behavior.

Fields: protocol version + length, device identity + hand side, boot/session id,
sequence counter, acquisition counter + sample timestamp, five flex values,
motion data + health, calibration state, power mode/health, left ENABLE,
validity, fault reason.

Conventions: **roll/pitch/yaw ∈ [-1, 1]**, **throttle ∈ [0, 1]**.
Normalized throttle is not measured rotor thrust.

Rules that are already decided:

- The hub invalidates the **whole command** if either hand is unhealthy or stale.
- Freshness uses a **monotonic hub-local receipt time**. Never subtract an
  unsynchronized hand timestamp from the hub clock.
- Track **acquisition progress**, not just packet arrival — sampling frozen
  behind a live comms task must be detectable.
- Host expiry is **receiver-local** and must work even if a frozen hub never
  sends a final invalid message. A live byte stream with frozen input is invalid.
- ENABLE is a **gesture-permission request**, not arm/start. It never
  autonomously arms, starts or resumes. Recovery requires release + deliberate
  new press + explicit host restart.
- A held button is never recovery consent. Reset cannot resurrect prior permission.
- Service the watchdog **only after** acquisition, validation, mapping and
  bounded output have progressed. A timer-only feed is not application health.
- Never clamp a fault into a valid gesture. Near-rail flex reads are **faults**.

UNSET numeric limits (freeze from measurement, do not copy from the nRF design):
acquisition/notification rate, `T_hand` max age, left/right skew, watchdog
period, fault-to-invalid latency, debounce (20 ms is a candidate to measure),
settling interval (50 ms provisional), filter/deadband/slew values.

## 6. Hard prohibitions

- **No nRF/Feather carry-over.** Not `raw × 3.6 / 4096`, not
  `analogReference(AR_INTERNAL)`, not `analogSampleTime()`, not A0–A4/D5/D6/A6
  labels, not the factory battery divider, not the Feather EN switch semantics.
  Rev A drawings are the nRF circuit record only.
- **Never connect** 5 V or a LiPo to any ADC pin. GPIO10 stays disconnected
  until a reviewed external monitor exists. RST/EN is not a battery disconnect.
- **No invented battery data.** Bench firmware reports
  *"USB bench power; battery unavailable"*. Never synthesize a voltage from a
  floating GPIO10.
- **No floating point anywhere on the control path.** Fixed-point milli-units
  (0–1000). See the [FPU record](firmware/probes/fpu/README.md).
- **Do not pace a periodic task with `vTaskDelay`** — use `esp_timer`.
- **Never write flash from the live control path.** A real ESP-IDF flash write
  suspends the scheduler. `cal save` / `cal erase` are refused while the hand is
  in `permitted`.
- Do not treat a catalog entry, an address scan, a successful API return or a
  boot as a peripheral pass.

## 7. Evidence discipline — this repo's core rule

Every result is **PASS**, **FAIL**, **BLOCKED**, **MOCKED-INPUT-ONLY** or
**NOT APPLICABLE (optional extension)**. Keep those distinct.

- A simulation PASS **never** marks a physical check passed, and vice versa.
- Injected application values that bypass a driver are **MOCKED-INPUT-ONLY**,
  not driver coverage. Stimulus must traverse the modeled driver.
- Set numeric acceptance limits **before** running a test.
- A documentation edit, a wiring review or a written instruction is not a test.
- Record model/engine/SDK versions, source hashes, ELF hashes, fixtures,
  stimulus traces, coordinate frames, time step and seed.
- Check milestones only after their tests pass. Keep tests with firmware and
  summarize results in pull requests and the current controller plan.
- Do not recreate dated implementation records, historical design folders or
  debug-dump collections in the published project. The user removed them.

Prose style in this repo is deliberately hedged and precise. Match it: state
what was observed, its scope, and what it does **not** establish. Do not
upgrade a partial result into a claim.

## 8. Repository layout

The repository was trimmed on 2026-09-18 to the active controller project.
Historical nRF52840/Feather material, the Rev A schematic package, the h7-ble
and archive design sets, the capability audits and the schematic tooling were
all removed. Do not resurrect them; they are recoverable from git history at
`4a4c9a2` if a specific fact is ever needed.

```
README.md                    scope, build order, checkpoints S0-S3 / C0-C7 / D1-D4
CLAUDE.md                    this file
docs/architecture.md         boundaries, responsibilities, contracts
docs/controller/             ACTIVE controller spec
  README.md                  stage table, read order
  bom.md                     active parts list
  build-guide.md             exact bench pins and circuits
  firmware-plan.md           FW-01..FW-06 work packages
  gesture-mapping.md         PROPOSED v1 gesture table and interlocks
  simantic-plan.md           S0-S3 gates
  validation.md              CTRL-001..055 acceptance
docs/drone-simulation.md     D1-D4, Goal 2
firmware/                    ACTIVE firmware workspace
  tools/                     env.sh, palmpilot.py, harness.py (one board),
                             controller.py (both hands + hub), selftest.py
  components/palmpilot_core/ pure logic shared by hand and hub: hand_core,
                             packet, hub_core (mixing + interlocks), link.h
  components/console/        whole-line UART output from any task
  apps/hand/                 hand firmware; `hand:left` / `hand:right` builds
  apps/hub/                  hub firmware: BLE central, one command on UART0
  tests/                     simulation suites; run_all.sh runs every one
                             (s1* one hand, s2* whole controller)
  probes/fpu/                FPU-gap probe and its finding
  probes/reset/              esp_restart gap
  probes/nvs/                NVS erase gap
  probes/gptimer/            timer-group fix and its before/after
  probes/mwdt/               MWDT (task/interrupt watchdog hardware) probe
  probes/iwdt/               interrupt watchdog with production settings
  probes/systick/            FreeRTOS tick under esp_timer load; multichip.py
                             runs it on S3/C3/P4, stock vs candidate SYSTIMER
simulation/simantic/
  README.md                  simulation scope
  hardware-validation/esp32s3-adc/   ADC reference app, runs on silicon and sim
  model-candidates/          simulator models awaiting a Simantic release
outputs/palmpilot-fall-2026/ schedule
tmp/                         gitignored toolchain + build output - DO NOT DELETE
```

Committed evidence is limited to what cannot be regenerated. Physical bench
captures under `hardware-validation/*/evidence/physical-*` are committed;
simulator dumps are gitignored because re-running the harness reproduces them.

## 9. Git state

Remote: `github.com/Samiurr10/gesture-controlled-drone`, branch `main`.

A second agent (Codex) was previously committing to this repository in
parallel, which caused a collision on 2026-09-18. It is no longer active and
this session owns the repository. If concurrent edits reappear, stop and check
`git log` before committing.

## 10. Firmware status

`firmware/apps/hand` (built LEFT or RIGHT) implements acquisition,
calibration, the motion module, tilt mapping, the control state machine,
persistence and the BLE link to the hub. `firmware/apps/hub` links both hands,
validates them and applies the gesture mapping, HOLD, PRECISION, slew and the
latching interlocks (`hub_core`), then sends one command per 20 ms on UART0.
`sh firmware/tests/run_all.sh` runs every suite: **266 checks across 11 suites
pass** as of 2026-09-29 (engine 0.5.14, stock S3 platform, all model
candidates, production watchdogs), including the whole controller as three
machines (S2-A link, S2-B mixing, faults, latch, reboot recovery, hub
CALIBRATE). There was no firmware panic on any board.
On engine 0.5.20 (2026-10-05) with the BLE and RNG candidates, every check passes
except one: S2-B reset-to-invalid measured 160 ms against a provisional 150 ms
limit. S1-B passed 22/22 but failed its second run once. S3-A (hands + hub
drive ArduCopter) passed 18/18 in its own run. With the released models,
S2-A fails and S2-B stalls.

The hand→hub packet payload is frozen in `firmware/components/palmpilot_core/packet.h`
(59 bytes, little-endian, versioned, CRC-32) and decoded independently in
`firmware/tests/s1g_packet.py`.

No S or C milestone is claimed. Still open: BLE pairing/bonding, the host
bridge that consumes the hub's commands, and anything physical. The watchdog is implemented with FW-06's service
discipline and its timeout is now exercised; only the panic and reset after a
trip remain physical-only. Persistence is implemented
but **not qualified**. Reboot restore, erase and on-device CRC rejection now
pass in simulation (S1-F); physical proof remains owed at C2/CTRL-022.

## 11. Next firmware milestone

**S0 for ESP32-S3**, then S1 one-hand acquisition. Per the 2026-09-17 readiness
record, enough is qualified to start one-hand firmware on: ESP-IDF v5.5.2, the
upstream ADC1 model, `esp_timer`/FreeRTOS, GPIO7, and UART diagnostics.

Still owed by the project before S1 closes: five-channel acquisition with
timestamps/filtering/validity, public GPIO driver + debounce + held-at-boot,
**LSM6DS3TR-C/LIS3MDL register fixtures** (project-owned — the BME280 fixture is
not IMU coverage), calibration + NVS persistence, and watchdog recovery.
