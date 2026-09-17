# ESP32-S3 controller simulation and prototype validation

**Current full ESP controller acceptance: NOT RUN.** Narrow executed diagnostic
results are linked in the [Simantic plan](simantic-plan.md); they do not pass
complete firmware/driver or physical acceptance. This migration defines the
working board and tests. The earlier nRF52840/H7 capability audit remains evidence only for its recorded
platforms and fixtures. Reusing a CTRL ID does not transfer a prior result to ESP.

Order: **S0–S3 ESP controller simulation → C0–C7 physical controller → later STM32
virtual drone**. No physical drone is planned. Use the [bench plan](build-guide.md),
[firmware packages](firmware-plan.md), [Simantic gates](simantic-plan.md) and
[test record](test-record-template.md). Record limits before each run and retain
captures; leave missing evidence open. A new reviewed ESP schematic/netlist and
wearable power circuit are prerequisites for permanent assembly, not completed
artifacts in this checklist.

## S0–S3 — Fresh ESP simulation gates

- [ ] **S0:** Pin ESP32-S3 model/hash and ESP-IDF/Xtensa configuration, load/boot
  the real firmware and assert UART0, ADC1/calibration, GPIO, timing, reset,
  watchdog and used storage behavior. Verify the external-IMU I2C driver path.
  Report substitutions and missing behaviors; catalog presence is not a pass.
- [ ] **S1:** Exercise one GPIO1 flex channel, then GPIO1/2/4/5/6, external
  LSM6DS3TR-C/LIS3MDL on GPIO8/9, calibration and GPIO7 ENABLE through actual
  drivers. USB bench power is explicit; battery behavior remains a separate
  modeled-logic/physical-power dependency.
- [ ] **S2:** Prove two concurrent ESP BLE peripheral links to the ESP hub, then
  identity/session/sequence/acquisition-progress, freshness, whole-command
  invalidation, mapping and deliberate recovery in project firmware.
- [ ] **S3:** Independently decode hub commands at a host test sink. Assert
  expiry, malformed/delayed/replayed data rejection, reset/watchdog and recovery.
  Name the actual UART/TCP or native-USB path; test them separately if both used.
- [ ] Keep host logic, peripheral simulation, injected application input and
  physical results separate. User-generated ADC voltages and sensor register
  responses must traverse the modeled drivers to close peripheral coverage.

S3 covers the controller boundary. Later drone integration must trace STM32
firmware actuator outputs through dynamics to displayed movement.

## Physical equipment and records

- [ ] Data-capable USB cable/supply, DMM, continuity and resistance tools.
- [ ] Oscilloscope where analog noise, rail transients or timing require it;
  a logic analyzer can supplement bus decoding but cannot measure analog limits.
- [ ] Serial logs and deterministic packet/fault injection for implemented firmware.
- [ ] Actual module markings, PCB revision, connector cavities, wiring revision
  and photos. ESP-IDF/compiler/build hashes and calibrated ADC configuration.
- [ ] Numeric limits for noise, voltage range, latency, age, watchdog and recovery
  selected before testing; reviewed controlled-supply method for later power tests.

## C0 — Confirm board and wiring

- [ ] **CTRL-001 — Identity and inventory.** Begin with one genuine
  ESP32-S3-DevKitC-1-N8R2 and one flex. Record module suffix, PCB revision,
  flash/PSRAM and actual USB ports. Later extend to three boards, ten flex
  channels and two Adafruit #5543 modules. Distinguish required parts from stock.
- [ ] **CTRL-002 — Unpowered wiring.** Remove all power and verify each new ESP
  connection: own 3V3 → flex → assigned GPIO, separate 47 kΩ/100 nF shunts to own
  GND. Verify connector numbering and external IMU power/bus connections. The
  legacy Rev A wire list is not this board's continuity reference.

## C1 — One flex, USB powered

