# Historical schematic archive

**Scope changed 2026-09-16.** Only the hand controller will be physically built. The order is: validate the controller in Simantic, build its physical prototype, then model the drone hardware/microcontroller in Simantic and use its actuator outputs to drive an on-screen mechanical simulation. There is no physical drone construction or flight phase. Pocket, ELRS and trainer hardware are not required.

The [project goals](../../README.md) and [current architecture](../../docs/architecture.md) define the active scope. Start implementation with the [controller simulation plan](../../docs/controller/simantic-plan.md), then use the [controller build guide](../../docs/controller/build-guide.md).

## Archived Rev A package

**ESP32 migration:** the hand/hub drawings are now superseded too. The active controller uses ESP32-S3 with external IMUs and a new power design. Do not use Rev A A0–A4, D5/D6, BAT or EN wiring on ESP32. The [current bench guide](../../docs/controller/build-guide.md) and [migration checkpoints](../../docs/controller/esp32-migration.md) define the replacement; a complete ESP32 wearable schematic has not yet been published.

[Rev A](rev-a/README.md), researched on September 14, 2026, records the former full-system physical-aircraft plan derived from the [original BOM](../../docs/reference/README.md). Its circuit records remain historical engineering references. Its aircraft build steps, trainer qualification gates, flight tests and purchasing lists are not later phases of this project.

- [Archived full schematic and build guide - 29-page PDF](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf).
- [Archived 142 connection records](rev-a/connection-list.md).
- [Revision contents and provenance](rev-a/README.md).
- [Historical nRF52840 hand wiring research](../../docs/schematic-research-hands.md).

## Drawing reference index

The table locates historical content; it is not an implementation sequence. PDF page numbers are the printed page numbers.

| Reference content | Archived PDF pages | Archived editable sheets | Use in the active project |
|---|---|---|---|
| Original system and parts | [1-2](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=1) | [System overview](rev-a/schematic-sheets/00-system-overview.svg) | History only; superseded system route. |
| Hand circuits, power and buttons | [10-15](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=10) | [Left hand](rev-a/schematic-sheets/06-left-hand.svg), [right hand](rev-a/schematic-sheets/06-right-hand.svg), [power](rev-a/schematic-sheets/07-wearable-power.svg), [buttons](rev-a/schematic-sheets/07b-buttons.svg) | Historical nRF52840 wiring; does not apply to ESP32 pins, sensors or power. |
| Trainer prototype | [16-20](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=16) | [Trainer buffer](rev-a/schematic-sheets/09-trainer-buffer.svg), [carrier](rev-a/schematic-sheets/09b-buffer-carrier.svg) | Historical, outside required scope. |
| Physical aircraft | [3-9](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=3) | [Power](rev-a/schematic-sheets/02-aircraft-power.svg), [peripherals](rev-a/schematic-sheets/03-aircraft-peripherals.svg), [stack connectors](rev-a/schematic-sheets/04-stack-connectors.svg), [motors](rev-a/schematic-sheets/05-motor-wiring.svg) | Historical; does not mandate physical parts or select Simantic's virtual hardware. |
| Original implementation and acceptance | [21-26](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=21) | Tables in archived PDF | Original physical-system gates are not active project gates. |
| Source evidence | [27-29](rev-a/PalmPilot_Full_Schematic_and_Build_Guide.pdf#page=27) | [Source register](rev-a/connection-list.md#sources), [figure provenance](sources/README.md) | Research evidence, not completed tests. |

## Formats and historical regeneration

These are module-level wiring drawings. Their JSON is a connection schedule, not a KiCad project, PCB netlist or electrical-rule-check result. No physical validation is implied.

The [builder](../../tools/build_palmpilot_schematic.py) reproduces this historical package; it does not generate the new drone simulation. Its [dependencies](../../tools/requirements-schematics.txt) and [review regeneration instructions](rev-a/README.md#regenerate-for-review) are retained for maintenance. New architecture and controller requirements belong in the active docs, not in the archived connection data.
