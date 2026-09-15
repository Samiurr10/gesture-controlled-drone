# PalmPilot / Gesture-Controlled Drone

**Build the controller first.** Start with one Feather Sense and one flex sensor
on USB, expand to both hands, then build the ground hub and qualify its trainer
connection to the RadioMaster Pocket. Aircraft assembly follows controller
milestone **C7**.

**Current status:** the circuit and build documentation are available. Custom
controller firmware, the final radio model, physical assembly and measured test
results are still pending. Checked documentation does not mean tested hardware.

## Start at the bench

1. Open the [controller build guide](docs/controller/build-guide.md) and
   [incremental parts list](docs/controller/bom.md).
2. Build C1: **U6 3V → flex → A0**, with a **47 kΩ resistor and 100 nF capacitor
   separately from A0 to U6 GND**. Use one Sense #4516; leave its battery for C3.
3. Implement the ADC diagnostic in the [firmware plan](docs/controller/firmware-plan.md),
   measure straight/bent readings and check an unplugged sensor before adding fingers.
4. Save results using the [test record template](docs/controller/test-record-template.md)
   and update the checkpoints below only after their exit checks pass.

Keep the [left-hand drawing](hardware/schematics/rev-a/schematic-sheets/06-left-hand.svg)
beside the bench. The [29-page schematic PDF](hardware/schematics/rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf)
covers every assembly; **pages 10–15 are the hands and pages 16–20 are the hub/trainer**.

## Current system

```text
LEFT:  five flex sensors + onboard motion → Feather Sense ─┐
                                                         ├─ BLE → Feather Express hub
RIGHT: five flex sensors + onboard motion → Feather Sense ┘          │
                                                      buffered PPM trainer cable
                                                                    ↓
                                                         RadioMaster Pocket
                                                                    │
                                                    ELRS — later aircraft phase
                                                                    ↓
                                                     RP1 V2 → Kakute H7 → ESC/motors
```

| Assembly | Selected baseline |
|---|---|
| Hand controllers | Two Adafruit Feather nRF52840 Sense #4516; five flex #1070 each on A0–A4; left D5 ENABLE |
| Ground hub | Feather nRF52840 Express #4062; D6 CALIBRATE; D5 PPM; D9 buffer `/OE` |
| Controller power | Three independent protected 1S #1578 batteries; own-board EN-to-GND OFF switches |
| Trainer | SN74LVC1G125DBVR buffer, JP301 and mono TS cable to Pocket DSC trainer port |
| Later aircraft | Full-size Kakute H7 v1.5 + Tekko32 F4 50A AM32; RP1 V2; 4S propulsion; ArduPilot |

The Pocket retains physical arming, mode selection and manual takeover. Hand-link
loss must disable gesture authority even while the ELRS radio link remains alive.
See the [current architecture](docs/architecture.md) for ownership and interfaces.

**Trainer dependency:** leave **JP301 open** until the actual Pocket's input
voltage compatibility is established. C1–C5 can proceed before that is resolved;
complete controller qualification requires the verified trainer connection.

## Documentation and schematics

| Need | Document |
|---|---|
| Fall 2026 schedule — original baseline | [Gantt workbook](outputs/palmpilot-fall-2026/PalmPilot_Fall_2026_Gantt.xlsx), [schedule status](outputs/palmpilot-fall-2026/README.md) |
| Controller build order | [Controller overview](docs/controller/README.md) |
| Parts for each stage and total quantities | [Controller BOM](docs/controller/bom.md) |
| Every controller pin and assembly step | [Controller build guide](docs/controller/build-guide.md) |
| Firmware, BLE, calibration and trainer implementation | [Firmware work packages](docs/controller/firmware-plan.md) |
| Acceptance checks and fault tests | [Controller validation](docs/controller/validation.md) |
| Record actual results | [Test template](docs/controller/test-record-template.md), [implementation records](docs/implementation-records/README.md) |
| All drawings and PDF page index | [Schematic index](hardware/schematics/README.md) |
| Every connection | [142-record wire list](hardware/schematics/rev-a/connection-list.md), [JSON schedule](hardware/schematics/rev-a/connection-netlist.json) |
| Later aircraft build | [Aircraft integration](docs/aircraft-integration.md) |
| Source BOM and design history | [BOM provenance](docs/reference/README.md), [historical designs](docs/archive/README.md) |

