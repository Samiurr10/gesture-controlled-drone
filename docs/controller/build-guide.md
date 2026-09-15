# Controller build guide — Rev A

Build date baseline: 14 September 2026. Begin with one USB-powered hand board,
then expand through the [controller milestones](README.md). Follow the
[BOM](bom.md) for incremental quantities and the
[validation plan](validation.md) for evidence required before marking a stage
complete. This is an assembly plan; it does not claim completed firmware or
hardware tests.

## Drawings to keep beside the bench

The canonical package is [hardware/schematics/rev-a](../../hardware/schematics/rev-a/).
Use the [PDF](../../hardware/schematics/rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf)
with the [wire-ID connection list](../../hardware/schematics/rev-a/connection-list.md).

| Assembly | Drawing |
|---|---|
| Left five-finger circuits, U6 | [06-left-hand.svg](../../hardware/schematics/rev-a/schematic-sheets/06-left-hand.svg) |
| Right five-finger circuits, U7 | [06-right-hand.svg](../../hardware/schematics/rev-a/schematic-sheets/06-right-hand.svg) |
| Battery and EN switches, all three boards | [07-wearable-power.svg](../../hardware/schematics/rev-a/schematic-sheets/07-wearable-power.svg) |
| Left ENABLE and hub CALIBRATE | [07b-buttons.svg](../../hardware/schematics/rev-a/schematic-sheets/07b-buttons.svg) |
| Hub trainer buffer | [09-trainer-buffer.svg](../../hardware/schematics/rev-a/schematic-sheets/09-trainer-buffer.svg) |
| Five-pin IC on six-pad carrier; trainer plug | [09b-buffer-carrier.svg](../../hardware/schematics/rev-a/schematic-sheets/09b-buffer-carrier.svg) |

## C0 — Identify, label and prepare

1. Identify U6 and U7 as **Adafruit Feather nRF52840 Sense #4516**, and U8 as
   **Feather nRF52840 Express #4062**. Record the actual board revisions and
   inspect for damage before attaching wires.
2. Label U6 **LEFT**, U7 **RIGHT**, U8 **HUB**. Use the silkscreen names on the
   boards. `A0` is not GPIO 0; `D5` in these documents is the pad marked `5`.
3. Label each connector's cavity 1 on both halves. This design assigns cavity
   1 to regulated `3V` and cavity 2 to the finger signal. Confirm the actual
   housing orientation with continuity; a generic left/right connector view
   does not establish cavity numbers.
4. Read resistor values and check the first sensor's resistance while moving
   it gently through the intended range. Avoid bending the delicate terminal
   area. Keep the sensing length free to slide when mounted.
5. Disconnect **both USB and battery** before soldering or changing wiring.
   The EN switch disables the regulator but does not isolate USB or battery.

Each wearable has its own regulated supply and ground. BLE carries hand data;
there is no hand-to-hand or hand-to-hub cable in this design.

## C1 — Build the first flex channel on USB

Start with the left thumb on U6 A0. Leave battery installation until C3.

```text
U6 3V ── JL1 cavity 1 ── flex terminal 1
                          [flex sensor]
U6 A0 ── JL1 cavity 2 ── flex terminal 2
  │
  ├── RL1 47 kΩ ── U6 GND
  │
  └── CL1 100 nF ── U6 GND
```

The two sensor terminals are electrically nonpolar. The **connector** is
assigned a consistent polarity so the harness can be traced and checked.
RL1 and CL1 are parallel branches to ground; neither belongs in series with
the A0 signal. Put these two parts next to the Feather ADC connection.

| Wire ID | Connect from | Connect to |
|---|---|---|
| L1a | U6 `3V` | JL1.1, then FL1 terminal 1 |
| L1b | FL1 terminal 2, then JL1.2 | U6 `A0` |
| L1c | U6 `A0` node | RL1 terminal 1 |
| L1d | RL1 terminal 2 | U6 `GND` |
| L1e | U6 `A0` node | CL1 terminal 1 |
| L1f | CL1 terminal 2 | U6 `GND` |

Before powering, verify each intended path and confirm A0 is not shorted to
ground or 3V. Check resistance with power removed; capacitor charging can
affect a momentary resistance/continuity indication. Use the Feather's native
Micro-USB connector to power and program the board.

With power on, measure `3V` to `GND`, then A0 to `GND`. At a 3.300 V supply,
a 25 kΩ sensor would produce approximately 2.154 V; a 100 kΩ sensor would
produce approximately 1.055 V. These are calculated examples, not pass limits
for every flex sensor. Record measured comfortable straight/bent positions.

