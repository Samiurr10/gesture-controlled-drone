# ESP32-S3 controller simulation and prototype validation

**Current full ESP controller acceptance: NOT RUN.** Narrow executed diagnostic
results are linked in the [Simantic plan](simantic-plan.md); they do not pass
complete firmware/driver or physical acceptance. This migration defines the
working board and tests. Reusing a CTRL ID does not transfer a prior result
to a different ESP32-S3 build or fixture.

Order: **S0–S3 ESP controller simulation → C0–C7 physical controller → later STM32
virtual drone**. No physical drone is planned. Use the [bench plan](build-guide.md),
[firmware packages](firmware-plan.md) and [Simantic gates](simantic-plan.md). Record limits before each run and retain
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
  build guide is the continuity reference.

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
  against that design. RST/EN is not a battery disconnect. **Pending design; no default BAT/charger assumed.**
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