- [ ] **CTRL-010 — Supply and calibrated ADC.** Power through USB-to-UART port.
  Measure 3V3 and GPIO1 voltage; record 12-bit ADC1/attenuation/calibration setup
  and straight/comfortable-bent counts/millivolts. Compare against meter readings
  and measured sensor resistance. The 2.154/1.055 V divider examples are not
  calibration limits. Verify the usable measurement span and rail saturation.
- [ ] **CTRL-011 — Faults and settling.** With output inhibited, test unplugged
  sensor and controlled shorted-flex conditions. Near-ground/rail results must
  fault, never command maximum motion. Measure startup settling and recovery.
  Keep the MCU connected to its shunt network; document floating-wire limitations.

## C2 — Five flex inputs and external motion

- [ ] **CTRL-020 — Channel identity and interference.** Add GPIO2/4/5/6 in order;
  confirm thumb/index/middle/ring/little mapping. Alternate high/low channels,
  measure settling/coupling and repeat under BLE load with declared noise limits.
- [ ] **CTRL-021 — External IMU.** Verify #5543 power and 0x6A/0x1C identities,
  required initialization/data reads, mounting axes, neutral, drift and sensor
  timeout/fault handling. Qualify magnetic heading separately if used.
- [ ] **CTRL-022 — Calibration.** Test comfortable ranges, insufficient travel,
  unstable capture, invalid sensor/power state, save/load integrity, interrupted
  write and wrong-hand/version rejection. Record normalization and filter delay.

## C3 — Left ENABLE and wearable power/mechanics

USB bench sensing can progress while wearable power is designed. C3 remains
open until that power design and the actual assembly pass the following tests.

- [ ] **CTRL-030 — GPIO7 ENABLE.** Verify external pull-up HIGH, pressed LOW,
  debounce, release and disconnected lead. Boot/reconnect with button held must
  require release/new press. Document that a short to GND can imitate a press.
- [ ] **CTRL-031 — Reviewed power circuit.** Before a cell is connected, record
  charger/protection, regulator/current budget, disconnect and USB coexistence.
  Measure switching, charging, rail transients, reset and USB insertion/removal
  against that design. RST/EN is not a battery disconnect; old Feather EN wiring
  does not apply. **Pending design; no default BAT/charger assumed.**
- [ ] **CTRL-032 — Battery monitor and operating range.** After selecting an
  external monitor, verify scaled ADC voltage and calibration against a meter.
  GPIO10 remains disconnected until that revision exists. Characterize battery,
  local 3V3 and flex/IMU/radio behavior under load; establish operating floor and
  hysteresis before rail sag, false gestures or reset. Test each wearable; test
  hub USB interruption separately. No former A6 scale or floor is inherited.
- [ ] **CTRL-033 — Wearable fit.** Test strain relief, free flex movement, cable
  motion, secure reviewed power assembly and comfortable mounting. No intermittent
  input or unintended enable may be dismissed as calibration noise.

## C4 — Right hand

- [ ] **CTRL-040 — Independent right bring-up.** Repeat applicable C0–C3 sensor,
  calibration, power and mechanical tests on its own local supply/ground. Use
  GPIO1/2/4/5/6 and external motion on GPIO8/9; no right ENABLE. Verify distinct
  identity/side and calibration. A left result does not pass the right board.

## C5 — ESP hub and two-hand BLE

- [ ] **CTRL-041 — Two links and identity.** Demonstrate two simultaneous known
  hand connections to the ESP hub. Reject unknown peers, duplicate sides, wrong
  version/length/fields and obsolete sessions. Record actual stack/configuration.
- [ ] **CTRL-042 — Old/stalled samples.** Inject duplicates, reorder, queued old
  samples, session resets/wrap and acquisition frozen behind live BLE. None may
  refresh freshness incorrectly; use hub-local clock and whole-command validity.
- [ ] **CTRL-043 — Loss and interference.** Test each/both hand loss, delay/drop
  bursts, power faults and reconnect under radio load. Record selected `T_hand`,
  distributions and measured invalidation. Held ENABLE must not restore validity.