Develop the ADC bring-up described in the [firmware plan](firmware-plan.md).
The researched Adafruit core requires explicit settings for this circuit:

```cpp
analogReadResolution(12);
analogReference(AR_INTERNAL); // nominal 3.6 V conversion span
analogSampleTime(10);         // 10 microseconds acquisition
```

This fragment only configures sampling; it is not working controller firmware.
Keep A0–A4 pulls disabled and physical ADC voltages between local GND and VDD.
Allow at least 50 ms after power stabilizes before accepting samples for
calibration/control. Validate an unplugged sensor as a fault, rather than a
maximum command. It should pull the **board-side** ADC node toward 0 V through
the 47 kΩ resistor; a broken wire between that node and the MCU can still float.

Optionally build L2 on A1 now. Alternate sampling a low-valued and high-valued
channel to check settling and unintended coupling before expanding to five.

**C1 exit:** continuity documented, local supply and changing ADC values
measured, raw samples logged, unplug behavior checked. Firmware diagnostics
must exist before declaring the serial/ADC part passed.

## C2 — Expand to five fingers on the left hand

Repeat the same complete circuit for each remaining finger. Share U6 `3V`
and U6 `GND` buses; keep every ADC node separate. Each channel still needs its
own resistor and capacitor.

| Finger | U6 pin | JL connector | Signal net | Resistor to L_GND | Capacitor to L_GND |
|---|---|---|---|---|---|
| Thumb | A0 | JL1 | L_A0 | RL1 47 kΩ | CL1 100 nF |
| Index | A1 | JL2 | L_A1 | RL2 47 kΩ | CL2 100 nF |
| Middle | A2 | JL3 | L_A2 | RL3 47 kΩ | CL3 100 nF |
| Ring | A3 | JL4 | L_A3 | RL4 47 kΩ | CL4 100 nF |
| Little | A4 | JL5 | L_A4 | RL5 47 kΩ | CL5 100 nF |

For all JL1–JL5: cavity 1 → U6 `3V`; cavity 2 → the listed ADC node. The
connection list records every branch as L1a–L5f. Net labels `L_THUMB` etc. in
the hand research describe the same finger nodes named `L_A0` etc. in the
connection list.

The Sense motion sensors are already connected inside the board. Do not add
an external IMU cable. Select the library matching the received board
revision, confirm axis direction with deliberate hand movements, and record
mounting orientation. Sensor calibration and gesture mapping are firmware
work, not consequences of completing these wires.

**C2 exit:** all five fingers can be identified independently in the log, each
comfortable range is recorded, and motion readings match known movements.

## C3 — Add left ENABLE, battery and wearable mounting

### Left hold-to-enable button, SW4

```text
U6 3V ── R201 10 kΩ ──┬── U6 D5 (pad 5)
                      ├── C201 100 nF ── U6 GND
                      └── R202 1 kΩ ── SW4 normally-open ── U6 GND
```

| Part/terminal | Endpoint |
|---|---|
| R201.1 | U6 `3V` |
| R201.2, C201.1, R202.1 | U6 `D5` input node |
| C201.2 | U6 `GND` |
| R202.2 | SW4 contact group 1 |
| SW4 contact group 2 | U6 `GND` |

A four-legged tactile switch normally has two internally joined leg pairs.
Identify the separate contact groups with a meter. Do not wire two permanently
connected legs as though pressing would join them.

Use GPIO input mode with the external pull-up. An open button is HIGH;
pressed is approximately 0.30 V and LOW. Software must debounce, require a
release followed by a deliberate press after startup/reconnect, and reject
faulty or stale input. The button grants permission for gestures; it never
serves as the aircraft arm switch. See wire IDs SW4.1–SW4.7.

### Local battery and power switch

| Assembly | Battery positive | Battery negative | Switch conductor 1 | Switch conductor 2 |
|---|---|---|---|---|
| Left, C3 | BT2 original JST + → U6 JST BAT + | BT2 original JST − → U6 JST GND | U6 EN → SWL common | SWL OFF contact → U6 GND |
| Right, C4 | BT3 original JST + → U7 JST BAT + | BT3 original JST − → U7 JST GND | U7 EN → SWR common | SWR OFF contact → U7 GND |
| Hub, C5 | BT4 original JST + → U8 JST BAT + | BT4 original JST − → U8 JST GND | U8 EN → SWH common | SWH OFF contact → U8 GND |

