# Safety, Boundary, and Test Plan

## Safety Position

This system is an experimental aircraft with spinning exposed-energy hardware,
LiPo batteries, a prototype radio, one flight IMU, and custom propellers/body.
Software features reduce risk but do not certify the aircraft. Free flight is
not permitted until the evidence gates below pass on the final assembled
configuration.

The first safety principle is layered containment:

1. Low mass, guards, low speed, low altitude, and conservative propulsion.
2. Hand deadman, explicit ARM, and guarded KILL.
3. Aircraft-gateway packet validation and 60 ms freshness limit.
4. PX4 prearm checks, Position mode, geofence, RC-loss Land, and low-battery
   action.
5. Four-direction ToF collision braking after its separate validation gates.
6. A netted enclosure indoors or a physically clear area outdoors.
7. A second person ready to disconnect the battery after landing or a fault.

No single software switch is called the safety system.

## Boundary Definition

### Outdoor bounded volume

| Layer | Initial limit | Enforcement |
|---|---:|---|
| Pilot operating target | 10 m radius, 3 m above home | Operator procedure and observer callout |
| PX4 fence | 15 m horizontal, 5 m vertical | H7 Hold action after estimated breach |
| Clear physical site | At least 25 m radius | Site selection; no people or obstacles in margin |

The software fence is centered on a verified home position. It acts after a
breach, not before, and its position estimate has error. PX4 documents both
distance/height and polygonal fences and notes the need for vehicle-specific
margin. [[19]](sources.md#source-19)

A literal rectangular box may be uploaded later as a QGroundControl inclusion
polygon, but the first validation uses the simpler cylinder. Polygon support
does not make the boundary collision avoidance.

The range-sensor layer is separate from the geofence. It measures nearby
objects in four narrow body directions and can constrain low-speed Position-mode
movement before contact. It does not know the aircraft's geographic location,
cover diagonal blind sectors, or keep the aircraft inside the test site.

### Indoor bounded volume

The first indoor boundary is a physical net on the sides and overhead. Do not
enable or claim a GNSS bounding box indoors. Do not infer distance from BLE
RSSI.

An electronic indoor box is a separate release requiring:

- A defined local coordinate frame.
- Position accuracy and latency requirements tied to the enclosure size.
- Complete coverage at every attitude and location.
- A height source.
- Drift and outlier detection.
- Tested sensor-loss behavior.
- Enough margin for stopping distance and vehicle size.

UWB, motion capture, or optical flow/range sensing can supply such information,
but no specific system is approved by this version of the design.

## Safety Control Semantics

| Control/event | Meaning | Vehicle response |
|---|---|---|
| Deadman released | Pilot no longer authorizes live movement | Hand marks invalid; gateway stops CRSF; PX4 detects RC loss and Lands |
| ARM pressed | Request to arm, not permission to bypass checks | CH5 requests arm; PX4 prearm checks decide |
| KILL pressed | Continued thrust is the greater immediate hazard | Gateway latches CH8 high with neutral axes/ARM low; aircraft may fall |
| BLE disconnect/stale | Pilot link unavailable | Gateway stops CRSF within 60 ms; PX4 Lands after configured timeout |
| Geofence breach | Estimated position crossed limit | PX4 Hold in initial tests |
| Obstacle in covered direction | Range enters PX4 braking envelope | Collision Prevention limits speed and stops at configured separation |
| Range direction missing | Space is unknown, not clear | Block movement into the uncovered sector |
| Position loss | Position mode can no longer meet its contract | PX4 follows tested position-loss/failsafe degradation |
| Critical battery | Remaining energy is unsafe | PX4 initiates configured Land behavior |

KILL uses the same BLE path and is not independent during radio loss. Radio
loss is handled by silence and PX4. KILL is for an active link with an immediate
propulsion hazard, such as entanglement or movement toward a person at very low
height.

PX4 documents kill as immediate motor output stop and warns that a flying
vehicle will fall. [[21]](sources.md#source-21)

## Team Roles During Powered Tests

| Role | Responsibility |
|---|---|
| Test lead | Owns checklist, calls each transition, can stop test |
| Pilot | Uses gesture controller only; repeats callouts |
| Safety observer | Watches aircraft/site, not laptop; calls ABORT |
| Power operator | Controls battery connection; remains outside prop plane |
| Data operator | Runs QGroundControl/logging; cannot override safety lead |

One person may fill multiple data roles, but pilot and safety observer should be
different people for powered flight. Anyone may call ABORT. After ABORT, do not
resume from the middle of a checklist.

## Universal Stop Conditions

Immediately stop, disarm/kill as appropriate, disconnect battery, and quarantine
the hardware when any of these occurs:

- A person or animal enters the controlled area.
- Unexpected motor starts, wrong motor direction/order, or spontaneous arming.
- C3, H7, GNSS, range hub, or ESC resets under motor load.
- Smoke, odor, swelling, damaged insulation, loose prop/hub, or hot connector.
- Persistent EKF, compass, vibration, GPS, RC, or battery warning.
- Command sign differs from the checklist.
- BLE latency/loss exceeds the accepted envelope.
- Geofence or RC-loss action differs from the recorded configuration.
- A range sensor reports the wrong direction, misses an approved target, or
  marks invalid data as clear.
- Actual propeller touches a guard at any speed.
- Any team member is uncertain about the current state.

## Evidence and Configuration Control

Every test record must identify:

- Date, location, weather/wind for outdoor tests, and team members.
- Body, guard, propeller, motor, ESC, H7, GNSS, range sensors/hub, battery, and
  wiring revisions.
- All-up mass and center of gravity.
- Hand, gateway, and PX4 firmware commit hashes and binary SHA-256 values.
- QGroundControl parameter export.
- ESC settings if modified.
- Battery identifier, cycles, start/end voltage, charged capacity, and
  temperature.
- Pass/fail result, raw logs, plots, photos/video, and anomalies.

Changing propeller geometry/material, motor, battery cell count, ESC firmware,
flight firmware, body stiffness, guards, sensor mounting, radio antenna, or key
safety parameters invalidates the affected downstream tests.

## Phase 0: Design and Inspection

### Gate 0A: mechanical fit

- [ ] Body CAD includes the real ESC 41.6 x 39.4 x 6.3 mm envelope.
- [ ] Body supports 30.5 x 30.5 mm ESC and separate 20 x 20 mm H7 mounts.
- [ ] Battery, H7 USB, receiver plug, and power disconnect remain accessible.
- [ ] Propellers clear guards/body/wiring melt or flex at maximum deflection.
- [ ] GNSS and C3 antennas have clear placement.
- [ ] Finished planning mass is at or below 160 g without collision hardware or
  175 g with it, or the propulsion target is recalculated.
- [ ] Each collision sensor has a rigid body datum and an unobstructed measured
  FoV through the full propeller/guard/body-flex envelope.

### Gate 0B: electrical review

- [ ] Cross-vendor ESC harness has a signed continuity map.
- [ ] No raw VBAT can reach a 5 V or 3.3 V pin.
- [ ] H7 rail is budgeted to conservative 1.5 A.
- [ ] Battery/XT30 wire and capacitor ratings are documented.
- [ ] Every button has a hardware-defined inactive state.
- [ ] BLE, GNSS, and range-hub UART TX/RX directions are cross-checked.
- [ ] The dedicated 3.3 V ToF rail and every `XSHUT` line are continuity-checked.
- [ ] Props are physically stored away from the bench.

Acceptance: independent reviewer signs both checklists with no open high-risk
item.

## Phase 1: Hand Controller

### Sensor and controls

Run at least 30 minutes from the controller battery while logging:

- BNO085 valid-frame rate, checksum/frame errors, and maximum sample age.
- Roll/pitch neutral drift and noise.
- Joystick center/min/max and ADC noise.
- Button transitions and debounce behavior.
- Task watchdogs, heap high-water mark, resets, and battery voltage.

Acceptance:

- No reset, watchdog, unbounded memory growth, or invalid state transition.
- No accepted malformed BNO085 frame.
- Neutral commands remain within the configured deadband.
- Every deadman release invalidates the next command frame.
- KILL latches and cannot be cleared by BLE reconnect or a normal button press.
- ARM cannot assert with deadman released, axes non-neutral, fault active, or
  calibration invalid.

## Phase 2: BLE Link

Perform with no H7 motor power. Use sequence logs on both C3s and, where
possible, an over-the-air BLE capture.

### Functional matrix

| Test | Injection | Required result |
|---|---|---|
| Normal stream | 100 Hz commands for 30 min | No stale event or sequence error |
| Corrupt CRC | Flip one payload bit after serialization | Frame rejected; no CRSF update |
| Wrong length/version | Truncate/alter frame | Rejected |
| Duplicate/rollback | Replay old sequences | Rejected |
| Sequence wrap | 65535 then 0 | Accepted exactly once |
| Hand reboot | Reset while connected | Gateway goes silent; neutral handshake required |
| Aircraft C3 reboot | Reset while active | UART silent by default; no automatic active state |
| Deadman release | Release during continuous stream | Gateway silent within 60 ms |
| Notification stop | Keep BLE connected but stop writes | Gateway silent within 60 ms |
| RF disconnect | Shield/power off hand | Gateway silent within 60 ms unless already in latched kill-only state |
| Reconnect | Restore hand | No arm or movement until neutral handshake |
| Unauthorized peer | Attempt subscription from unbonded device | No command access |
| Pair while armed state simulated | Open commissioning request | Rejected |

### Range and interference matrix

Test 1, 5, 10, 20, and 30 m with propellers removed, first with motors
unpowered and then with motors spinning in a secured test fixture. At each
distance test:

- Controller antenna broadside and edge-on.
- Operator body between controller and aircraft.
- Aircraft yawed through four orientations.
- Quiet 2.4 GHz environment and controlled Wi-Fi traffic.
- At least five minutes per condition inside the intended 10 m volume.

Log negotiated interval, valid/invalid frames, sequence gaps, receive age,
disconnects, retries if visible, and RSSI.

Acceptance for the intended 10 m flight volume:

- At least 99.9% application frames valid over the aggregate test.
- p99 hand-send to gateway-accept latency below 30 ms.
- No receive age above 60 ms without immediate CRSF silence.
- Zero spontaneous disconnects during each five-minute condition.
- Reconnect never restores an armed state.

Results beyond 10 m are characterization, not permission to extend the flight
boundary.

## Phase 3: CRSF and H7 Props-Off

### PX4 installation

- [ ] Exact v1.17.0 source and custom board configuration archived.
- [ ] PX4 bootloader installed with recovery path proven.
- [ ] `crsf_rc` present and `rc_input` removed.
- [ ] `TELEM1` freed from MAVLink and assigned to CRSF.
- [ ] GNSS on GPS1 and external compass detected.
- [ ] Correct airframe geometry selected.
- [ ] Parameter export saved.

### Channel verification

With propellers removed, move one input at a time and record QGroundControl
channel values:

- Roll right increases the configured roll channel only.
- Pitch forward increases/decreases the configured pitch channel in the chosen
  intentional direction only.
- Vertical stick centers exactly at zero vertical intent.
- Yaw stick centers exactly at zero yaw intent.
- ARM, Position, validity, and KILL use only their assigned channels.
- All unused channels remain at defined values.

Acceptance: values are monotonic, full range is calibrated without clipping,
neutral is inside `MAN_DEADZONE`, and no movement input toggles an AUX function.

### Receiver-loss timing

Arm only in a props-off motor test state. Capture gateway GPIO/UART and H7
output/log timestamps. Stop valid BLE notifications without sending a BLE
disconnect.

Acceptance:

- Gateway stops CRSF no later than 60 ms after the last accepted command.
- PX4 declares RC loss and starts Land action no later than 650 ms after the
  last accepted BLE command under the configured timing.
- No previous channel value continues as a valid receiver stream.
- Restored BLE does not automatically clear failsafe into armed control.

### KILL timing

With props removed and motors commanded at low output, press guarded KILL.

Acceptance:

- H7 output stops within 100 ms of button activation.
- KILL remains latched through button release and reconnect; gateway repeats
  only neutral axes, ARM low, and KILL high.
- Clearing KILL requires the documented disarmed reset sequence.

Do not conflate Land timing with motor-stop timing. Land intentionally runs
motors; KILL stops them.

## Phase 4: Sensor and Power Integration

### Static sensor checks

- Calibrate accelerometer, gyro, compass, and level in final installed body.
- Verify reported roll/pitch/yaw direction by rotating the whole body.
- Verify compass orientation and check heading near each motor/battery state.
- Obtain a stable GNSS fix and valid home position outdoors under clear sky.
- Confirm barometer responds to a small controlled height change.

Acceptance: no persistent sensor warning, orientation error, unreasonable
innovation, or compass change caused by connecting the flight battery.

### Collision-sensor static checks

- Start with one VL53L1X and characterize approved target materials indoors and
  in direct sun at 0.1-1.5 m.
- Verify front/right/rear/left identity by moving one padded target at a time.
- Map the mounted FoV edges; confirm props, guards, wires, and body never appear.
- Inject no-return, sensor timeout, one unplugged direction, I2C recovery, hub
  reset, UART corruption, and complete UART silence.
- Verify every invalid/stale case becomes unknown/no data, never maximum range.

Acceptance: each approved target is detected reliably at least 1.2 m away,
p99 sample age is below 75 ms, a failed direction clears within 100 ms, and the
PX4 obstacle map matches the physical direction. Detailed gates are in the
[collision-prevention design](collision-prevention.md).

### Power tests

Use a smoke stopper for first energization, then direct battery only after
normal current is known.

| Test | Required result |
|---|---|
| USB only | H7 boots; no backfeed to battery/ESC |
| 3S battery, motors idle | 5 V rail stable; C3/GNSS remain connected |
| BLE connect/reconnect burst | No 5 V dip or C3/H7 reset |
| Range-hub boot/address cycle | Stable 5 V and 3.3 V ToF rails; all four addresses and directions valid |
| Each motor low-to-mid sweep, props off | No reset, UART error, or abnormal heating |
| Four motors secured, test prop only where enclosure permits | Rails remain valid; GNSS/compass, BLE, range hub, and ToF data remain healthy |

Acceptance: no brownout/reset, no insulation damage, and no component exceeds
its approved temperature.

## Phase 5: One-Motor Propulsion Gate

Mount one F1204 5000KV motor and the actual team propeller in a guarded thrust
stand. Use the intended ESC, 3S battery, inline current/voltage measurement, RPM
measurement, and temperature measurement.

Run incremental commands, allowing inspection between steps. Never stand in the
propeller plane.

Record at each point:

- Command percentage/DShot value.
- Battery and motor voltage.
- Current and electrical power.
- Static thrust.
- RPM.
- Motor, ESC, connector, and battery temperature.
- Vibration/noise and any visible deformation.

Acceptance for an aircraft at or below the 175 g collision-hardware planning
maximum:

- At least 87.5 g static thrust per motor, or half of the measured all-up mass
  if heavier/lighter.
- No operating point above 6 A per motor.
- No unsafe temperature or worsening temperature trend.
- No prop/hub slip, cracking, deformation, guard contact, or excessive
  vibration.
- RPM remains below a documented propeller limit.
- Battery voltage sag leaves sufficient control and landing margin.

If the propeller has no documented safe RPM/material validation, it fails this
gate regardless of thrust.

## Phase 6: Four-Motor Props-Off Gate

- Verify PX4 motor numbering against physical position.
- Verify every motor direction.
- Verify ESC startup with zero command and no spontaneous spin.
- Sweep each motor separately, then all at low output.
- Trigger BLE stale, C3 reset, range-hub reset/silence, H7 reboot, low-battery
  simulation, and KILL.
- Inspect flight logs for sensor clipping, vibration, scheduler load, UART
  errors, and resets.

Acceptance: every output/failure response matches the signed test table. Any
motor-order or direction discrepancy blocks propeller installation.

## Phase 7: Enclosed First Lift

Use the physical net, full guards, a fresh inspected battery, minimum practical
height, and no GNSS geofence claim. Start with the least assisted mode that has
been validated for the enclosure and transition to Altitude/Position behavior
only when its sensor prerequisites are trustworthy.

Sequence:

1. Verify controls and state with battery disconnected.
2. Clear and close enclosure.
3. Connect battery and complete callouts.
4. Arm, raise output only enough to become light on the ground, then disarm.
5. Review log and hardware.
6. Lift 10-20 cm for less than five seconds, land, disarm, inspect.
7. Increase to 0.5 m only after clean logs and repeatable control.
8. Test small roll/pitch/yaw/vertical inputs one axis at a time.
9. Test deadman Land from the lowest stable hover.
10. Test KILL only from a few centimeters above a soft clear surface.

Acceptance: no guard contact, flyaway tendency, severe oscillation, motor
saturation at hover, EKF fault, reset, or uncommanded axis response. Hover
should not require more than about half of available thrust; use measured logs,
not visual judgment alone.

## Phase 8: Outdoor Position and Fence

Requirements before arming:

- Legally permitted site and operation.
- Clear sky and suitable weather/wind for the small craft.
- At least 25 m clear radius from home and no people/obstacles in the margin.
- Valid global position, home, compass, battery, and RC status.
- Position mode selected and verified.
- Fence and safety parameters loaded from the approved export.
- Observer and battery disconnect plan in place.

Progression:

1. Low hover at home; center controls and verify 3D position hold.
2. Move no more than 1 m along each horizontal axis and return.
3. Test vertical command below 1 m.
4. Expand to 3 m, then 5 m operating radius.
5. Test deadman RC loss from a 0.5 m hover.
6. Approach the horizontal fence at very low speed under a special test plan.
7. Record breach point, Hold initiation, maximum radius, and recovery.
8. Approach the vertical fence separately at low climb speed only after the
   horizontal behavior passes.

Acceptance:

- Neutral controls actively brake and hold position as PX4 documents.
  [[20]](sources.md#source-20)
- RC loss produces Land within the measured timing budget.
- Fence breach produces Hold, not Disarm/Terminate or continued outward travel.
- Maximum overshoot remains inside the physically clear site with documented
  margin.
- GNSS/compass/EKF remain valid and motor/ESC/battery temperatures are normal.

Do not intentionally test the fence near the edge of the clear area. Do not use
Return until it has a separate home/altitude/path validation plan.

## Phase 9: Four-Direction Collision Assistance

Do not enable `CP_DIST` in flight until Phases 0-8 and the static collision
sensor checks pass. Load the collision-assisted profile: dominant-axis hand
commands, no translation while yawing, 0.5 m/s maximum horizontal speed,
`CP_DIST=0.6 m`, `CP_DELAY=0.3 s` pending log tuning, `CP_GUIDE_ANG=0`, and
`CP_GO_NO_DATA=0`.

Progression:

1. Reproduce covered and uncovered direction behavior in PX4 SITL.
2. With props off and either valid outdoor GNSS Position mode or the controlled
   HIL position source, carry the aircraft toward a padded target while applying
   the matching command and inspect the fused obstacle map.
3. Repeat after unplugging one sensor. Movement toward that direction must be
   unavailable.
4. Repeat complete hub-silence injection. Horizontal motion must stop and the
   documented Hold transition must occur.
5. Outdoors with valid GNSS Position mode, approach a large soft/breakaway
   target below 0.2 m/s and minimum stable height.
6. Test front, right, rear, and left separately; do not test diagonal motion.
7. Test RC loss while obstacle braking is active. The already validated RC-loss
   behavior must remain effective.
8. Perform ten low-speed approaches per covered direction against an approved
   large matte target.

Acceptance:

- No target contact, false-clear event, direction swap, or oscillatory approach.
- Sensor-to-target separation is at least `CP_DIST`, and the nearest body/prop
  point independently retains the required physical clearance.
- A missing/stale direction is blocked rather than treated as clear.
- Range loss, RC loss, geofence, battery, and KILL actions match the signed
  interaction matrix.
- Final speed and `CP_DELAY` come from the worst measured lighting, target,
  latency, and braking case with margin.

The collision feature remains unavailable indoors as an electronic safety
claim until a separate local-position system is validated. The physical net and
guards remain mandatory in every indoor phase. [[32]](sources.md#source-32)

## Failure Analysis

| Failure | Detection | Response | Residual risk |
|---|---|---|---|
| Hand IMU stale/corrupt | Hand parser age/checksum | Fault frame, no live control | Fault may occur between packets; 100 Hz supervision limits exposure |
| Hand C3 reset | BLE/sequence loss | Gateway CRSF silence | PX4 holds old setpoint until RC timeout, then Lands |
| BLE interference/loss | Gateway receive age | CRSF silence at 60 ms | Vehicle moves during timeout/deceleration; site margin required |
| Unauthorized BLE peer | Secure Connections/bond/allowlist | Reject connection/commands | Commissioning and key-storage implementation must be reviewed |
| Aircraft C3 crash | CRSF stops | PX4 RC-loss Land | A stuck UART stream is addressed by packet age and H7 RC timeout testing |
| H7 reset/fault | Output stops/watchdog/log | ESC receives no valid DShot | Vehicle falls; low altitude/enclosure limits consequence |
| Aircraft IMU failure | PX4 sensor/EKF checks | PX4 failsafe behavior | Single IMU is a single point of failure |
| GNSS/compass loss | EKF/status checks | PX4 position-loss degradation | Position/geofence may be unavailable; clear site remains essential |
| Fence breach | PX4 estimated position | Hold | Action is after breach and depends on position accuracy |
| One range sensor stale/missing | Hub valid mask and PX4 data age | Covered sector becomes unknown and blocked | Thin/transparent targets can still be missed |
| Range hub/I2C/UART loss | Frame age/CRC/status | Horizontal motion stops; Hold after validated complete-loss timeout | Vehicle still moves during sensing/control delay |
| Wrong range orientation | Props-off direction test and installation record | Block release until corrected | An undetected assembly error creates a false obstacle map |
| ESC channel failure high | No complete independent electronic cutoff | KILL/H7 output may not stop failed hardware | Physical enclosure/clear area; inspect ESC; future hardware cutoff if required |
| Battery sag/brownout | Voltage/log/reset checks | Battery failsafe or reset | Incorrect thresholds or severe sag can still cause a fall |
| Propeller/hub failure | Inspection, vibration, RPM gate | Abort/disarm | Custom prop remains a major mechanical risk |

## Release Criteria

The BLE flight prototype is ready for its intended 10 m by 3 m outdoor
operating target only when:

- All gates 0 through 8 pass for base flight; Phase 9 also passes before
  collision assistance is enabled in free flight.
- The issue log has no open critical/high-severity item.
- The exact firmware and parameter artifacts are archived.
- At least ten consecutive enclosed takeoff/hover/land cycles have no anomaly.
- At least five consecutive outdoor low-hover flights have no anomaly before
  any fence approach.
- Battery consumption leaves a demonstrated landing reserve.
- The team has rehearsed RC loss, KILL, site intrusion, battery fire, and
  post-crash handling.

Moving to ExpressLRS requires repeating the receiver, arming, failsafe, and
range portions of this plan. A radio with more range never weakens the H7 fence
or line-of-sight operating procedure.
