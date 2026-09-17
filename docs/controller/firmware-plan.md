# ESP32-S3 controller firmware work packages

**Active target: ESP32-S3, September 16, 2026.** This is an implementation plan,
not implemented or validated production ESP controller firmware. Complete S0–S3 in
[Simantic](simantic-plan.md), repeat the applicable tests on the physical
controller at C0–C7, then integrate the later STM32 virtual drone.

## 1. Reproducible board and firmware baseline — FW-01

Use **ESP32-S3-DevKitC-1-N8R2 / ESP32-S3-WROOM-1-N8R2** as the working reference:
8 MB quad flash and 2 MB quad PSRAM. Confirm module marking and PCB revision
before flashing hardware. ESP-IDF is the initial driver/simulation baseline;
its exact release, Xtensa toolchain, BLE stack and dependencies must be pinned
at S0. An Arduino-ESP32/Adafruit library adapter is an optional later choice
requiring its own compatibility checks on ESP32-S3.

- [ ] Pin ESP-IDF, compiler, build tools, bootloader/partition table, flash mode,
  PSRAM configuration and each used library. The prior ARM compiler does not
  build this Xtensa ESP32-S3 target.
- [ ] Start with a standalone **left-hand** target and one ADC input; create
  right-hand and hub targets after the first acquisition/calibration checks.
- [ ] Put board pin constants, sensor drivers and transport adapters behind
  explicit interfaces. Shared calibration and command logic must be the same
  code tested in the MCU build and host logic tests.
- [ ] Record firmware ELF/binary hashes, simulator loading/boot procedure and a
  reproducible clean-checkout build; later add actual-board flashing/logging.
- [ ] Start physical programming/logging on UART0 through the DevKit's
  USB-to-UART connector. Simantic UART/TCP is a distinct adapter to verify.
  Native USB on GPIO19/20 remains separately qualified if selected.

| Baseline item | Current value / evidence needed |
|---|---|
| Three controller MCUs | ESP32-S3; first physical bench is Freenove WROOM N8R8; confirm each deployed PCB revision |
| Hand inputs | Five flex dividers and external Adafruit #5543 per hand |
| Board configuration | N8R2 simulation reference; N8R8 physical bench, PSRAM disabled in diagnostic firmware |
| Framework/toolchain/BLE version | ESP-IDF baseline; exact versions and stack to pin at S0/S2 |
| Controller firmware | Not implemented by this migration |
| Full ESP schematic and wearable power | Pending; current guide is a bench pin plan |
| Peripheral and BLE support | Use the current ESP32-S3 readiness record; complete driver/stack qualification remains open |
| Host command schema | Proposed below; serialization and timing limits to freeze |

## 2. One-hand acquisition and diagnostics — FW-02

