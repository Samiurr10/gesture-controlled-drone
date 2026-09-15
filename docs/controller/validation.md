# Controller build and validation checklist

**Current result: not run.** Hardware revisions, firmware behavior, battery limits and Pocket electrical compatibility have not been measured in this repository. These checkboxes define work to do; a drawing or calculation is not a passed bench test.

Build in the order below. Use the [build guide](build-guide.md), [firmware work packages](firmware-plan.md), [test record template](test-record-template.md), and [canonical Rev A schematics](../../hardware/schematics/rev-a/schematic-sheets/). Save one record per test/variant, with captures and logs. Copy expected limits into the record **before** running it and mark pass only from measured evidence.

The immediate milestone is the complete controller on the bench, including qualified Pocket operation. Aircraft assembly and motor work come after that milestone. The final flight-controller check below is a later integration test, not a reason to start the aircraft early.

## Test equipment and evidence

- [ ] DMM with resistance/continuity and DC-voltage measurement; known data-capable USB cable and suitable USB supply.
- [ ] Oscilloscope with high-impedance probe for voltage, edge, timing and transient measurements. A logic analyzer may supplement decoding; it cannot establish analog voltage compatibility alone.
- [ ] USB serial logging and a reproducible packet/fault-injection facility once firmware exists.
- [ ] Means to characterize the intended battery range safely under load; record the controlled supply method before using it. Do not force a LiPo below its rated operating range to find a fault threshold.
- [ ] Photographs of each actual board revision, connector cavity numbering, battery polarity and assembled wire labels.
- [ ] Numeric limits for sample age, rail/battery operating range, channel noise, latency, watchdog response and authority transfer recorded before their tests.

## C0 — Confirm parts and build baseline

- [ ] **CTRL-001 — Identity and inventory.** Record parts as received, starting with one Sense #4516 and one flex channel; distinguish planned quantities from parts actually on hand. Extend the record to two Sense boards, one Express #4062, ten sensors and the remaining passives, connectors and protected batteries as later stages arrive. Record actual PCB revisions and confirm firmware library compatibility with each delivered IMU. Record Pocket/EdgeTX details when received.
- [ ] **CTRL-002 — Unpowered wiring.** Remove battery/USB before resistance checks. Confirm one channel against its drawing: `3V → flex → ADC`, separate 47 kΩ and 100 nF branches from ADC to its own GND. Verify connector cavity numbering and no unintended ADC-to-GND bridge. Confirm battery plug polarity. Record photos/continuity outcomes; resistance readings in-circuit can include parallel paths.

## C1 — One flex channel on USB

- [ ] **CTRL-010 — Regulated supply and one raw channel.** Power one Sense on USB. Record measured `3V`, ADC settings and relaxed/comfortably bent ADC/voltage ranges. At an actual 3.300 V rail, 25 kΩ/100 kΩ illustrative sensor values predict 2.154/1.055 V; use measured sensor values for comparison rather than treating examples as limits.
- [ ] **CTRL-011 — One-channel faults and settling.** With output inhibited, unplug the flex and verify a near-ground reading becomes a fault. Using a documented controlled test connection, simulate the flex terminals shorted and verify near-rail input becomes a fault, never maximum motion. Restore the circuit and verify recovery requires valid input and deliberate re-enable. The board-side ADC lead must remain connected to its shunt network; an isolated/floating MCU input is not reliably detected by this circuit.

## C2 — Five-finger left hand

- [ ] **CTRL-020 — Channel identity and interference.** Expand A0–A4 one at a time. Flex only one finger and prove the correct logged channel responds. Exercise high/low adjacent channels and rapid scans; measure settling and cross-channel error against declared limits. Repeat under BLE load when FW-04 exists.
- [ ] **CTRL-021 — IMU identity, axes and neutral.** Log the actual sensor identity and mounting axes. Check individual rotations, stationary drift, neutral repeatability and fault reporting. Record magnetic disturbances if magnetic heading is used. Do not infer absolute heading reliability from a stationary demonstration.
- [ ] **CTRL-022 — Calibration.** Capture comfortable open/bent ranges and orientation neutral. Verify insufficient travel, motion during capture and sensor faults reject calibration. Check save/load integrity, wrong-hand rejection and incompatible-version rejection. Record normalized limits, noise, deadband and filter delay.

