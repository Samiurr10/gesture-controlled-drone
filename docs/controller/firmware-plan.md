# Controller firmware implementation plan

**Status: specification only; the current Feather controller firmware is not implemented or validated in this repository.** The first deliverable is a controller that works on the bench: two five-finger wearables → BLE hub → qualified Pocket trainer input. Complete the controller milestone before starting the aircraft build.

Use the [controller build guide](build-guide.md), [validation plan](validation.md), and [Rev A drawings](../../hardware/schematics/rev-a/schematic-sheets/). Pin and electrical sources are in [hand research](../schematic-research-hands.md) and [trainer research](../schematic-research-trainer.md). Earlier XIAO/CRSF firmware documents describe a different architecture and do not supply this design's protocol or timing limits.

## 1. Freeze a reproducible baseline — FW-01

- [ ] Record the delivered left/right Sense and hub Express revisions, USB identities and photographs.
- [ ] Select and record an exact Adafruit nRF52 board-package version, compiler/toolchain, build tool, BLE stack and bootloader compatibility; commit the build manifest when implementation begins.
- [ ] Select and pin sensor libraries matching the actual Sense IMU revision. The researched current Sense Rev C uses LSM6DS3TR-C plus LIS3MDL; confirm the received board before selecting its drivers.
- [ ] Create separate left-hand, right-hand and hub build targets with explicit board identifiers and pin constants.
- [ ] Add a minimal build/flash/log procedure and demonstrate rebuilding each target from a fresh checkout.
- [ ] Record the Pocket hardware and installed EdgeTX version. Freeze the tested model export alongside its firmware version when the radio stage passes.

| Baseline item | Selected / tested value |
|---|---|
| Left / right Sense revisions | Not yet recorded |
| Hub Express revision | Not yet recorded |
| Adafruit nRF52 board package and toolchain | Not yet selected |
| Sensor and BLE library versions | Not yet selected |
| Hand / hub firmware commit | Not implemented |
| Pocket hardware / EdgeTX version | Not yet recorded |
| Tested radio model export | Not created |

## 2. One-hand acquisition and diagnostics — FW-02

Begin with one flex channel on USB, then expand to five before adding BLE or gesture output. Firmware must report raw measurements and state so a wiring fault can be separated from a mapping error.

| Input / output | Left Sense | Right Sense | Hub Express |
|---|---|---|---|
| Thumb through little finger | A0, A1, A2, A3, A4 | A0, A1, A2, A3, A4 | — |
| Battery ADC, factory wired | A6 | A6 | A6 |
| External hold-to-enable | D5, active low | — | — |
| External calibration button | — | — | D6, active low |
| PPM output | — | — | D5 |
| Buffer `/OE` | — | — | D9; HIGH disables |

- [ ] Explicitly set 12-bit ADC resolution, internal nominal 3.6 V range and 10 µs acquisition using the pinned core's supported APIs. The researched API names are `analogReadResolution(12)`, `analogReference(AR_INTERNAL)`, and `analogSampleTime(10)`; confirm them against the frozen version.
- [ ] Disable internal pulls on A0–A4. Configure button GPIOs as inputs using their fitted external pull-ups; implement software debounce (20 ms stable state is an initial bench setting).
- [ ] Allow at least 50 ms after supply stabilization before accepting samples, calibration or control permission. Initialization or self-test failure leaves control invalid.
- [ ] Log timestamp, five raw ADC readings, converted voltages, IMU identity and raw measurements, battery voltage, button state, calibration status and every fault reason.
- [ ] Check A6 battery conversion against a meter. The nominal 12-bit relationship is `Vbat = 2 × raw × 3.6 / 4096`; measure board-specific error before selecting thresholds.
- [ ] Test adjacent-channel settling using widely different input values, then with BLE active. Do not accept a channel scan merely because single-channel readings look stable.
- [ ] Record IMU axes and sensor mounting orientation. Select and validate the orientation estimator; document drift, filtering and whether yaw uses magnetic sensing. No reliable absolute heading is assumed.
- [ ] Detect rail-adjacent flex readings and IMU failures. Treat them as invalid input, never as an extreme gesture. Record the limits of detection: an in-range stuck reading or cross-channel short may escape a range check.

### Battery and regulated-rail acceptance

The dividers use the board's `3V` rail, while the selected ADC reference is internal. A falling regulated rail can therefore lower all flex readings and imitate finger bending. Battery protection cutting power is not an adequate operating threshold.

- [ ] Measure battery voltage, local `3V`, raw ADC readings and reset behavior over the intended battery operating range under sensor/BLE load.
- [ ] Identify regulator dropout and ADC floor behavior near the intended lower operating limit using an appropriate controlled supply procedure; do not deliberately overdischarge a LiPo.
- [ ] Set and record a conservative battery acceptance floor and hysteresis for each board, with measured margin above rail sag, false gestures, unstable operation and reset.
- [ ] Invalidate hand/hub control before the characterized operating boundary. If rail compensation or ratiometric measurement is introduced, document and validate that change before relying on it.

Thresholds are **not yet locked**. The acceptance gate is measured correct input behavior across the declared rail/battery range, not just a nominal battery number.

