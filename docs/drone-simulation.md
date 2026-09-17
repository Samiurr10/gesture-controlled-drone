# Drone hardware, MCU and mechanical simulation

**Goal 2 — after the controller works.** The drone exists in simulation and moves on a computer screen. There is no physical aircraft construction or flight phase. The immediate priority remains [controller simulation](controller/simantic-plan.md), then the [physical hand-controller prototype](controller/README.md).

The hand controller now uses **ESP32-S3**; the virtual drone candidate remains **STM32H743/KakuteH7 with ArduCopter 4.7.1**. MCU families need not match. The [current feasibility assessment](implementation-records/2026-09-16_esp32-full-drone-feasibility.md) records actual runtime tests. Full flight-firmware operation, mechanics, output bridge and renderer remain unqualified or unimplemented.

## Required signal path

```text
Physical ESP32-S3 gesture controller
    -> validated host command bridge
    -> drone command-input peripheral/model in Simantic
    -> flight-control firmware executing on simulated MCU
    -> observable motor/actuator output signals
    -> signal decoder and virtual motor/actuator model
    -> mechanical dynamics: forces, torques, position and orientation
    -> on-screen drone display

Mechanical state -> virtual IMU / other required sensors -> drone MCU feedback
```

The display renders the mechanical state. It must not translate gestures directly into screen position while bypassing the simulated drone MCU or motor outputs. An isolated visual mockup can help development, but it does not satisfy this goal.

The flight-control loop needs feedback: derive virtual sensor readings from the same state used by the display and provide them through the modeled sensor interfaces. State which electrical, actuator and sensor behaviors are idealized. MCU emulation alone does not establish electrical or mechanical fidelity.

## D1 — Drone hardware/MCU feasibility

**Implementation dependency:** qualified controller C7 before the integrated demonstration. The user's request authorizes drone feasibility tests now in parallel with controller qualification; it does not mark S0–S3 or C0–C7 complete.

- [ ] Select a virtual MCU/board configuration and flight-control firmware that can actually run in Simantic.
- [ ] Freeze boot layout, clocks, interrupt/timer behavior, required buses, virtual sensor models and a reproducible firmware build.
- [ ] Define the drone's command-input interface and adapter from the controller's versioned host records.
- [ ] Boot firmware, feed deterministic sensor/command inputs and observe changing motor outputs at the simulated peripheral boundary.
- [ ] Record supported, unsupported and approximated features, including the APIs used to inject sensors and capture outputs.

The STM32H743 candidate runs stock ArduCopter through IMU FIFO transactions and repeated vehicle-loop execution using explicit sensor/absent-device fixtures. Four alternate main-channel PWM routes also work in a separate diagnostic. Motor mapping in flight firmware, estimator health and closed feedback remain unqualified; original motor-output/DMA limitations remain recorded. The [H7 audit](../simulation/simantic/capability-audit/stm32h7/README.md) and [extended run](../simulation/simantic/capability-audit/full-drone/README.md) define the evidence boundary. Resolve required gaps or document a target change before claiming D1.

**Exit:** a repeatable firmware-driven demonstration of command input, sensor input and observable motor outputs, with model/firmware versions and traces saved.

## D2 — Output-driven mechanics

- [ ] Qualify all four firmware motor outputs. Initial PWM may avoid the DMA requirements of DShot; the tested Kakute M1/M2 TIM1 complementary channels still need correct output behavior. Two passing TIM2 channels alone are insufficient.
- [ ] Decode motor channel identity, signal value, validity and simulation timestamp; define reset, missing-output and malformed-output behavior.
- [ ] Map outputs to virtual motor response, thrust and reaction torque using documented units, limits and model parameters.
- [ ] Define mass, inertia, motor positions/rotation, gravity, initial state and any drag or ground-contact assumptions.
- [ ] Integrate position, velocity, attitude and angular velocity at a declared simulation time step.
- [ ] Convert the resulting state to the virtual sensors used by the MCU and close the feedback loop.
- [ ] Test motor ordering, torque signs, units, coordinate transforms and reproducibility with fixed input traces.

Define the body/world axes and orientation convention once. The hardware simulator, dynamics model and renderer may use different conventions only through explicit tested transforms.

Use a shared virtual timeline or a documented synchronization scheme. Record how commands from the physical controller are timestamped and resampled, how paused runs handle queued packets and how simulator lag is detected. Replayed old inputs must not become fresh after resume.

**Exit:** MCU actuator changes cause the expected mechanical response; resulting sensor readings return to the MCU; repeated runs agree within declared numeric tolerances.

## D3 — Display and controller integration

- [ ] Render the dynamics model's position and attitude; show command validity, simulation state and relevant fault status.
- [ ] Connect the physical hand controller through the C6 host bridge to the virtual drone command input.
- [ ] Provide explicit start/enable, stop and reset controls, with visible inhibited/running/fault states.
- [ ] Freeze handling of invalid hand data, stale hub packets, USB loss, MCU reset and simulator stalls.
- [ ] Distinguish a paused/reset run from an intentionally simulated failsafe response. Display neither stale motion as live nor invalid inputs as valid.
- [ ] Require deliberate recovery after a fault; a held hand enable alone cannot restart or arm the virtual drone.

The old Pocket/PPM/ELRS path is not required for this integration. A future optional radio-interface experiment must not block the controller-to-computer path.

**Exit:** a user can operate the physical controller, observe the resulting simulated drone movement, stop/reset the run and recover predictably from injected faults.

## D4 — End-to-end qualification

| Scenario | Evidence required |
|---|---|
| Neutral and deliberate start | Valid calibrated inputs, defined initial state, no automatic start from boot or reconnect |
| Roll, pitch, yaw and throttle individually | Controller record → MCU motor output → mechanical response → displayed state, all on a synchronized timeline |
| Combined gestures | Bounded inputs, documented mapping and predictable combined response |
| Controller faults | Invalid calibration, sensor errors, either hand lost/stale, hub reset, disconnect and malformed commands produce the specified inhibited/failsafe response |
| Simulator faults | Missing motor outputs, MCU reset, lag/pause/resume and sensor-feedback loss are detected and handled |
| Repeatability | Fixed firmware/models/parameters/seed and recorded command traces reproduce results within declared tolerances |
| Live demonstration | Measured controller-to-display latency, stated runtime and documented model limits |

Assign records `DRONE-001` (D1), `DRONE-002` (D2), `DRONE-003` (D3) and `DRONE-004` (D4), with scenario suffixes as needed. Set numeric limits before each test; none are established by this plan.

**Exit:** the qualified physical hand controller drives the Simantic drone MCU; its output signals drive the mechanical simulation; that state produces visible screen motion. Archive a repeatable launch procedure, interface specification, versions, parameters, synchronized logs and a demonstration recording.

## Records and exclusions

Use [implementation records](implementation-records/README.md) and the [test record template](controller/test-record-template.md). Identify which boundaries use real hardware, emulated peripherals, idealized models or application mocks. A successful visual demonstration is not evidence of physical-drone stability, lift, range, battery endurance or flight readiness.

Physical aircraft procurement, wiring, propulsion tests, Remote ID installation, flight testing and airborne recovery are outside the current scope. Historical aircraft drawings remain references only. Current execution checkpoints are in the [root README](../README.md#full-implementation-checkpoints).