Use one protected #1578 cell per board with its supplied connector. Verify
actual polarity before first insertion. A closed EN-to-GND switch means
**OFF**; open means **ON**. For an SPDT switch, isolate the unused throw and
identify common by continuity. The table corresponds to LP1–LP4, RP1–RP4 and
HP1–HP4 in the connection list.

Charge each Feather through its own Micro-USB circuit, with access for
inspection and off the body. No external charger or external battery-sense
divider is required; A6 is factory battery monitoring. Never connect the
sensor bus to BAT or USB, and never feed a Feather from the aircraft pack.

Mount the board, passive networks and battery so they cannot pull on flex
terminals or exposed joints. Label finger connectors, cover conductors, allow
the sensor strips to slide as fingers bend, and keep USB/battery access.

**C3 exit:** measured button states, battery operation, regulator switch
behavior and strain relief pass; boot/reconnect cannot silently enable control.

## C4 — Build the second hand

Build U7 by repeating the five sensor circuits and its own power circuit.
There is **no added external right-hand button**.

| Finger | U7 pin | JR connector | Signal net | Resistor to R_GND | Capacitor to R_GND |
|---|---|---|---|---|---|
| Thumb | A0 | JR1 | R_A0 | RR1 47 kΩ | CR1 100 nF |
| Index | A1 | JR2 | R_A1 | RR2 47 kΩ | CR2 100 nF |
| Middle | A2 | JR3 | R_A2 | RR3 47 kΩ | CR3 100 nF |
| Ring | A3 | JR4 | R_A3 | RR4 47 kΩ | CR4 100 nF |
| Little | A4 | JR5 | R_A4 | RR5 47 kΩ | CR5 100 nF |

JR1–JR5 cavity 1 → U7 `3V`; cavity 2 → the listed right ADC node. Use R1a–R5f
and RP1–RP4 to check all branches. Repeat analog, motion and battery checks
on this board rather than copying the left hand's calibration numbers.

The left/right physical mounting and logical identity must agree. Keep their
calibration records distinct. A swapped or unidentified hand must not be
accepted by hub firmware.

**C4 exit:** both hands pass their individual tests and report distinct,
verified identities. Their battery circuits and grounds remain independent.

## C5 — Build the hub and validate both BLE links

U8 is the **Express #4062**, with its own BT4 and SWH power circuit from the
table above. Add the external calibration button:

```text
U8 3V ── R203 10 kΩ ──┬── U8 D6 (pad 6)
                      ├── C202 100 nF ── U8 GND
                      └── R204 1 kΩ ── SW5 normally-open ── U8 GND
```

SW5 wiring is identical to SW4 using these new references and U8's local
power/ground. Wire IDs SW5.1–SW5.7 give every branch. The button must only
request calibration while hub output is inhibited. The operator confirms
manual radio authority and, if an aircraft is connected later, that it is
disarmed. The one-way trainer connection does not report radio or aircraft
state to the hub. The firmware plan must implement the coordinated calibration.

### Pin map to preserve in hardware and firmware

| Board | Function | Feather name | Nordic pin |
|---|---|---|---|
| U6 left Sense | ENABLE | D5 | P1.08 |
| U8 Express | PPM waveform to buffer input | D5 | P1.08 |
| U8 Express | Buffer active-low /OE | D9 | P0.26 |
| U8 Express | CALIBRATE | D6 | P0.07 |

No UART or I2C hand-to-hub wires are used. Develop and validate reception from
both hands with the radio disconnected. Log node identity, sequence, packet
age, finger and motion data, calibration, battery status, and ENABLE state.
Power off one hand, reset the hub, and reconnect a hand; each event must
invalidate gesture authority and require deliberate re-enabling.

**C5 exit:** both-hand data flows to the hub, calibration can be performed
while the hands are still, and missing/stale/wrong-hand data is rejected.

## C6 — Assemble and qualify the trainer interface

**Keep JP301's shunt removed.** Complete the hub-side circuit and standalone
measurements before connecting an active trainer signal to the Pocket. The
actual radio's electrical input compatibility remains an open design item.

### U301 connections — use actual IC pin numbers

