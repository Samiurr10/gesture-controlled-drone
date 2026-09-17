# PalmPilot / Gesture-Controlled Drone Simulation

**We will physically build the hand gesture controller. The drone will be simulated and move on a computer screen.** We are not building a physical drone.

Scope updated **September 16, 2026**. This plan supersedes the earlier physical-aircraft build and flight plans, including the aircraft portions of the original BOM and Rev A schematics.

**Controller decision:** use **ESP32-S3** for both hands and the controller hub. The bench target is **ESP32-S3-DevKitC-1 with ESP32-S3-WROOM-1-N8R2**, external motion sensors and USB power. ESP32-S3 is the sole controller platform. The old Rev A hand pins, onboard sensors and battery circuits are superseded; use the [ESP32 migration record](docs/controller/esp32-migration.md) and current [BOM](docs/controller/bom.md).

## Goals and priority

1. **Make the controller work.** First simulate the hand controller in **Simantic**, starting with one flex input and expanding to the complete controller. Then build and test the physical hand-controller prototype.
2. **Make the drone simulation.** Simulate the drone's hardware and microcontroller in **Simantic**. Use the simulated microcontroller's motor/actuator output signals to drive a mechanical/dynamics simulation, and display the resulting drone motion on screen. Connect the working physical controller to this simulation.

The first priority is controller simulation, followed by its physical prototype. Drone simulation implementation follows controller qualification. Moving a graphic directly from hand gestures does not complete the second goal: displayed motion must come from the drone's simulated control and mechanical response.

**Current status — September 17:** enough is available to start one-hand firmware using the local ADC fix, `esp_timer`/FreeRTOS, GPIO7 and UART. The corrected ADC probe and full ESP-IDF ADC application pass; a public-driver test confirms the TIMG model gap. Exact IMU fixtures/drivers, calibration persistence, watchdog recovery and ESP BLE remain to be qualified. Production controller firmware and integrated drone simulation are not implemented. See the [latest readiness and test record](docs/implementation-records/2026-09-17_hand-controller-readiness.md). The physical ADC bench board is a **Freenove ESP32-S3 WROOM N8R8**, with PSRAM disabled in validation firmware; the N8R2 remains the simulation reference.

## Start here

1. Review the [ESP32 decision](docs/controller/esp32-migration.md) and [latest readiness record](docs/implementation-records/2026-09-17_hand-controller-readiness.md), then continue **S0** in the [controller Simantic plan](docs/controller/simantic-plan.md).
2. Qualify the exact ESP32 model, ADC and sensor-driver path, then simulate one flex channel before adding sensors and the second hand.
3. Complete S0–S3 with recorded simulation evidence. Then use the [controller build guide](docs/controller/build-guide.md) and [incremental parts list](docs/controller/bom.md) for C0–C7.
4. After the controller works, follow the [drone simulation plan](docs/drone-simulation.md) for D1–D4.

## System we are building

```text
Phase 1: Simantic hand-controller models + controller firmware
         simulated sensors -> hand nodes -> hub -> validated commands
                                      |
Phase 2: Physical hand-controller prototype replaces simulated controller
         flex/external IMUs -> two ESP32-S3 hands -> BLE -> ESP32-S3 hub
                                      |
                            computer command bridge
                                      |
Phase 3: Simantic drone hardware + microcontroller/flight-control firmware
                                      |
                            motor/actuator output signals
                                      v
                         mechanical / dynamics simulation
                             |                   |
                    simulated sensor feedback   position + orientation
                             |                   v
                      back to drone MCU     on-screen drone display
```

| Part | Current scope |
|---|---|
| Hand controller | Two ESP32-S3-DevKitC-1 N8R2 bench targets, five flex inputs and an external motion-sensor breakout per hand; simulate, then prototype |
| Controller hub | ESP32-S3, planned two-peer BLE input validation and command output to the computer; stack compatibility remains to be tested |
| Computer connection | USB-to-UART bridge for bench diagnostics; freeze the production host transport after driver tests |
| Drone electronics | STM32H743 / KakuteH7 ArduCopter candidate in Simantic; full board behavior remains under qualification |
| Drone motion | Dynamics model driven by simulated MCU actuator outputs, with sensor feedback and an on-screen view |
| Pocket, trainer buffer and ELRS | Optional historical interface work; not required purchases or completion gates |
| Airframe, physical FC/ESC, motors, propellers, aircraft battery and flight tests | Outside the current project scope |

The [architecture](docs/architecture.md) defines responsibilities and interfaces. Begin with one ESP32 hand and one sensor. USB bench wiring is defined in the controller guides; a complete ESP32 wearable schematic and battery design remain implementation checkpoints.

## Documentation