The committed schematic package contains the PDF, 11 editable SVG sheets and the
connection schedule. These are module-level wiring drawings; they are not a PCB
layout or a KiCad electrical-rule-check result. Research is retained for
[hands](docs/schematic-research-hands.md), [trainer](docs/schematic-research-trainer.md)
and [aircraft](docs/schematic-research-aircraft.md).

The Gantt workbook preserves the original August 24–December 11, 2026 plan with
parallel controller and aircraft work. **The controller-first checkpoints below
govern the current build order.** The workbook dates and dependencies need to be
revised before using it as the execution schedule for that order. Record completed
hardware and firmware checkpoints with measured evidence.

## Full implementation checkpoints

Check a hardware or firmware item only when its required tests pass and its
result links to evidence in [implementation records](docs/implementation-records/README.md).
Record the actual hardware revision, firmware commit, configuration, measurements
and failures. Set numeric acceptance limits before testing. All implementation
items below start unchecked because no physical results have been recorded.

### D0 — Documentation baseline

- [x] Preserve the source BOM and label the older H7 Mini / XIAO design as historical.
- [x] Document the current controller-first architecture, incremental BOM and pin-level assembly guide.
- [x] Store the Rev A PDF, 11 SVG drawings and all 142 connection records in the repository.
- [x] Define firmware work packages, controller acceptance tests and a reusable test record.
- [x] Include the Fall 2026 Gantt workbook alongside the build documentation.

### C0 — Prepare the first controller bench

- [ ] Record parts actually on hand, board revisions, connector numbering and component values; start with one Sense and one flex channel.
- [ ] Prepare the meter, soldering/inspection tools and data-capable USB cable; complete unpowered checks (CTRL-001/002).
- [ ] Freeze the board core, libraries and toolchain; compile/upload a basic diagnostic and save the build instructions (FW-01).

### C1 — One working flex input

- [ ] Assemble U6 A0 with its own 47 kΩ / 100 nF network and confirm every connection before USB power.
- [ ] Implement raw ADC logging; measure local 3V and comfortable straight/bent values with the documented ADC settings (CTRL-010).
- [ ] Demonstrate unplugged/shorted-sensor fault detection and settling; optionally add A1 to check channel independence (CTRL-011).

### C2 — Complete left-hand sensing

- [ ] Expand to A0–A4, one independent divider per finger, and verify finger identity and channel interference (CTRL-020).
- [ ] Read the received Sense board's onboard motion sensors and verify mounting axes, neutral and fault reporting (CTRL-021).
- [ ] Implement and validate per-finger calibration, saved profiles, deadband and filtering; reject invalid calibration (CTRL-022; FW-02/03).

### C3 — Left wearable, enable and battery

- [ ] Add the filtered D5 ENABLE button; verify debounce, release-before-enable, startup, release and broken-lead behavior (CTRL-030).
- [ ] Add the protected battery and EN switch; verify polarity, charging access and regulator behavior (CTRL-031).
- [ ] Measure battery/3V/ADC behavior under load; set and test a low-battery operating floor before droop can imitate a gesture (CTRL-032).
- [ ] Mount the sensor strips, board and battery with sliding allowance and strain relief; log full comfortable movement (CTRL-033).

### C4 — Complete the right wearable

- [ ] Build U7's five A0–A4 circuits, independent battery and EN switch; repeat applicable sensing, motion, power and fit checks (CTRL-040).
- [ ] Store a separate right-hand calibration and verify distinct left/right identities; do not copy the left sensor ranges.

### C5 — Ground hub and two-hand BLE

- [ ] Build the Express hub's battery, EN switch and filtered D6 CALIBRATE circuit; reserve D5/D9 for the trainer interface.
- [ ] Implement simultaneous known-hand connections with version, session, sequence and acquisition-progress checks (FW-04; CTRL-041/042).
- [ ] Measure link behavior and freeze sample-age limits; reject stale, duplicated, delayed, disconnected and battery-invalid input from either hand (CTRL-043).
- [ ] Implement calibration only while hub output is inhibited, with operator-confirmed manual/disarmed conditions when applicable (CTRL-050).
- [ ] Freeze and validate gesture-to-AETR mapping, bounds, neutral, throttle enable behavior and whole-command invalidation in USB diagnostics (FW-05; CTRL-051).

### C6 — Trainer interface and radio takeover