| Connection | Exact endpoint(s) |
|---|---|
| Supply | U8 `3V` → U301 pin 5 `VCC` |
| Ground | U8 `GND` → U301 pin 3 `GND` |
| Waveform input | U8 `D5` → U301 pin 2 `A` |
| Enable input | U8 `D9` → U301 pin 1 `/OE` |
| R301 10 kΩ | U8 `3V` ↔ U301 pin 1 `/OE` |
| R302 100 kΩ | U301 pin 2 `A` ↔ U8 `GND` |
| C301 100 nF | U301 pin 5 `VCC` ↔ U301 pin 3 `GND`, physically close to U301 |
| Output resistor | U301 pin 4 `Y` → R303 1 kΩ → JP301.1 / TP301 |
| Cable signal | JP301.2 / TP302 → J301 TS **tip** |
| Cable return | U8 `GND` → J301 TS **sleeve** |

All these grounds are hub ground. The cable joins it to the radio signal
ground; the buffer does not provide galvanic isolation. Do not add a PPM
output capacitor or a wire from radio power to the Feather. Use the Pocket's
**DSC trainer port**, not its separate audio jack. H01–H14 in the connection
list are trainer **wire IDs**, distinct from purchasing line IDs in the BOM.

### Adapter trap: U301 pin 5 does not use carrier pad 5

For the selected Adafruit #1230 **six-pad front**, the five-pin IC occupies:

| IC pin | Function | Carrier footprint pad | Carrier header in official CAD |
|---|---|---|---|
| 1 | /OE | 1 | JP2.1 |
| 2 | A | 2 | JP2.2 |
| 3 | GND | 3 | JP2.3 |
| 4 | Y | 4 | JP1.3 |
| 5 | VCC | **6** | JP1.1 |
| No IC leg | Unused | 5 | JP1.2 — leave unused |

The physical carrier has no numbered header labels. Inspect the
[carrier drawing](../../hardware/schematics/rev-a/schematic-sheets/09b-buffer-carrier.svg)
and continuity-test from each actual IC leg to its intended header before
powering. Never assume the adapter pad and five-pin IC numbers match.

### Qualification sequence

1. With JP301 open and radio disconnected, verify hub supply and that R301
   holds `/OE` HIGH through reset. Configure D9 HIGH before output operation;
   LOW enables the buffer. Implement and inspect complete invalid frames
   before any live command mode.
2. Scope TP301 relative to hub GND. Check voltage levels, edge timing,
   startup/reset, malformed frames and stale-data behavior against the
   [firmware plan](firmware-plan.md).
3. Establish the actual Pocket input limits through manufacturer evidence or
   competent circuit-level examination. An idle DMM voltage alone cannot
   prove input tolerance or logic thresholds. Record the evidence.
4. Only after 3.3 V signaling is confirmed compatible, close JP301 with both
   devices off and validate loaded levels at TP302 and received radio
   channels. Lack of decoding does not authorize raising the signal to 5 V.
5. Implement and validate the final EdgeTX model. Keep radio arm/mode sourced
   from its physical controls and measure SE manual takeover. The proposed
   TR5-valid/TR6-heartbeat gate and reconnection latch need actual-radio
   testing; stopping PPM alone can retain trainer values during the radio's
   timeout.

Use the [trainer research](../schematic-research-trainer.md) for the proposed
waveform and authority gate, and the [validation plan](validation.md) for the
full failure matrix. Do not call the controller qualified because channels
move on the radio screen once.

## C7 — Qualify the complete controller, then begin the aircraft

Complete and retain the controller validation record: sensor faults,
calibration, two-hand BLE faults, battery/runtime behavior, reset/reconnect,
PPM faults, radio takeover, and secure wearable construction. Record actual
firmware versions and measured response times. Leave unperformed checks open.

Controller qualification uses the actual Pocket and, where applicable, a
bench receiver or signal-capture setup. End-to-end checks at the aircraft's
flight controller follow aircraft electronics assembly with propellers
removed; they are separate gates in the root implementation checklist.

Once C7 passes, start aircraft assembly and carry forward the proven
controller configuration. Wiring alone does not satisfy this gate: custom
firmware, the EdgeTX model and recorded physical tests are required.

## Pins deliberately left without added wires

- **U6/U7:** A5, AREF, SPI pins, TX/RX, 2/6/9/10/11/12/13 and SDA/SCL have
  no added external connection in this revision. Right U7 D5 is also unused.
- **U8:** A0–A5, AREF, SPI pins, TX/RX, 2/10/11/12/13 and SDA/SCL have no
  added external connection.
- **All three:** BAT and USB header pads need no added lead; native battery
  and USB sockets provide power. A6 is factory battery sensing. Preserve the
  board's internal sensor connections. Do not tie AREF to 3V.

For source-specific pin verification, ADC calculations and charging details,
see [hand/power research](../schematic-research-hands.md) and
[trainer research](../schematic-research-trainer.md).
