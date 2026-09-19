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
| Simantic CLI/engine | **0.5.7** |
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
Platform .repl       tmp/simantic/audit/esp32s3/ESP32-S3-WROOM-1-N8R2.repl
ESP32-S3 mask ROM    tmp/simantic/esp-idf-tools/esp32s3_rev0_rom.bin
ADC overlay DLL      tmp/simantic/adc-s3-validation/repro/model/bin/Debug/net10.0/S3AdcUnderTest.dll
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
4. `Sim(repl=..., elf=sim.elf, uart='uart0')`, with the ADC overlay loaded and
   `Miscellaneous.ESP32S3_Sens` rewritten to `AdcUnderTest.ESP32S3_Sens` in the
   `.repl`.

The physical board and simulator run the **same bootloader/partition/app
binaries**; only the ROM wrapper differs. Keep it that way.

## 4. Simulator capability — verified status

Do not re-litigate these; they are measured, with evidence in
`docs/controller/simantic-plan.md`.

| Capability | Status | Detail |
|---|---|---|
| ESP-IDF v5.5.2 boot, FreeRTOS, UART0 | **WORKS** | full app boots via ROM/flash |
| ADC1 one-shot, public `esp_adc` driver | **WORKS with overlay** | 960 reads / 10 ch / 4 atten pass |
| `esp_timer` (SYSTIMER-backed) | **WORKS** | create/start/stop/delete; periodic callbacks fire |
| FreeRTOS task delay | **WORKS, runs long** | returns, but a requested delay takes materially longer. Pace periodic work with `esp_timer`, not `vTaskDelay` |
| GPIO1/2/4/5/6/7 digital input | **WORKS** | register-level injection followed |
| I2C0 via `i2c_master` driver | **WORKS** | LSM6DS3TR-C + LIS3MDL fixtures pass identity, config, status gating and burst reads. GPIO-matrix routing is NOT modeled, so SDA/SCL pin choice is untested |
| Scripted I2C/SPI slaves in Python | **WORKS** | `I2C.ScriptedI2cSlave` with a `file:` in the `.repl` |
| **GPTimer / TIMG0** | **BROKEN — model gap** | setup returns `ESP_OK`, no alarm callbacks; `gptimer_get_raw_count` hangs at `timer_ll_trigger_soft_capture` (`timer_ll.h:194`). Model `Timers.ESP32C3_Timg` stores registers only. **Use `esp_timer`, not GPTimer.** |
| GPIO43 | **BROKEN** | high-bank GPIO unhandled; reserved for UART0 anyway |
| NVS read + `set_blob` | **WORKS** | init, open, get, set and commit all return; 29 consecutive saves pass |
| **NVS `erase_key`** | **BROKEN — hangs** | never returns in a multi-task app; no error, no panic, silent for 60+ simulated seconds. Probe: `firmware/probes/nvs` |
| **`esp_restart`** | **BROKEN — engine aborts** | same "Collection was modified" error as the FPU gap. Blocks reboot persistence and all watchdog-recovery testing. Probe: `firmware/probes/reset` |
| Watchdog recovery | **UNTESTABLE HERE** | a watchdog reset is a reset; detection could be tested, recovery cannot |
| ESP32 BLE, two concurrent links | **UNQUALIFIED** | Nordic BLE passes do **not** transfer |
| ADC2, DMA/continuous, ADC interrupts | **OUT OF SCOPE** | not modeled |

The ADC model is **ideal and synchronous**: `raw = min(4095, uV × 4095 × (4−atten) ÷ 4400000)`.
It validates the model contract, not silicon accuracy, noise, latency or
factory calibration. Physical endpoint differs: nominal 3V3 gives 4095 on
silicon but 3071 in the ideal model.

The ADC fix is **PR #168** (`simantic-dev/renode-infrastructure`), **open and
unmerged**, loaded as a namespace-only overlay. Stock engine 0.5.7 fails ADC.

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
- **No GPTimer** in controller firmware while the TIMG model gap stands.
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
  tools/                     env.sh, palmpilot.py, harness.py, selftest.py
  apps/hand/                 hand-node firmware
  tests/                     simulation suites; run_all.sh runs every one
  probes/fpu/                FPU-gap probe and its finding
  probes/reset/              esp_restart gap
  probes/nvs/                NVS erase gap
simulation/simantic/
  README.md                  simulation scope
  hardware-validation/esp32s3-adc/   ADC reference app, runs on silicon and sim
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

`firmware/apps/hand` implements S1 acquisition, calibration, the external
motion module, gravity-referenced attitude mapping, the control state machine
and calibration persistence. `sh firmware/tests/run_all.sh` runs every suite;
**143 checks across 7 suites pass** as of 2026-09-18.

The hand→hub packet payload is frozen in `firmware/apps/hand/main/packet.h`
(59 bytes, little-endian, versioned, CRC-32) and decoded independently in
`firmware/tests/s1g_packet.py`.

No S or C milestone is claimed. Still open: the watchdog, the BLE stack and
transport binding, and the right-hand/hub targets. Persistence is implemented
but **not qualified** — reboot restore, erase and on-device CRC rejection are
all blocked by model gaps and are physical-only at C2/CTRL-022.

## 11. Next firmware milestone

**S0 for ESP32-S3**, then S1 one-hand acquisition. Per the 2026-09-17 readiness
record, enough is qualified to start one-hand firmware on: ESP-IDF v5.5.2, the
PR #168 ADC overlay, `esp_timer`/FreeRTOS, GPIO7, and UART diagnostics.

Still owed by the project before S1 closes: five-channel acquisition with
timestamps/filtering/validity, public GPIO driver + debounce + held-at-boot,
**LSM6DS3TR-C/LIS3MDL register fixtures** (project-owned — the BME280 fixture is
not IMU coverage), calibration + NVS persistence, and watchdog recovery.