- [ ] Assemble the buffer and carrier with JP301 open; verify all five IC pins, adapter pad mapping, passive values and reset-disabled output (CTRL-060).
- [ ] Implement finite eight-slot PPM frames, TR5 validity, fresh-data TR6 heartbeat and watchdog behavior; scope normal, frozen and malformed output (FW-06; CTRL-061/062/063).
- [ ] Establish the actual Pocket input limits and record compatibility before closing JP301; then measure the connected signal and decoded values (CTRL-070/071).
- [ ] Configure and export the Pocket Master/Jack model: AETR trainer mapping, physical arm/mode ownership, SE gate, stream validity, fresh heartbeat and fault latch (FW-07; CTRL-080).
- [ ] Measure manual takeover and throttle mismatch; test every loss/freeze/reconnect case and require deliberate re-enable after faults (CTRL-081/082/083).

### C7 — Controller bench qualification

- [ ] Complete all applicable CTRL-001 through CTRL-084 checks, including a sustained run and repeated takeover tests near the qualified battery limit.
- [ ] Record measured latency, runtime, operating ranges and mechanical fit; correct failures and attach successful retests.
- [ ] Rebuild the tested firmware and archive matching hand identities, calibration profiles, radio model and operating procedure.
- [ ] Demonstrate calibration, enable, manual takeover and fault recovery; accept the complete controller for later FC integration.

**Controller-first gate:** complete C7 before main aircraft assembly. The later
CTRL-090 flight-controller test is part of A2, not a prerequisite for the
controller-only bench milestone.

### A0 — Aircraft parts and mechanical fit

- [ ] Confirm the received stack, motors, propellers, pack and peripherals match the current BOM; record revisions, dimensions and mass.
- [ ] Check stack/connector access, screw clearance, capacitor restraint, wire routes, battery retention and printed structure against the finished loads.

### A1 — Aircraft power and manual radio

- [ ] Wire the main power, capacitor and eight-contact FC/ESC harness from the Rev A drawings; complete unpowered inspection and continuity checks.
- [ ] Bring up electronics with an appropriate current limiter and propellers removed; measure rails before adding peripherals.
- [ ] Install and record the verified ArduPilot build; confirm sensors/logging, bind ELRS and demonstrate manual sticks, physical arm/modes and radio-loss behavior.

### A2 — Controller-to-flight-controller integration

- [ ] Verify RP1 UART3, GPS UART4, compass I²C and ESC telemetry UART7 against actual board labels and parameter assignments.
- [ ] Transfer the qualified controller/radio configuration and verify AETR directions, endpoints and arm/mode ownership at the FC (CTRL-090).
- [ ] Repeat relevant hand, hub, trainer and radio fault tests at the FC input, including manual throttle transition; record downstream response times.

### A3 — Motors and power qualification

- [ ] With propellers removed, verify output assignment, motor positions and rotation for the documented BetaFlightX layout.
- [ ] Confirm ESC revision/current scaling and calibrate battery voltage/current against instruments.
- [ ] Qualify the actual 4S motor/prop combination in a suitable guarded fixture; record current, thrust, temperature, sag and installed vibration before flight.

### A4 — Navigation, RF and recovery

- [ ] Resolve the compass placement/100 mm separation requirement and measure motor-current interference before navigation-dependent operation.
- [ ] Verify installed antennas, receiver behavior, Remote ID configuration/broadcast and Finder operation.
- [ ] Configure and demonstrate the selected ArduPilot radio-loss, low-battery and flight-mode behavior on the actual build.

### A5 — Flight progression and implementation release

- [ ] Complete the preceding electrical, propulsion, mechanical and control checks, then establish controlled manual flight.
- [ ] Introduce bounded gesture authority with an independent radio operator; expand the tested envelope gradually and repeat affected checks after changes.
- [ ] Archive as-built schematics/photos, firmware commits, radio model, calibration, FC parameters, mass/CG, test logs and measured operating limits.
- [ ] Close the remaining implementation issues; keep unmeasured range, endurance, payload and speed claims explicitly unverified.

## Repository maintenance

Current build instructions live in `docs/controller/`; reviewed drawings live in
`hardware/schematics/rev-a/`. Preserve that revision when changing the circuit and
record the change with its affected tests. Earlier documents in `docs/h7-ble/`
remain linked for history and use a different architecture.

Run the package and local-link check from the repository root:

```sh
python3 tools/verify_schematic_package.py --paths README.md docs hardware/schematics
```

This checks connection-table consistency, file presence and drawing structure;
it does not validate electronics or firmware. See the
[regeneration instructions](hardware/schematics/rev-a/README.md#regenerate-for-review)
for producing a new PDF/SVG review set with the portable builder. Generated
`output/` and `tmp/` files are ignored; the reviewed package lives under `hardware/`.
