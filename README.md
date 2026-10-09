# PalmPilot — gesture-controlled drone

Two wearable hand controllers, each an ESP32-S3 with five flex sensors and a
motion sensor, send their readings over BLE to an ESP32-S3 hub. The hub turns them
into roll, pitch, yaw and throttle and sends one command every 20 ms over USB to a
laptop. On the laptop, stock ArduCopter runs on a simulated STM32F405 flight
controller, and its motor outputs drive a physics model of a quad that is shown on
screen.

**We build the controller. The drone is only simulated.** No airframe, motors or
flight test are in scope. The screen shows only what the simulated flight
controller's motors did; nothing moves the drone straight from a gesture.

## The plan

1. **Simulate everything first.** Both hands, the hub and the drone run in Simantic
   with the real firmware. The physics is checked twice: first against closed-form
   results, then against ArduPilot's own SITL physics.
   → [Simulation plan](docs/simulation.md)
2. **Wire and test the physical controller, one board at a time.** Start with one
   flex sensor, then one hand, the second hand, and the hub. Each physical step
   repeats the simulation tests for that part. → [Wiring](docs/wiring/README.md)
3. **Physical controller, simulated drone.** Plug the physical hub into the laptop
   in place of the simulated hands and hub, and fly the simulated drone from a 3D
   view. → [Demo plan](docs/demo.md)

The step-by-step order with commands and pass criteria: [Test plan](docs/test-plan.md).

## Status, 2026-10-08

| Part | State |
|---|---|
| Hand and hub firmware | Implemented: acquisition, calibration, motion, mapping, interlocks, BLE, persistence, watchdog |
| Simulation, one hand and both hands (S1, S2) | Pass on engine 0.6.3 with the BLE and RNG model candidates. S2-B reset-to-invalid is 120 or 160 ms against a provisional 150 ms limit |
| Simulation, controller into ArduCopter (S3) | S3-A and S3-B pass |
| Closed-loop gesture flight (D2) | Flies in AltHold with both simulated hands. Agrees with ArduPilot SITL to within about 0.4° and 0.05 m/s. Open: a 1–2.5° attitude-estimate drift after manoeuvres |
| Simulator stall with four machines | Root-caused. Fix open upstream (renode-infrastructure #340) |
| Physical controller | Wiring drawn, nothing built or tested |
| Laptop demo | Planned. The runner and the 3D view are not built |

No milestone is claimed complete. Simulation results are evidence about the
firmware against Simantic's models, not about hardware.

## Documents

| Document | Contents |
|---|---|
| [docs/simulation.md](docs/simulation.md) | What is simulated, the models, the physics and its verification, known limits |
| [docs/wiring/](docs/wiring/README.md) | Pins, circuits, the build order and pinplanner drawings for LEFT, RIGHT and HUB |
| [docs/test-plan.md](docs/test-plan.md) | Every test in order: simulation (A), physical bench (B), physical controller with simulated drone (C) |
| [docs/bench/](docs/bench/README.md) | Bench procedures for part B: one per simulation suite, each with its wiring drawing, the firmware to flash and the console steps (not tested on hardware) |
| [docs/demo.md](docs/demo.md) | Laptop demo: data path, 3D view, operator procedure, what is missing |
| [docs/gesture-mapping.md](docs/gesture-mapping.md) | Which gesture is which command, and the safety interlocks |
| [docs/bom.md](docs/bom.md) | Parts for the controller |
| [firmware/README.md](firmware/README.md) | Building, simulating, the test suites and the firmware's UART commands |
| [CLAUDE.md](CLAUDE.md) | Frozen constraints: pin map, toolchain, command contract, evidence rules |

## Layout

```text
firmware/apps/hand, hub, replay   hand and hub firmware; replay is a scripted stand-in hand
firmware/components/              shared logic (hand_core, hub_core, packet) and UART console
firmware/tests/                   simulation suites S1-S3; run_all.sh runs them all
firmware/tools/                   env.sh (pinned paths), palmpilot.py (build/sim), controller.py
firmware/probes/                  engine-defect reproducers and drone flight scripts
simulation/drone/                 bridge, physics, sensor models, SITL cross-check
simulation/simantic/              model candidates awaiting release; ADC reference app with physical captures
docs/                             the documents above
tmp/                              gitignored toolchain and build output, not reproducible
```
