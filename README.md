# PalmPilot — gesture-controlled drone

Two wearable hand controllers, each an ESP32-S3 with five flex sensors and a
motion sensor, send their readings over BLE to an ESP32-S3 hub. The hub turns them
into roll, pitch, yaw and throttle and sends one command every 20 ms over USB to a
laptop. On the laptop, ArduCopter 4.7.1 runs in real time as ArduPilot's native
simulator (SITL), and its motor outputs drive ArduPilot's physics model of a quad that is
shown on screen. The simulation test suites run the same ArduCopter release on an
emulated Matek F405-Wing (STM32F405) flight controller instead.

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

## Status, 2026-11-17

| Part | State |
|---|---|
| Hand and hub firmware | Implemented: acquisition, calibration, motion, mapping, interlocks, BLE, persistence, watchdog |
| Simulation, one hand and both hands (S1, S2) | Pass on engine 0.6.6 with the RNG model candidate. S2-B reset-to-invalid is 120 or 160 ms against a provisional 150 ms limit |
| Simulation, controller into ArduCopter (S3) | S3-A and S3-B pass |
| Closed-loop gesture flight (D2) | Flies in AltHold with both simulated hands on the F405 (default) and on the Pixhawk 6X (H7, selectable). On the F405, agrees with ArduPilot SITL to within about 0.4° and 0.05 m/s. Open: a 1–3° attitude-estimate drift after manoeuvres |
| Physical controller | Built on breadboards: LEFT, RIGHT and HUB on ESP32-S3 DevKits, flashed with the same images that pass in simulation. Both hands link to the hub at 50 packets/s; the physical hub has flown the simulated drone. No physical test-plan step is claimed passed. Open: a hand that stops sending while still linked. Record: [docs/bench-bringup.md](docs/bench-bringup.md) |
| Laptop demo | `simulation/drone/demo_view.py`: ArduCopter SITL in real time (or the emulated F405 with `--drone f405`) in a 3D view, flown by the physical hub (`--hub PORT`), the keyboard (`--manual`) or a scripted virtual pilot. Both hands' telemetry in the side panel |
| Simulator gaps | Four-machine stall (renode-infrastructure #340) and H7 F-RAM framing (simantic-core #659): fixed upstream, not in the pinned engine 0.6.6. This repo stops stalled runs with a watchdog and works around the F-RAM framing |

No milestone is claimed complete. Simulation results are evidence about the
firmware against Simantic's models, not about hardware.

## Getting started

What a fresh clone can and cannot do today:

| Want to | Needs | Reproducible from this repo? |
|---|---|---|
| Read the design, wiring and test plan | nothing | yes |
| Build the hand and hub firmware | ESP-IDF v5.5.2 with its Xtensa GCC 14.2.0 | expected with a standard ESP-IDF v5.5.2 install (`idf.py -C firmware/apps/hand -D SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.left" build`); only tried with this repo's pinned toolchain |
| Flash and run the physical controller | the above, three ESP32-S3 DevKits, the parts in [docs/bom.md](docs/bom.md), wiring per [docs/wiring/](docs/wiring/README.md) | yes |
| Fly the SITL demo drone | an ArduPilot SITL build of Copter-4.7.1 and pymavlink | expected with a standard ArduPilot checkout; the scripts look for it under `tmp/ardupilot` (`simulation/drone/sitl_live.py`, `demo_view.py`) |
| Run the Simantic simulation suites | the Simantic engine 0.6.6 and Python SDK 0.4.0, the ESP32-S3 mask ROM and image packer, the platform files | **not yet**: these live in a local, gitignored `tmp/` that `firmware/tools/env.sh` points to |
| Run the drone suites (S3, `fly.py`) | the above plus board descriptions and sensor peers from a private `sim-fixtures` checkout | **no**: not published |

`firmware/tools/palmpilot.py` wraps the build, flash image and simulation steps once
the toolchain is in place. [docs/simantic.md](docs/simantic.md) explains how the
simulation runs.

## Documents

| Document | Contents |
|---|---|
| [docs/simantic.md](docs/simantic.md) | How the Simantic simulation runs: binaries, machines, stimulus, the drone loop, the suites, speed |
| [docs/simulation.md](docs/simulation.md) | What is simulated, the models, the physics and its verification, known limits |
| [docs/bench-bringup.md](docs/bench-bringup.md) | Moving from simulation to the physical boards: what carried over, what the bench found, the bench profile |
| [docs/wiring/](docs/wiring/README.md) | Pins, circuits, the build order and pinplanner drawings for LEFT, RIGHT and HUB |
| [docs/test-plan.md](docs/test-plan.md) | Every test in order: simulation (A), physical bench (B), physical controller with simulated drone (C) |
| [docs/demo.md](docs/demo.md) | Laptop demo: data path, 3D view, operator procedure, what is missing |
| [docs/gesture-mapping.md](docs/gesture-mapping.md) | Which gesture is which command, and the safety interlocks |
| [docs/bom.md](docs/bom.md) | Parts for the controller |
| [firmware/README.md](firmware/README.md) | Building, simulating, the test suites and the firmware's UART commands |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Evidence rules and firmware rules for changes |
| [CLAUDE.md](CLAUDE.md) | Frozen constraints: pin map, toolchain, command contract, evidence rules (also the instructions for the AI assistant used on this project) |

## Layout

```text
firmware/apps/hand, hub, replay   hand and hub firmware; replay is a scripted stand-in hand
firmware/components/              shared logic (hand_core, hub_core, packet) and UART console
firmware/tests/                   simulation suites S1-S3; run_all.sh runs them all
firmware/tools/                   env.sh (pinned paths), palmpilot.py (build/sim), controller.py; bench/ physical bench tools
firmware/probes/                  engine-defect reproducers and drone flight scripts
simulation/drone/                 bridge, physics, sensor models, SITL cross-check, SITL demo runner
simulation/simantic/              model candidates awaiting release; ADC reference app with physical captures
docs/                             the documents above
tmp/                              gitignored toolchain and build output, not reproducible
```

## Licence

MIT ([LICENSE](LICENSE)), except `simulation/drone/ardupilot_frame.py`, which is a
port of ArduPilot code and is GPLv3, and the Simantic model candidates, which carry
their own notices.