| Need | Document |
|---|---|
| Current scope, system boundaries and open decisions | [Architecture](docs/architecture.md) |
| Latest ADC/timer results and remaining controller work | [September 17 readiness](docs/implementation-records/2026-09-17_hand-controller-readiness.md) |
| ESP32 decision, simulation and model gaps | [ESP32 migration](docs/controller/esp32-migration.md), [Simantic plan](docs/controller/simantic-plan.md), [current assessment](docs/implementation-records/2026-09-16_esp32-full-drone-feasibility.md) |
| Executed simulator tests and concrete platform requests | [ESP32-S3 and STM32H7 audit](simulation/simantic/capability-audit/README.md), [Simantic handoff](simulation/simantic/capability-audit/SIMANTIC-REQUESTS.md) |
| Controller stages and physical construction | [Controller overview](docs/controller/README.md), [BOM](docs/controller/bom.md), [build guide](docs/controller/build-guide.md) |
| Controller software and acceptance | [Firmware plan](docs/controller/firmware-plan.md), [validation](docs/controller/validation.md) |
| Drone MCU outputs, dynamics and display | [Drone simulation plan](docs/drone-simulation.md) |
| Record simulation and physical results separately | [Test template](docs/controller/test-record-template.md), [implementation records](docs/implementation-records/README.md) |
| Revised schedule and course milestones | [Schedule status and workbook](outputs/palmpilot-fall-2026/README.md) |
| Circuit reference and historical drawings | [Schematic index and scope labels](hardware/schematics/README.md) |
| Simulation inventory and scope classification | [Simantic inventory guide](simulation/simantic/README.md) |
| Original source material and older designs | [BOM provenance](docs/reference/README.md), [design archive](docs/archive/README.md) |

Historical PDFs, circuit schedules and research preserve earlier design decisions. Aircraft parts in those records are not a shopping list or a later physical build phase. Controller instructions and the scope above take precedence.

## Full implementation checkpoints

Only check an implementation milestone when its exit criteria pass and link to a record in [implementation records](docs/implementation-records/README.md). Label evidence as simulation, physical prototype or integrated demonstration. Planned dates and written instructions are not completed tests.

### Goal 1A — Simulate the controller first

- [ ] **S0 — ESP32 simulator baseline:** pin ESP32-S3 toolchain/model versions; boot the chosen framework; verify first-hand ADC, motion-sensor, GPIO and timer support. Record blocked/substituted features and the BLE/host-transport checks to complete in S2/S3.
- [ ] **S1 — One-hand sensing and calibration:** start with one flex channel, expand to five plus motion and enable; report explicit USB bench-power status and test calibration/sensor faults. Battery monitoring follows its new circuit design.
- [ ] **S2 — Both hands and hub:** verify identities, two BLE links, acquisition progress, freshness and whole-command invalidation on faults.
- [ ] **S3 — Controller simulation qualification:** validate bounded commands, enable/stop/recovery behavior and the host-output contract with repeatable normal and fault scenarios. Record unsupported coverage; mocked inputs alone do not qualify missing hardware paths.

### Goal 1B — Build the physical controller prototype

Begin after the controller simulation exit criteria are met. Resolve missing required simulation coverage before marking Goal 1A complete; any change to that gate must be recorded explicitly.

- [ ] **C0 — ESP32 bench preparation:** confirm DevKitC-1 N8R2 board revisions, external sensors, parts, toolchain, inspection and USB diagnostics; publish/review the ESP32 schematic revision before wearable assembly.
- [ ] **C1 — One physical flex input:** assemble left ESP32 GPIO1 / ADC1_CH0 with 47 kΩ and 100 nF, validate ADC attenuation/calibration, measure readings and test open/short behavior.
- [ ] **C2 — Complete left-hand sensing:** verify five flex channels, motion axes, calibration and filtering.
- [ ] **C3 — Left wearable:** qualify the new charger/regulator/battery-monitor design, enable, power switch, fit and strain relief; measure the valid operating range. The DevKit requires an external battery charger and power circuit.
- [ ] **C4 — Right wearable:** repeat sensing, power, fit and independent calibration with a distinct hand identity.
- [ ] **C5 — Hub and BLE:** validate both physical links, calibration control, mapping and stale-data handling.
- [ ] **C6 — Controller-to-computer bridge:** validate serialized commands, session/sequence/freshness, bounds, disconnection and deliberate recovery on the host.
- [ ] **C7 — Controller qualification:** pass required physical controller tests; archive firmware, calibration, measured latency/runtime and a repeatable command-monitor demonstration. No drone or radio hardware is required.

### Goal 2 — Drone simulation and on-screen demonstration

- [ ] **D1 — Drone hardware/MCU feasibility:** select and validate a Simantic target and firmware, virtual sensors, command input and observable actuator outputs; document fidelity limits.
- [ ] **D2 — Output-driven mechanics:** decode MCU motor signals, compute forces/torques, integrate drone motion and return simulated sensor data to the MCU.
- [ ] **D3 — Display and controller integration:** render the dynamics state and connect the qualified physical controller through the command bridge; provide explicit start, stop and reset controls.
- [ ] **D4 — End-to-end qualification:** demonstrate individual axes and combined motion, loss/fault behavior and reproducible runs; save synchronized command, actuator and motion traces.

No milestone requires aircraft assembly, physical motor tests or real flight. The old A0–A5 aircraft checkpoints are retired. [Aircraft integration](docs/aircraft-integration.md) now directs older links to the virtual-drone plan.

## Repository maintenance

Active controller instructions live in `docs/controller/`; drone simulation requirements live in `docs/drone-simulation.md`. Preserve schematic circuit revisions when changing wiring, and identify affected tests. Keep original source evidence distinguishable from the current implementation plan.

Run the documentation and schematic consistency check from the repository root:

```sh
python3 tools/verify_schematic_package.py --paths README.md docs hardware/schematics simulation outputs
```

This checks local link targets and historical schematic structure; it does not validate electronics, firmware or simulation behavior. See the [Rev A regeneration instructions](hardware/schematics/rev-a/README.md#regenerate-for-review) when updating historical schematic exports.