- [ ] **CTRL-050 — Hub calibration/state.** Test GPIO7 CALIBRATE only while
  output is inhibited and host session stopped. Verify invalid profiles,
  calibration during a request, restart and explicit state/rejection messages.
- [ ] **CTRL-051 — Axis mapping.** Verify agreed signs, neutral/endpoints,
  combined motion, filters/slew limits, roll/pitch/yaw [-1, 1] and throttle [0, 1].
  Test throttle boot/enable transition and whole-command invalidation.

## C6 — Physical hub-to-host bridge

- [ ] **CTRL-052 — Command contract and transport.** Independently decode actual
  hub UART0 output through its onboard USB-to-UART bridge. Check FW-06 framing,
  schema, sessions, acquisition progress, bounds, validity and faults. Record
  baud/host driver; native USB needs its own test if selected. Simulated TCP alone
  does not establish this physical path.
- [ ] **CTRL-053 — Expiry and watchdog.** Independently freeze hand acquisition,
  BLE, mapping/output and host processing; test disconnect, reset and buffered
  delivery. Measure onset, last fresh command and receiver expiry. Continued
  traffic cannot preserve stale commands; expiry cannot depend on a final message.
- [ ] **CTRL-054 — Stop/reset/recovery.** Release ENABLE in every direction;
  stop/reset the host and restore links with ENABLE held. Require valid inputs,
  release/new press and deliberate host restart. Record throttle transitions.

## C7 — Physical controller acceptance

- [ ] **CTRL-055 — Sustained demonstration.** Run two wearables, ESP hub and
  host sink for a predeclared duration across the qualified power range and
  movement/radio conditions. Repeat critical faults near the power boundary;
  save logs, firmware, calibration and wiring/power revisions.
- [ ] All applicable CTRL-001–055 requirements pass on this ESP physical build.
- [ ] Numeric limits are frozen and every failure has a corrective action/retest.
- [ ] Rebuild, calibration, operator enable/stop/reset and deliberate recovery
  are reproducible from the archived procedure.
- [ ] Accept the controller boundary for the later [STM32 virtual drone](../drone-simulation.md).
  Pocket/PPM and physical aircraft/flight work are not prerequisites.

## Optional historical trainer validation — nRF Rev A only

**Legacy pin/circuit reference.** D5/D9/U301/JP301/TP301 below belong to the old
Feather package. No ESP trainer wiring has been assigned or qualified; do not
apply these pad names to the ESP board. These tests remain outside S3/C7 and
would need a reviewed ESP extension schematic before future implementation.


The following retained CTRL IDs apply only if the trainer extension is pursued.
Mark them **NOT APPLICABLE (optional extension)** for the active project; they do
not block controller or drone-simulation completion. The electrical gates remain
mandatory before connecting this optional circuit to a real radio.

### Trainer buffer and PPM with JP301 open

Keep the shunt **removed** and radio disconnected throughout these tests. Use HUB_GND as the instrument reference. TP301 is the hub side of JP301; TP302 is the radio side.

- [ ] **CTRL-060 — Buffer assembly and reset state.** Check U301 legs and carrier continuity: five-pin IC pin 5 VCC lands on the six-pad carrier's pad 6. Confirm decoupling, 10 kΩ `/OE` pull-up, 100 kΩ input pull-down, 1 kΩ output series resistor and tip/sleeve cable continuity. Measure VCC, D9 and output around boot/reset/power loss. Disabled output is high impedance; do not assume its voltage must be zero.
- [ ] **CTRL-061 — Complete PPM frame.** Capture eight slots, 22,500 µs frame period, 300 µs markers, 1000–2000 µs channel edge intervals and fixed TR7/TR8 = 1500 µs. Check neutral/endpoints, sync interval and both initial and sustained operation. Record actual timing errors, high/low voltage and overshoot against predeclared limits.
- [ ] **CTRL-062 — Validity and fresh-data heartbeat.** Verify TR1–TR4 AETR, TR5 invalid/valid encoding, and TR6 toggling every two newly generated valid frames (nominal 45 ms half-cycle at uninterrupted frame rate). Freeze one hand's data; TR5 must become invalid by the next complete frame after detection and TR6 must stop advancing. A timer or repeated buffer must not maintain an apparently healthy heartbeat.
- [ ] **CTRL-063 — Frozen hub, watchdog and malformed frames.** Stall acquisition, BLE handling and mapping separately; freeze the application while the timer remains active. Check bounded output submission, no endless replay of a valid frame, watchdog recovery and disabled/invalid boot. Inject truncated frames and restart at awkward phases. Record detection/reset times and scope traces, including failure cases where firmware cannot emit a final invalid frame.

