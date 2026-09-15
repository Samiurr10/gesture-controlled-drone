# Controller BOM and incremental purchasing

Revision A • 14 September 2026

These are **required build quantities, not an inventory of purchased or received
parts**. Check what is already on hand and what each supplied kit contains
before ordering. Prices, availability and delivery dates are not assessed here.

The build-stage names match the [controller roadmap](README.md). The first
purchase can be limited to C1; complete the first analog channel before
committing to all wearable hardware.

## Main components by stage

| Item | C1 first channel | C2 five left fingers | C3 left wearable | C4 right wearable | C5 hub | C6 trainer | Full controller total |
|---|---:|---:|---:|---:|---:|---:|---:|
| Adafruit Feather nRF52840 Sense #4516 | 1 | — | — | 1 | — | — | **2** |
| Adafruit Feather nRF52840 Express #4062 | — | — | — | — | 1 | — | **1** |
| Adafruit short flex sensor #1070 | 1 | 4 | — | 5 | — | — | **10** |
| Keyed two-contact mating connector pair | 1 | 4 | — | 5 | — | — | **10 pairs** |
| Protected 1S 500 mAh LiPo, Adafruit #1578 | — | — | 1 | 1 | 1 | — | **3** |
| Maintained SPST switch, or SPDT used as SPST | — | — | 1 | 1 | 1 | — | **3** |
| Normally-open momentary pushbutton | — | — | 1 | — | 1 | — | **2** |
| TI SN74LVC1G125DBVR, SOT-23-5 | — | — | — | — | — | 1 | **1** |
| Adafruit #1230 SOT-23 adapter, six-pad front used | — | — | — | — | — | 1 | **1** |
| Two-pin 2.54 mm header + removable shunt, JP301 | — | — | — | — | — | 1 set | **1 set** |
| 3.5 mm male mono TS plug + short shielded signal/return cable | — | — | — | — | — | 1 assembly | **1 assembly** |
| RadioMaster Pocket matching the source BOM, with its specified radio batteries | — | — | — | — | — | 1 set | **1 set** |

An optional second sensor at C1 is **brought forward from C2**: purchase two at
C1 and three more at C2. Bring its resistor, capacitor and connector forward
as well. Total quantities remain unchanged. The three #1578 cells power the
three Feathers; Pocket batteries are separate and must match the radio manual.

## Every passive component

All resistors: 1% tolerance, at least 0.125 W. All 100 nF capacitors: ceramic
X7R, rated at least 10 V. Choose packages suitable for the selected prototype
board; these counts specify electrical parts, not a finished PCB footprint.

| Value | C1 | C2 | C3 | C4 | C5 | C6 | Total | Schematic references |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 47 kΩ resistor | 1 | 4 | — | 5 | — | — | **10** | RL1–RL5, RR1–RR5 |
| 100 nF capacitor | 1 | 4 | 1 | 5 | 1 | 1 | **13** | CL1–CL5, CR1–CR5, C201, C202, C301 |
| 10 kΩ resistor | — | — | 1 | — | 1 | 1 | **3** | R201 left button, R203 hub button, R301 buffer /OE |
| 1 kΩ resistor | — | — | 1 | — | 1 | 1 | **3** | R202 left button, R204 hub button, R303 trainer output |
| 100 kΩ resistor | — | — | — | — | — | 1 | **1** | R302 buffer input pull-down |

The ten flex-channel capacitors do not include the two button filters or the
buffer bypass capacitor. Each pushbutton needs its own 10 kΩ pull-up, 1 kΩ
series resistor and 100 nF filter.

## Prototyping, enclosure and wiring supplies

| Supply | When needed | Quantity/selection basis |
|---|---|---|
| Micro-USB **data** cable and suitable USB host/5 V supply | C1 onward | At least one for first-board programming; add ports/cables for simultaneous three-board work |
| Solderless breadboard and bench jumpers | C1/C2, optional | One reusable bench setup; verify how the selected Feather is supplied with headers |
| Solderable prototype boards, mating headers and mounting hardware | C3/C4/C5 | Three board assemblies; final size depends on wearable/hub enclosure |
| Flexible insulated wire | C1 onward | 28–30 AWG signal/sensor leads; 26 AWG low-voltage power leads where added; cut to actual routing |
| Heat-shrink, cable labels and strain relief | C1 onward | Label every sensor cable and both connector halves; insulate every exposed joint |
| Glove/hand straps and board/battery enclosures | C3/C4 | Two wearable mounting sets with removable batteries and service access |
| Hub enclosure and accessible test points TP301/TP302 | C5/C6 | One hub set; keep JP301 reachable and visibly labeled |
| Optional detachable button connectors | C3/C5 | Up to two extra keyed two-contact pairs; additional to the ten flex pairs |

Keep the batteries' original JST-PH leads and plugs. Do not replace them with
unverified mating plugs. Buy spare passives/connectors if useful for assembly,
but record spare quantities separately from the electrical totals above.

## Tools for the relevant stage

- **C0–C2:** computer, multimeter with resistance/continuity modes, USB data
  cable, fine hand tools, and a way to record serial readings.
- **C3–C5:** soldering iron, suitable solder/flux, cutters, heat-shrink tools,
  and magnification for inspection.
- **C6:** equipment and skill for SOT-23 soldering or a correctly assembled
  adapter; an oscilloscope for voltage/edge measurements. A logic analyzer can
  help with timing, but does not establish analog voltage compatibility.

## Quantities and substitutions that matter

- **No separate IMU or BLE module is required.** Check the received Sense
  revision and use its matching onboard sensor library.
- **No external Feather charger is required.** Each board charges its own
  selected cell through its native USB/JST circuit.
- A generic “74x125” chip is not an automatic substitute for
  **SN74LVC1G125DBVR**; pinout, voltage behavior and power-off behavior matter.
- The selected trainer connector is a **mono TS** plug for the **DSC** port.
  Do not substitute the separate radio audio jack or infer wiring from a TRS
  headphone cable.
- Full-controller quantities exclude the aircraft and its propulsion battery.
  Aircraft procurement/assembly follows controller qualification.

## Source basis

Selections and circuit additions come from the source BOM and the verified
[hand/power research](../schematic-research-hands.md),
[trainer research](../schematic-research-trainer.md), and
[Rev A connection list](../../hardware/schematics/rev-a/connection-list.md).
Those documents retain the manufacturer links and distinguish researched
pinouts, calculated behavior and untested project choices.