## C3 — Left ENABLE, battery and mechanical fit

- [ ] **CTRL-030 — ENABLE button.** Verify open button is HIGH and pressed is LOW, with debounce logged. Boot with it held; control must remain disabled until release/new press. Test release, disconnected lead and reconnect. A short to GND can imitate a press; document that limitation and verify the release-before-enable requirement.
- [ ] **CTRL-031 — Power switch and charging.** Verify EN-to-own-GND switch closed = regulator OFF, open = ON. Confirm programming/charging access and actual battery polarity. Record rail behavior on switching, reset and USB connect/disconnect. EN shutdown is not battery/USB isolation; unplug both for wiring changes.
- [ ] **CTRL-032 — Battery, rail and ADC operating range.** Log meter battery voltage, A6 estimate, `3V`, raw flex readings and BLE/IMU operation through the declared battery range. Characterize regulator dropout and ADC floor near the lower operating boundary under load. A falling `3V` with an internal ADC reference can imitate bending. Set a measured operating floor with margin and hysteresis; verify control invalidates before false gesture, brownout or reset. Repeat for right hand and hub when built.
- [ ] **CTRL-033 — Wearable strain and motion.** Secure fragile sensor terminals, preserve sliding sensing length and inspect protected battery mounting. Exercise full comfortable motion and cable movement while logging. No intermittent connector, range fault or unintended enable may be dismissed as calibration noise. Repeat for the right hand.

## C4 — Second hand

- [ ] **CTRL-040 — Right-hand bring-up.** Repeat applicable CTRL-002/010/011/020/021/022/031/032/033 tests for the right board. Verify its A0–A4 finger labels and separate ground/power domain; it has no external ENABLE button.

## C5 — Hub, two-hand BLE, calibration and command mapping

Build the hub before running the following two-hand link tests.

- [ ] **CTRL-041 — Identity and packet acceptance.** Demonstrate simultaneous known left/right connections. Reject wrong identity, two left roles, unsupported packet version/length, bad fields and obsolete session data. Check bonding behavior and reconnection. Record firmware versions, packet examples and accepted/rejected counts.
- [ ] **CTRL-042 — Duplicate, old and stalled samples.** Inject repeated sequence values, out-of-order packets, older buffered packets, session resets and sequence wrap cases. Also freeze acquisition while communications continues. None may keep freshness alive improperly. Verify counters, local age calculation and the whole-command invalid state. Unsynchronized remote timestamps must not be compared directly to the hub clock.
- [ ] **CTRL-043 — Loss, delay and interference.** Inject controlled drop bursts and delayed delivery for each hand separately, then both. Test disconnect/reconnect, hand power loss and low-battery faults under realistic radio traffic. Record normal and stressed age/interarrival distributions, the selected `T_hand`, and measured detection time. Recovery while ENABLE/SE remain held must not restore authority automatically.

- [ ] **CTRL-050 — Hub input and local state.** Verify hub D6 CALIBRATE, D5 PPM assignment and D9 `/OE`. Calibration is accepted only in the hub's output-inhibited state with operator-confirmed manual/disarmed conditions when applicable. Test calibration during a control request, malformed saved calibration and restart. Log explicit state/rejection causes.
- [ ] **CTRL-051 — Axis mapping.** With trainer output inhibited, test the frozen gesture-to-AETR table one axis at a time. Record directions, neutrals, endpoints, combined motions, filtering and slew limits. Verify throttle initialization/enable transition explicitly; 1500 µs is not automatically low throttle. All sensor or permission failures must invalidate the complete gesture set.

