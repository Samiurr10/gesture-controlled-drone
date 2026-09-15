# Controller build — start here

The first deliverable is a working, qualified two-hand controller: two Feather
nRF52840 Sense wearables, a Feather nRF52840 Express ground hub, and a verified
trainer connection to the RadioMaster Pocket. Build and qualify the controller
before starting aircraft assembly.

**Current status:** Rev A wiring is documented. Physical assembly, measurements,
custom firmware, the final EdgeTX model, and controller qualification are still
to be completed. A checked document is not evidence that hardware passed a test.

## First bench milestone

Start with **one Sense #4516 and one flex #1070** on USB. A second flex channel is
useful for checking that adjacent ADC readings do not affect one another. Each
channel needs its own 47 kΩ resistor and 100 nF capacitor. Make the first channel
work on A0, record straight/bent voltages and raw readings, and confirm that an
unplugged sensor is rejected before adding the other fingers.

## Build order

| Milestone | Build and demonstrate | Completion evidence |
|---|---|---|
| C0 — Prepare | Confirm actual board revisions, inspect parts, label connectors | Inventory and revision record |
| C1 — One or two fingers | USB-powered left Sense; A0, optionally A1 | Wiring check, meter readings, serial ADC log |
| C2 — Full left hand | All five independent divider circuits; read onboard motion sensors | Five-finger calibration and channel-isolation log |
| C3 — Left wearable | D5 hold-to-enable button, local battery, EN switch, strain relief | Button and battery checks; enable stays inactive through faults/restarts |
| C4 — Right wearable | Second five-finger Sense, its own battery and EN switch | Same analog, motion and power checks; distinct left/right identity |
| C5 — Hub | Express, D6 CALIBRATE, battery/switch, both BLE links | Two-hand data logging; invalid/stale/reconnected data stays disabled |
| C6 — Trainer | Buffer and cable; verify electrical compatibility before closing JP301; validate EdgeTX takeover | Scope captures, radio channel checks, measured fault response |
| C7 — Qualify controller | Complete controller fault, runtime and mechanical checks | Recorded results in the [validation plan](validation.md) |

The root [implementation checklist](../../README.md) tracks the whole project,
including aircraft assembly and flight stages after C7. These milestones are
planned work; none is marked passed by the documentation update.

## Build documents

- [Incremental controller BOM](bom.md) — what each stage needs, with reconciled totals.
- [Step-by-step controller build guide](build-guide.md) — wire and pin schedules.
- [Firmware implementation plan](firmware-plan.md) — work required to make the circuit function.
- [Controller validation plan](validation.md) — acceptance checks and evidence to record.
- [Rev A schematic package](../../hardware/schematics/rev-a/) — complete project drawings and connection data.
- [Full schematic and build guide PDF](../../hardware/schematics/rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf).
- [Every connection, by wire ID](../../hardware/schematics/rev-a/connection-list.md).

## Open controller dependency

The Pocket trainer jack's input limits have not been established for the actual
radio. **Leave JP301 open until electrical compatibility is verified.** The
trainer circuit is a bench design, and the final firmware/radio behavior must
be tested. The first five controller milestones can proceed independently of
that interface. See the [trainer research](../schematic-research-trainer.md)
for evidence, the adapter pin map, and the proposed dropout gate.

## Design baseline

This controller follows the 14 September 2026 `PalmPilot_BOM.pdf` baseline and
the source-linked [hand research](../schematic-research-hands.md). It uses
Feather boards with built-in BLE; the Sense boards also contain the motion
sensors. Earlier XIAO/ESP32-C3/BNO085 designs elsewhere in the repository are
historical and have different pin maps and firmware assumptions.
