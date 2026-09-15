# PalmPilot schematics — build the controller first

The current circuit is **Rev A**, based on the [34-page PalmPilot BOM](../../docs/reference/PalmPilot_BOM.pdf). Start with the two hand controllers, then the ground hub. The aircraft is a later implementation phase.

## Start here

- [Controller build guide](../../docs/controller/build-guide.md): parts, assembly order and bench checkpoints.
- [Full schematic and build guide — 29-page PDF](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf).
- [All 142 connection records](rev-a/connection-list.md): source pin, destination pin, wire and notes.
- [Revision contents and provenance](rev-a/README.md).
- [Full implementation checklist](../../README.md).

## Controller-first drawing index

Page numbers below are the PDF's printed page numbers. Open the PDF directly if your viewer does not support page links.

| Build stage | PDF pages | Editable schematic sheets |
|---|---|---|
| Confirm exact parts and system architecture | [1–2](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=1) | [System overview](rev-a/schematic-sheets/00-system-overview.svg) |
| **First: left and right hand controllers** | [10–15](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=10): both five-finger circuits, power, buttons, assembly and calibration | [Left hand](rev-a/schematic-sheets/06-left-hand.svg), [right hand](rev-a/schematic-sheets/06-right-hand.svg), [wearable/hub power](rev-a/schematic-sheets/07-wearable-power.svg), [filtered buttons](rev-a/schematic-sheets/07b-buttons.svg) |
| **Second: ground hub and trainer prototype** | [16–20](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=16): buffer, every connection, carrier, waveform and qualification gate | [Trainer buffer](rev-a/schematic-sheets/09-trainer-buffer.svg), [carrier and plug](rev-a/schematic-sheets/09b-buffer-carrier.svg) |
| Later: aircraft | [3–9](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=3): power, peripherals, connectors, motors and physical board locator | [Aircraft power](rev-a/schematic-sheets/02-aircraft-power.svg), [peripherals](rev-a/schematic-sheets/03-aircraft-peripherals.svg), [stack connectors](rev-a/schematic-sheets/04-stack-connectors.svg), [motors](rev-a/schematic-sheets/05-motor-wiring.svg) |
| Implementation and acceptance | [21–26](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=21): flight-controller settings, power measurements, extra parts, unused pins, assembly and test records | Use the page tables and repository checklist. |
| Evidence | [27–29](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=27) | [Research sources](rev-a/connection-list.md#sources), [local image provenance](sources/README.md) |

**Trainer status:** JP301 must remain open until the received Pocket's input compatibility has been established. Firmware, radio configuration and actual dropout/recovery behavior still require implementation and measurement. Completing the documentation does not complete these tests.

## File formats and regeneration

The drawings are module-level wiring schematics and editable SVGs. The JSON is a connection schedule, **not a KiCad project, PCB netlist or electrical-rule-check result**. Use the exact received board revision and verify connector orientation before wiring.

The original PDF is preserved in [rev-a](rev-a/README.md). The [builder](../../tools/build_palmpilot_schematic.py) and its [dependencies](../../tools/requirements-schematics.txt) are checked in; generated review output defaults to `output/pdf/`. See [regeneration instructions](rev-a/README.md#regenerate-for-review).