## 3. Calibration and comfortable ranges — FW-03

- [ ] Provide an explicit calibration state with gesture output invalid. The hub button starts a documented stationary-hand capture procedure, with clear local status and success/failure feedback.
- [ ] Collect each finger's comfortable open/bent distributions, orientation neutral and noise/drift. Reject insufficient range, unstable capture, wrong identity, failed IMU or inadequate battery.
- [ ] Store versioned calibration per physical hand identity, side and sensor configuration, with integrity checks. Do not apply left calibration to the right board or silently accept incompatible saved data.
- [ ] Bound normalized values, apply documented filters/deadbands, and invalidate out-of-plausibility data. Clamp only normal valid travel; clamping a fault into a plausible gesture hides the fault.
- [ ] Require release and a new deliberate enable after calibration, reboot, reconnection or a fault. A button already held during boot must not enable control.

The hub's PPM connection is one-way: the hub cannot infer the Pocket's SE position or aircraft armed state from it. Calibration therefore requires the hub's own output-inhibited/service state **and an operator check of manual radio authority and disarmed aircraft if one is connected**. Do not claim automatic knowledge of radio or flight-controller state without implementing and testing a separate feedback path.

## 4. Two-hand BLE contract — FW-04

Implement two distinct hand peripherals and one hub central. Treat the following packet schema as a proposed version-1 contract to freeze with the implementation.

| Field | Required purpose |
|---|---|
| Protocol version and exact length | Reject unsupported/truncated packets |
| Allowlisted device identity and hand side | Require one known left and one known right hand |
| Boot/session identifier | Recognize resets and invalidate continuity across sessions |
| Sequence counter | Reject duplicates, replays and out-of-order samples; define wrap handling |
| Acquisition counter and local sample timestamp | Detect stalled sampling even if the communications task remains alive |
| Five flex measurements | Supply traceable sensor data in a documented representation |
| Orientation / IMU sample and health | Supply defined units/axes plus estimator validity |
| Battery and calibration validity | Invalidate operation outside qualified conditions |
| Debounced enable state, left only | Carry the hold-to-enable request; right must not assert it |

- [ ] Freeze byte order, units, bounds, counter widths, sequence-wrap rules and session behavior; add captured example packets to the implementation docs.
- [ ] Bind each hand to an expected identity/side; reject unknown peers, duplicate sides and identity mismatches. Implement and test the selected BLE bonding/authentication policy.
- [ ] Use a monotonic **hub-local** receive timestamp for the age limit. Do not subtract an unsynchronized hand clock from the hub clock.
- [ ] Track sample progress as well as packet arrival: repeated packets or a live communications loop with frozen acquisition must not refresh freshness.
- [ ] Choose bounded queues/latest-sample processing so old notifications cannot accumulate and later appear current. Evaluate acquisition timestamps/counter progress for buffered data; define any clock-offset or elapsed-time checks explicitly.
- [ ] Require both hands to pass identity, session, sequence, sample-age, calibration, health and battery checks together. A missing or invalid hand invalidates the complete gesture command set.
- [ ] Log accepted/rejected packet counts, rejection reasons, interarrival distribution, sample age and disconnect/recovery events.

### Timing decisions to measure before freezing

| Parameter | Current status | Evidence required to lock it |
|---|---|---|
| Hand acquisition and BLE notification rates | Proposed design decision; unset | Both-hand throughput, radio interference, battery cost and orientation performance |
| Maximum accepted sample age `T_hand` | Proposed design decision; unset | Measured end-to-end age under normal load and injected delay, plus chosen maximum allowable stale-command interval |
| Allowed left/right sample skew | Proposed design decision; unset | Simultaneous-motion test and pairing policy |
| MCU watchdog timeout / service interval | Proposed design decision; unset | Freeze/stall testing across all intended loads |
| End-to-end fault-to-manual limit | Proposed acceptance decision; unset | Hub detection, PPM phase, EdgeTX evaluation and downstream output measurements |

Record numeric pass limits **before** qualification tests. The older XIAO design's timing values do not apply by inheritance.

## 5. Hub mapping and control state — FW-05

- [ ] Freeze a gesture-to-axis table that names physical hand motion, neutral, direction, minimum/maximum, filter, deadband and slew limit for roll, pitch, throttle and yaw. Agree and bench-check the table before using it for control.
- [ ] Implement a simulator/diagnostic mode showing both raw input and mapped AETR values with trainer output inhibited. Verify one axis at a time, then simultaneous motions and mechanical range limits.
- [ ] Explicitly define throttle startup, enable and manual-to-gesture transfer behavior. A centered 1500 µs throttle is **not** assumed to mean minimum thrust.
- [ ] Require both calibrated, fresh hands and a new left-button press for local permission. Release of the left ENABLE button invalidates control; it never arms the aircraft.
- [ ] Make calibration, low battery, sensor faults, BLE faults and reset visible, with local output invalid and a release/re-enable requirement.