## C6a — Buffer and PPM with JP301 open

Keep the shunt **removed** and radio disconnected throughout these tests. Use HUB_GND as the instrument reference. TP301 is the hub side of JP301; TP302 is the radio side.

- [ ] **CTRL-060 — Buffer assembly and reset state.** Check U301 legs and carrier continuity: five-pin IC pin 5 VCC lands on the six-pad carrier's pad 6. Confirm decoupling, 10 kΩ `/OE` pull-up, 100 kΩ input pull-down, 1 kΩ output series resistor and tip/sleeve cable continuity. Measure VCC, D9 and output around boot/reset/power loss. Disabled output is high impedance; do not assume its voltage must be zero.
- [ ] **CTRL-061 — Complete PPM frame.** Capture eight slots, 22,500 µs frame period, 300 µs markers, 1000–2000 µs channel edge intervals and fixed TR7/TR8 = 1500 µs. Check neutral/endpoints, sync interval and both initial and sustained operation. Record actual timing errors, high/low voltage and overshoot against predeclared limits.
- [ ] **CTRL-062 — Validity and fresh-data heartbeat.** Verify TR1–TR4 AETR, TR5 invalid/valid encoding, and TR6 toggling every two newly generated valid frames (nominal 45 ms half-cycle at uninterrupted frame rate). Freeze one hand's data; TR5 must become invalid by the next complete frame after detection and TR6 must stop advancing. A timer or repeated buffer must not maintain an apparently healthy heartbeat.
- [ ] **CTRL-063 — Frozen hub, watchdog and malformed frames.** Stall acquisition, BLE handling and mapping separately; freeze the application while the timer remains active. Check bounded output submission, no endless replay of a valid frame, watchdog recovery and disabled/invalid boot. Inject truncated frames and restart at awkward phases. Record detection/reset times and scope traces, including failure cases where firmware cannot emit a final invalid frame.

## C6b — Actual Pocket electrical compatibility gate

- [ ] **CTRL-070 — Input compatibility established; JP301 still open.** Obtain the actual Pocket trainer-input limits from manufacturer evidence or competent circuit-level examination/measurement: permitted signal range, input thresholds, loading and power-off behavior. Record the source and actual board revision. The researched family tip/sleeve pinout and a 3.3 V starting waveform do not establish these limits. Idle voltage from a DMM, successful decode or observing the radio's Slave/Jack output alone is insufficient proof of input tolerance.
- [ ] **CTRL-071 — First loaded connection.** Only after CTRL-070 establishes compatibility with the measured hub output, power both devices off, close JP301 and connect TS TIP signal / SLEEVE ground to the **DSC Trainer Port**. Set Pocket to Master/Jack. Measure TP302 loaded levels, transients and timing, then decoded slot values. If the input does not decode, investigate the circuit/format; do not simply increase the signal to 5 V.

If CTRL-070 cannot be resolved, record it as **blocked** and keep JP301 open. The other controller stages can still progress, but the complete controller milestone remains incomplete.

## C6c — Radio authority, dropout and deliberate recovery

Use radio channel monitoring or a suitably instrumented receiver bench setup. Motors/propellers are not needed for this stage. Freeze and export the tested model only after the following pass.