Use the header-verified [bench assignments](build-guide.md#active-pin-assignments):

| Function | LEFT | RIGHT | HUB |
|---|---|---|---|
| Thumb / index / middle / ring / little | GPIO1 / 2 / 4 / 5 / 6 | GPIO1 / 2 / 4 / 5 / 6 | — |
| ADC1 channel order | 0 / 1 / 3 / 4 / 5 | 0 / 1 / 3 / 4 / 5 | — |
| External motion SDA / SCL | GPIO8 / 9 | GPIO8 / 9 | — |
| Hold-to-enable | GPIO7, active low | — | — |
| CALIBRATE | — | — | GPIO7, active low |
| Future battery measurement | GPIO10 reserved, disconnected | GPIO10 reserved, disconnected | Not selected |

GPIO3 is a strapping pin and is deliberately omitted. Reserve native USB
GPIO19/20 and bridge UART GPIO43/44. No onboard motion or battery divider is
assumed.

- [ ] Implement ADC1 one-shot reads with 12-bit results and the pinned release's
  high attenuation setting. Configure each of the five channels explicitly,
  disable GPIO pulls and report raw counts plus calibrated millivolts.
- [ ] Use ESP ADC calibration support and verify its calibration availability
  and conversion path. Arduino's documented ESP32-S3 `ADC_11db` measurement span
  is 0–3100 mV; the selected ESP-IDF release may use a different attenuation enum
  name. Match the selected ESP32-S3 driver and calibration contract.
- [ ] Begin with a provisional 50 ms post-supply settling interval; validate the
  actual circuit. Exercise alternating low/high channels, repeated reads,
  channel identity, saturation, timeouts and scan noise, later under BLE load.
- [ ] Initialize external LSM6DS3TR-C and LIS3MDL at factory I2C addresses 0x6A
  and 0x1C using GPIO8/9, initially 100 kHz. Check exact identity registers,
  initialization writes, data-ready behavior, burst reads and driver timeouts.
  Pin the chosen driver source; a successful address scan is insufficient.
- [ ] Report acceleration/gyro/magnetic units, axes and timestamps. Validate the
  orientation estimator, drift and neutral. Absolute yaw is not established by
  acceleration/gyro alone or an uncalibrated magnetometer.
- [ ] Read GPIO7 using its external pull-up and software debounce; 20 ms stable
  state is an initial candidate to measure. Boot-held ENABLE must remain
  ineffective until released and newly pressed.
- [ ] Log acquisition counter, local monotonic timestamp, five raw/calibrated
  readings, IMU identities/data, button, calibration, power mode and fault
  reasons. Detect near-rail flex input and sensor failures; do not clamp faults
  into valid gestures. Document in-range stuck-input detection limitations.

ADC references: [Espressif ADC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html),
[ESP-IDF one-shot driver](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/adc_oneshot.html).
Motion wiring: [Adafruit #5543 pinouts](https://learn.adafruit.com/adafruit-lsm6ds3tr-c-lis3mdl-precision-9-dof-imu?view=all).

### Power state is explicit

The first bench firmware reports **USB bench power; battery unavailable**. It
must not invent a voltage from floating GPIO10 or apply the former factory A6
formula. A battery field may be absent/invalid according to the frozen schema;
bench mode is allowed only as an explicit configuration, not as a way to bypass
later battery faults.

Wearable operation remains blocked on a reviewed charger, regulator, power path,
switch and external monitor. Once selected, measure battery voltage, local 3V3,
ADC error and reset behavior under ESP/radio load, then set an operating floor
and hysteresis before rail sag can imitate bending. Simulated traces test the
logic, not the physical operating floor. USB coexistence and interruption/reset
behavior require real measurements. RST/EN is not a battery disconnect.

## 3. Calibration and comfortable ranges — FW-03

- [ ] Provide an output-inhibited standalone calibration command for S1. Later,
  hub GPIO7 CALIBRATE starts the same per-hand capture procedure with clear
  success/failure status; calibration never emits valid motion commands.
- [ ] Capture comfortable open/bent distributions and motion neutral. Reject
  insufficient range, unstable capture, sensor faults and disallowed power state.
- [ ] Store versioned profiles tied to device identity, hand side, sensor and
  pin configuration. Test integrity, wrong-side/version rejection and interrupted
  writes through the chosen ESP storage implementation.
- [ ] Bound valid normalized travel, specify filters/deadbands/delay and reject
  implausible readings. Test reboots, missing/corrupt profiles and repeated capture.
- [ ] Require release/new ENABLE after calibration, reboot, reconnect or fault.
  A held button is not recovery consent.

Stop the host control session before coordinated calibration. The hub cannot
infer the host/drone state unless a feedback/acknowledgement path is implemented
and tested. Define that interaction in FW-06.

## 4. Two-hand BLE contract — FW-04

Keep **two ESP32-S3 peripheral hands and one ESP32-S3 central hub**. This migration
does not select Wi-Fi or ESP-NOW. Pin and test the ESP-IDF BLE stack, including
its configured maximum connections, first with one link and then two concurrent
links using the actual project firmware.

| Packet field | Required purpose |
|---|---|
| Version and exact length | Reject incompatible or truncated packets |
| Device identity and hand side | Require exactly one known left and one known right |
| Boot/session identifier | Invalidate continuity across resets |
| Sequence counter | Reject duplicate, replayed and out-of-order packets |
| Acquisition counter and sample timestamp | Detect sampling frozen behind a live communications task |
| Five flex values plus motion data/health | Document representation, units and axes |
| Calibration and power mode/health | Distinguish approved bench mode from qualified wearable operation |
| Left debounced ENABLE | Carry a request; the right cannot assert permission |

- [ ] Freeze serialization, byte order, units/bounds, counter widths/wrap rules,
  bonding/authentication and reconnect behavior; retain decoded packet examples.
- [ ] Use a monotonic **hub-local** receipt time for freshness. Never subtract
  unsynchronized hand timestamps directly from the hub clock.
- [ ] Track acquisition progress as well as arriving packets; bound queues and
  transit age so buffered or repeatedly transmitted old samples cannot stay valid.
- [ ] Require both hands' identity, session, calibration, sensor/power health,
  sequence, sample age and allowed skew together. One invalid hand invalidates
  the whole command.
- [ ] Inject delay/drop bursts, duplicate/wrong-side nodes, corrupt fields,
  stalled acquisition, counter wrap, reset and reconnect. Log causes, counts,
  sample ages and recovery. One link or raw radio traffic cannot pass this stage.

Acquisition/notification rates, maximum age `T_hand`, left/right skew, watchdog
period and fault-to-invalid limits are **unset**. Select numeric test limits
before qualification and freeze them from measured behavior and the accepted
stale-command policy.

## 5. Hub mapping and control state — FW-05

- [ ] Freeze a gesture table with physical motion, axes/signs, neutral/endpoints,
  deadbands, filtering and slew limits. First test one axis at a time with
  command validity inhibited.
- [ ] Bound roll/pitch/yaw to [-1, 1], throttle to [0, 1], and define startup and
  enable transitions. Normalized throttle is not a measured rotor thrust.
- [ ] Implement boot/self-test, service/calibration, waiting, locally permitted,
  fault-latched and recovery-pending states. Every state except permitted
  reports invalid commands; a failed self-test cannot enable control.
- [ ] Permit only fresh calibrated two-hand inputs and a new left press.
  ENABLE release, sensor/power fault, stalled acquisition or link loss invalidates
  the whole command. Reset cannot resurrect the previous permission.
- [ ] Require all conditions valid, release/new press and explicit host restart
  after a stopped/faulted session. Held ENABLE never arms/starts/resumes a drone.

## 6. Host command interface — FW-06

Use one transport-independent command schema for the simulated and physical
controller. Implement UART0 first: physical DevKit USB-to-UART bridge at C6,
explicit simulator UART/TCP adapter at S3. Native USB is a separately tested
alternative, not implied by UART success.

| Field | Proposed constraint |
|---|---|
| Version and length | Framing and compatibility checks |
| Hub session and command sequence | Reset, duplicate and reorder handling |
| Left/right sessions and acquisition progress | Trace a command to fresh input from both hands |
| Roll, pitch, yaw / throttle | [-1, 1] / [0, 1], with frozen signs and meaning |
| Enable, validity and fault reason | Whole-command permission; not drone start/arm |
| Freshness evidence | Explicit receipt-age/progress/transit policy |

- [ ] Freeze encoding, frame boundaries, corruption detection, rates, queue
  bounds and expiry. Keep diagnostic log bytes distinguishable from commands.
- [ ] Independently decode output at a host test sink; capture valid, invalid,
  malformed, late, replayed and unsupported records and explicit assertions.
- [ ] Use receiver-local monotonic expiry and acquisition progress. A live byte
  stream with frozen input must not remain valid. Expiry must still work if a
  frozen/off hub cannot send a final invalid message.
- [ ] Service the watchdog only after required acquisition/communication,
  validation, mapping and bounded output work progress. Test independent stalls;
  a timer-only feed does not establish application health.
- [ ] Implement host stop/reset, any calibration acknowledgement and deliberate
  restart; test link/process/MCU restarts with ENABLE held.
- [ ] Archive source, dependencies, memory/board configuration, schema, profiles,
  fixtures and results. Re-run relevant cases after driver/model changes.

Goal 1 ends at the accepted host command boundary. Goal 2 then feeds the
[STM32 drone simulation](../drone-simulation.md): drone firmware motor/actuator
outputs drive dynamics and rendering. The bridge must not set displayed pose
directly from gestures and label that drone-MCU validation.

## Completion evidence

- [ ] S0–S3 reports identify passed, failed, blocked and substituted-input coverage;
  required peripheral tests remain open until their actual drivers are exercised.
- [ ] C0–C7 required tests in [validation](validation.md) pass on the physical
  prototype against recorded limits; failures are closed and retested.
- [ ] Source, reproducible builds, pinned dependencies, calibration format, BLE
  packet and host command specifications, and diagnostic instructions are saved.
- [ ] The physical controller produces the same frozen command contract accepted
  in simulation, with measured freshness, latency and recovery behavior.
- [ ] Optional trainer results, if any, are recorded separately; Pocket/PPM/ELRS
  and a physical drone are not prerequisites for goal 1 or goal 2.