| Hub state | Required behavior |
|---|---|
| Boot / self-test | D9 HIGH, D5 LOW; no driven trainer waveform until initialized |
| Output-inhibited service / calibration | No gesture authority; no valid gesture stream |
| Waiting for valid hands / deliberate enable | Validity low; do not resume because an old button state is still held |
| Locally permitted | Fresh validated two-hand data can produce valid frames; the radio still decides final authority |
| Fault latched | Validity low, heartbeat frozen; stop/gate output as tested; record cause |
| Recovery pending | Recheck all conditions; require button release/new press and independent radio re-enable |

## 6. Finite PPM generation and application heartbeat — FW-06

Implement exactly **eight slots per 22,500 µs frame**, with **300 µs markers** and 1000–2000 µs channel edge intervals. Start with positive markers. Actual radio decoding and electrical compatibility are separate gates.

| Trainer slot | Meaning | Encoding |
|---|---|---|
| TR1 | Aileron / roll | 1000–2000 µs; neutral 1500 µs |
| TR2 | Elevator / pitch | 1000–2000 µs; neutral 1500 µs |
| TR3 | Throttle | 1000–2000 µs; transfer/start behavior explicitly qualified |
| TR4 | Rudder / yaw | 1000–2000 µs; neutral 1500 µs |
| TR5 | Validated hand data / local permission | 1000 µs invalid; 2000 µs valid; **not aircraft arm** |
| TR6 | Application-health heartbeat | Alternate 1000/2000 µs every two freshly generated valid frames |
| TR7 | Reserved | Fixed 1500 µs |
| TR8 | Reserved | Fixed 1500 µs |

For each channel, drive HIGH for 300 µs and LOW for `channel_us − 300`. After the eight channels, emit the final marker and complete the sync interval so that the last marker to the next frame start equals `22,500 − sum(channel_us)`. With TR7/TR8 fixed neutral, the actual sync edge interval spans 7500–13,500 µs; the broader eight-variable-channel calculation in the research is a decoder check, not a change to these reserved slots.

- [ ] Use hardware timing for individual edges and bounded, complete frame submission. Do not continuously loop a DMA/PWM buffer of old commands.
- [ ] Generate the heartbeat in the checked application-data path. Advance it only after two fresh, valid frames built from newly validated samples from **both** hands; timer interrupts alone do not prove live acquisition or mapping.
- [ ] Sustain the expected heartbeat half-cycle of 45 ms when data are fresh each frame. If new validated samples are unavailable for a frame, mark output invalid and stop advancing the heartbeat.
- [ ] On stale/invalid input, publish TR5 invalid in the next complete frame while freezing TR6, if execution is still running; then stop or disable according to the tested takeover design. Do not depend on sending this frame after a total MCU freeze.
- [ ] Implement a watchdog serviced only when acquisition/communications validation, mapping and bounded output submission have progressed. A timer-only watchdog feed cannot demonstrate application health.
- [ ] Initialize D9 HIGH before configuring D5; keep `/OE` disabled until a complete invalid frame stream is ready. Resets must return to disabled/invalid behavior through the external pull-up.
- [ ] Measure timing, levels, startup/reset transients and behavior after frozen tasks at TP301 with JP301 open. Store scope captures and logs.

## 7. Pocket authority and recovery — FW-07

Complete electrical qualification before closing JP301. Then implement and export the tested EdgeTX **Master/Jack** model, mapping TR1–TR4 explicitly to Ail/Ele/Thr/Rud. Keep physical radio arm and mode switches independent of TR5/TR6.

Required authority expression:

```text
gesture_authority = SE_held
                 AND trainer_link_active
                 AND TR5_valid
                 AND heartbeat_changed_recently
                 AND NOT latched_fault
```

- [ ] Gate trainer replacement with this complete condition. Release of the Pocket SE momentary switch must always restore manual authority.
- [ ] Implement a fault latch so a recovered stream cannot restore gestures while SE remains held. Require release followed by a deliberate re-enable.
- [ ] Validate startup, held-SE reboot, cable reinsertion and invalid-to-valid recovery. A recovered signal alone must not be treated as operator consent.
- [ ] Test the proposed TR6 stuck-high/stuck-low logical-switch delays. The research suggests 0.1 s delayed level tests, but the final setting and measured response are **not yet qualified** for the actual EdgeTX version.
- [ ] Measure manual-throttle steps during transfer at matched and deliberately mismatched positions; define an acceptable transfer procedure and limits before controller qualification.
- [ ] Export the final radio model, record its hash and firmware version, and link fault-injection evidence.

The inspected EdgeTX source can retain trainer validity for approximately one second after pulses stop. A valid-looking repeated PPM frame can persist longer. Therefore stopped PPM alone is insufficient; test the TR5/heartbeat gate and latch together. Do not claim a 100 ms fallback guarantee from the proposed 0.1 s logical-switch setting.

## Completion evidence

- [ ] All applicable controller tests in [validation](validation.md) pass against recorded numeric limits, with failures closed and retested.
- [ ] Source, build instructions, pinned dependencies, calibration format, packet specification and diagnostic instructions are committed for the implemented firmware.
- [ ] Radio model export and measured hardware configuration match the tested setup.
- [ ] The controller bench milestone is signed off before aircraft assembly begins. Later flight-controller and flight validation remain separate milestones.
