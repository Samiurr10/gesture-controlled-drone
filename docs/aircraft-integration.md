# Aircraft integration after controller qualification

This is the later phase of the [full implementation checklist](../README.md).
Complete controller milestone C7 before beginning the main aircraft assembly.
Controller sensing, BLE and hub waveform development can proceed with the
aircraft absent. A props-off receiver/FC fixture is a separate integration step.

## Selected aircraft baseline

| Part | Current selection |
|---|---|
| Flight controller / ESC | Kakute H7 v1.5 full-size + Tekko32 F4 4-in-1 50A AM32, SKU 11091+31102 |
| Propulsion | Four EMAX ECO II 2207 2400KV; selected P3B 5.1 x 3 x 2 props; one 4S 1300mAh XT60 pack |
| Receiver | RadioMaster RP1 V2, matched to Pocket ELRS configuration |
| Navigation | Matek M10Q-5883 GNSS/compass |
| Support | Dronetag BS gen.2; VIFLY Finder 2; supplied 1000uF/35V capacitor; microSD |
| Firmware family | ArduCopter `KakuteH7`; verify exact received sensors and frozen build |

Use the [full schematic](../hardware/schematics/rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf)
pages 3-9 for wiring and pages 21-26 for configuration and checks. The
[aircraft research](schematic-research-aircraft.md) records primary sources.

## A0: received parts and mechanical fit

Record actual board revisions, pack/motor labels, dimensions and mass. Check
stack grommets, motor screw winding clearance, capacitor restraint, wire
passages, battery retention and USB/SD access. Qualify the printed structure and
landing-foot attachments against the finished mass and propulsion loads before
powered flight tests. The BOM's modeled mass and thrust targets are estimates
and development targets, not measured performance.

## A1: power, firmware and manual radio bench

1. Inspect the disconnected XT60 lead and capacitor polarity. Connect motor
   current directly through the ESC large pads.
2. Verify all eight FC/ESC harness contacts by function; use FC ESC1.
3. Bring up FC/ESC electronics through an appropriate current limiter, props
   removed. Measure rails before attaching peripherals one at a time.
4. Record the ArduPilot image and parameters; confirm IMU, barometer and logging.
5. Bind the radio/receiver and prove manual sticks, physical arm/modes and radio
   loss behavior before using the hand controller.

## A2: controller-to-FC integration

| Link | Connection | Configuration boundary |
|---|---|---|
| RP1 CRSF | TX -> R3; RX <- T3; 5V/G | `SERIAL3_PROTOCOL=23`, non-inverted full-duplex |
| Matek GNSS | TX -> R4; RX <- T4; 5V/G | UART4 GPS assignment, separate from receiver |
| Matek compass | CL -> SCL; DA -> SDA | Verify discovered compass and installed orientation |
| ESC telemetry | TLM -> R7 in stack harness | UART7 telemetry, separate from analog CURRENT |

Transfer the controller's qualified radio model, then recheck all channel
endpoints and directions at the FC. Trainer TR5/TR6 health values do not become
aircraft arm or flight-mode channels. Repeat hand, hub, trainer cable and radio
fault tests while observing FC inputs. Record any change in takeover timing or
manual throttle transition.

## A3: motor and power qualification

The drawing uses `FRAME_CLASS=1`, `FRAME_TYPE=12` (BetaFlightX), with motor
functions 33/34/35/36 on outputs 1/2/3/4. Viewed from above: M1 rear-right CW,
M2 front-right CCW, M3 rear-left CCW, M4 front-left CW. Mission Planner motor
test letters are A front-right, B rear-right, C rear-left, D front-left.
Verify every location and direction with propellers removed before installing
matching props.

Read the ESC PCB revision before choosing current-monitor scaling. Calibrate
voltage/current against instruments. Qualify the actual 4S motor/prop combination
using a suitable guarded fixture, then check installed current, temperatures,
vibration and voltage sag. Remove the small electronics smoke stopper for
propulsion tests; it is not a propulsion current path.

## A4: navigation, RF and recovery

Matek's documented separation requirement is 100mm from power wiring, ESCs,
motors and ferrous material. The current compact mounting arrangement does not
establish that clearance. Resolve placement and motor-current interference
before relying on navigation-dependent recovery.

Configure and demonstrate the selected ArduPilot radio-loss, low-battery and
flight-mode behavior on the actual build. Do not import the historical PX4
geofence limits or assume a hand-link loss is visible as ELRS radio loss. Verify
receiver antenna installation, Remote ID setup/broadcast and Finder operation.

## A5: flight progression and final records

Establish controlled manual flight after the electrical, propulsion, mechanical,
navigation and radio checks pass. Only then introduce bounded gesture authority
with an independent radio operator. Extend the envelope incrementally and repeat
affected fault tests after mapping/tuning changes.

Archive the final schematic revision, actual wiring photos, firmware commits,
radio model, calibration profiles, parameters, mass/CG, test logs and measured
operating limits in [implementation records](implementation-records/README.md).
Keep unverified range, endurance, payload and speed claims marked unverified.
