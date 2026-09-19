# PalmPilot / Gesture-Controlled Drone

Build an **ESP32-S3 hand controller** that controls an **STM32H7 drone simulation** on a computer screen.

## Build order

1. Simulate one hand in Simantic: one flex input, then five flex inputs, motion sensing and ENABLE.
2. Add the second ESP32-S3 hand and an ESP32-S3 BLE hub; validate the host command interface.
3. Build and qualify the physical hand-controller prototype.
4. Run drone firmware on a simulated STM32H7, drive dynamics from its motor outputs, and display the resulting motion.

The physical project is the controller. The drone remains virtual.

## Hardware and current status

- **Physical bench:** Freenove ESP32-S3 WROOM N8R8. **Simulation reference:** ESP32-S3-WROOM-1-N8R2. Current validation disables PSRAM.
- **Each hand:** five flex sensors and an external Adafruit #5543 LSM6DS3TR-C + LIS3MDL module. Left hand has ENABLE; the hub has CALIBRATE.
- **Power:** USB for bench work. Wearable power and the complete ESP32-S3 wearable schematic remain to be designed.
- **Simulation:** ADC support is in [Simantic PR #168](https://github.com/simantic-dev/renode-infrastructure/pull/168), ready for review. Its calibrated mode passes 51 unit tests and 2,480 firmware reads; it is not included in stock engine 0.5.7.
- **Next:** complete one-hand acquisition and exact motion-sensor driver tests. NVS persistence, watchdog recovery and two-hand BLE still need qualification. See the [controller simulation plan](docs/controller/simantic-plan.md).

## Project documents

| Need | Document |
|---|---|
| System boundaries and command flow | [Architecture](docs/architecture.md) |
| Controller build sequence | [Controller overview](docs/controller/README.md) |
| Parts to order | [Controller BOM](docs/controller/bom.md) |
| Pins and circuit connections | [Build guide](docs/controller/build-guide.md) |
| Firmware implementation | [Firmware plan](docs/controller/firmware-plan.md) |
| How gestures map to drone commands | [Gesture mapping](docs/controller/gesture-mapping.md) |
| Controller firmware source and tests | [Firmware workspace](firmware/README.md) |
| Simantic setup and remaining work | [Controller simulation plan](docs/controller/simantic-plan.md) |
| Controller acceptance tests | [Validation checklist](docs/controller/validation.md) |
| STM32H7, dynamics and display | [Drone simulation plan](docs/drone-simulation.md) |
| Timeline and course milestones | [Gantt schedule](outputs/palmpilot-fall-2026/README.md) |

## Full implementation checkpoints

Check milestones when their exit criteria pass. Keep automated tests with the firmware and record concise results in the relevant pull request. Simulation and physical-controller checks are separate.

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