### Actual Pocket electrical compatibility gate

- [ ] **CTRL-070 — Input compatibility established; JP301 still open.** Obtain the actual Pocket trainer-input limits from manufacturer evidence or competent circuit-level examination/measurement: permitted signal range, input thresholds, loading and power-off behavior. Record the source and actual board revision. The researched family tip/sleeve pinout and a 3.3 V starting waveform do not establish these limits. Idle voltage from a DMM, successful decode or observing the radio's Slave/Jack output alone is insufficient proof of input tolerance.
- [ ] **CTRL-071 — First loaded connection.** Only after CTRL-070 establishes compatibility with the measured hub output, power both devices off, close JP301 and connect TS TIP signal / SLEEVE ground to the **DSC Trainer Port**. Set Pocket to Master/Jack. Measure TP302 loaded levels, transients and timing, then decoded slot values. If the input does not decode, investigate the circuit/format; do not simply increase the signal to 5 V.

If CTRL-070 cannot be resolved, record it as **blocked** and keep JP301 open. Only this optional trainer extension remains blocked; the active controller prototype and drone simulation can still be completed.

### Radio authority, dropout and deliberate recovery

Use radio channel monitoring or a suitably instrumented receiver bench setup. Motors/propellers are not needed for this stage. Freeze and export the tested model only after the following pass.

- [ ] **CTRL-080 — Explicit trainer mapping.** Verify TR1/2/3/4 → Ail/Ele/Thr/Rud, signs, neutral and endpoints. Confirm TR5/TR6 health slots cannot arm or change flight modes; physical radio switches retain those functions. Account for actual EdgeTX scaling rather than assuming 1000/2000 µs equals exact ±100%.
- [ ] **CTRL-081 — Physical takeover and throttle mismatch.** Release SE during each gesture direction. Measure time to manual authority and the output step with matching throttle, then deliberately mismatched manual/gesture throttle positions. Record the chosen permitted transfer conditions and operating procedure. The left ENABLE button is a gesture permission input, not a direct motor-power cutoff.
- [ ] **CTRL-082 — Fault matrix and latency.** Run every fault in the matrix below while SE is held. Record failure onset, TR5/TR6 response, radio gate state, output change and time to manual authority. Compare against the predeclared end-to-end limit; repeated old commands must not remain authoritative merely because PPM edges continue.
- [ ] **CTRL-083 — Latched loss and recovery.** Recover each hand/hub/cable while SE stays held; gestures must remain unavailable. Verify release and deliberate re-enable, including boot with held controls, Pocket restart, new BLE sessions, recalibration and return from low battery. Ensure fault latching also covers startup qualification and does not clear itself on a healthy heartbeat.
- [ ] **CTRL-084 — Sustained optional trainer run.** Run the controller with the optional trainer extension through the declared battery range and representative motion/interference for a recorded duration. Repeat critical takeover tests near the low-battery boundary. Save logs, model export, firmware commit, calibration and unresolved issues. Duration and pass limits must be selected before this run.

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

## Retired physical-aircraft test ID

**CTRL-090** formerly described a physical receiver/flight-controller bench and
later flight work. It is retired from the active acceptance checklist because
no physical drone is being built. Preserve old records under their original
scope if any exist; use the separate [drone simulation acceptance plan](../drone-simulation.md)
for modeled drone inputs, MCU outputs, dynamics and on-screen movement. A
controller test alone cannot pass that second-goal integration.