- [ ] **CTRL-080 — Explicit trainer mapping.** Verify TR1/2/3/4 → Ail/Ele/Thr/Rud, signs, neutral and endpoints. Confirm TR5/TR6 health slots cannot arm or change flight modes; physical radio switches retain those functions. Account for actual EdgeTX scaling rather than assuming 1000/2000 µs equals exact ±100%.
- [ ] **CTRL-081 — Physical takeover and throttle mismatch.** Release SE during each gesture direction. Measure time to manual authority and the output step with matching throttle, then deliberately mismatched manual/gesture throttle positions. Record the chosen permitted transfer conditions and operating procedure. The left ENABLE button is a gesture permission input, not a direct motor-power cutoff.
- [ ] **CTRL-082 — Fault matrix and latency.** Run every fault in the matrix below while SE is held. Record failure onset, TR5/TR6 response, radio gate state, output change and time to manual authority. Compare against the predeclared end-to-end limit; repeated old commands must not remain authoritative merely because PPM edges continue.
- [ ] **CTRL-083 — Latched loss and recovery.** Recover each hand/hub/cable while SE stays held; gestures must remain unavailable. Verify release and deliberate re-enable, including boot with held controls, Pocket restart, new BLE sessions, recalibration and return from low battery. Ensure fault latching also covers startup qualification and does not clear itself on a healthy heartbeat.
- [ ] **CTRL-084 — Sustained bench run.** Run the complete controller through the declared battery range and representative motion/interference for a recorded duration. Repeat critical takeover tests near the low-battery boundary. Save logs, model export, firmware commit, calibration and unresolved issues. Duration and pass limits must be selected before this run.

| Required fault injection | Verify and record |
|---|---|
| Either hand off, disconnected, delayed or battery-invalid | All gesture axes lose authority; no partial one-hand continuation |
| Duplicate/old packet, stale acquisition with live BLE | Invalid data does not refresh sample age or heartbeat |
| Sensor open, near-rail reading or failed IMU | Fault becomes invalid permission; normal-looking stuck-sensor detection limits documented |
| Left ENABLE release or broken button lead | Gesture authority ends; new deliberate enable required |
| Hub off, reset, frozen application or watchdog expiry | Output cannot preserve valid authority indefinitely |
| Stopped PPM or cable removed | Radio fallback and measured delay; no reliance on the built-in trainer timeout alone |
| Repeated valid old frame / stuck-high TR6 / stuck-low TR6 | Radio heartbeat gate removes authority and latches the fault |
| Malformed, incomplete or wrong-channel-count PPM | Decoder/gate behavior recorded; no unexpected output accepted |
| SE release / radio restart / reconnect with SE held | Manual takeover independent of hub; no automatic gesture re-entry |
| Manual/gesture throttle mismatch | Output step measured and transfer procedure qualified |

The researched EdgeTX implementation may retain trainer validity for about one second after pulses stop. The proposed 0.1 s heartbeat level-delay setting is a bench candidate, **not a guaranteed 100 ms end-to-end response**. Measure the actual installed version and exported model.

## C7 — Controller bench milestone

- [ ] CTRL-001 through CTRL-084 applicable tests pass for the as-built revision, with actual results and all fault cases attached.
- [ ] Numeric operating ranges and acceptance limits are frozen; unresolved failures have a corrective action and successful retest.
- [ ] Actual firmware can be rebuilt; hand identity/calibration and radio model exports match the tested hardware.
- [ ] Both hands fit comfortably and maintain reliable sensing across the qualified battery range.
- [ ] An operator can demonstrate calibration, enable, manual takeover, fault recognition and deliberate recovery from the written procedure.
- [ ] The complete controller is accepted for later flight-controller bench integration. This milestone makes no claim of aircraft or flight validation.

## Later aircraft integration — after the controller milestone

- [ ] **CTRL-090 — Flight-controller receiver bench.** Once the controller milestone is complete and later aircraft assembly reaches receiver integration, keep propellers removed and motor outputs inhibited for receiver/channel checks. Verify AETR, endpoints, physical radio arm/mode ownership, receiver/FC failsafe configuration, and every relevant dropout/transfer at the flight-controller input. Measure end-to-end failure-to-manual behavior at the downstream endpoint; radio-only results do not prove this stage.
- [ ] Treat propulsion commissioning, restrained tests and flight testing as subsequent aircraft milestones in the root README, with their own evidence. Do not mark them complete from controller tests.
