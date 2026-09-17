# Historical source documents

**Controller parts also superseded:** ESP32-S3 replaces the original Feather nRF52840 hands and hub. Use the [current BOM](../controller/bom.md) and [migration record](../controller/esp32-migration.md); source PDF pinouts, onboard sensor assumptions and battery circuitry remain historical.

**Scope changed 2026-09-16.** The active deliverable is a physical hand controller driving a virtual drone. First validate the controller in Simantic, then build its physical prototype. The second goal is Simantic drone hardware/microcontroller simulation whose actuator signals drive a mechanical simulation displayed on screen. Physical aircraft construction, flight tests and Pocket/ELRS/trainer procurement are outside the required scope.

Use the [project goals](../../README.md), [current architecture](../architecture.md) and [controller plan](../controller/README.md) for active requirements.

## Original PalmPilot BOM - preserved historical source

[PalmPilot_BOM.pdf](PalmPilot_BOM.pdf) is the unchanged 34-page document supplied by the user on September 14, 2026. Its internal title is *Manta Flow Prototype BOM and Specification Sheet*. PalmPilot and Manta Flow name the same original project. The PDF's physical-aircraft architecture, procurement lists and flight gates have been superseded by the scope above; they are not future phases of the current project.

SHA-256: `e503a87921fdb7e46c1f7dd6f3e43a99a9c226164545777db485c19ab8449217`.

| Pages | Historical content | Current use |
|---|---|---|
| 1-2 | 4S aircraft electronics and propulsion | Provenance only; no aircraft purchase requirement. |
| 5-6 | Two-hand sensor kit, hub and trainer allowance | Hand/hub reference; active quantities are in the [controller BOM](../controller/bom.md). Trainer allowance is excluded. |
| 23-24 | Aircraft interfaces and power budgets | Original physical-system engineering record. |
| 24-28 | Hand circuitry, calibration, BLE and trainer development | Hand/controller reference; the trainer path is historical. |
| 30-31 | Original verification and evidence expectations | Historical gates; follow current controller and simulator acceptance docs. |

The source document contains proposed requirements and estimates. It does not prove that hardware was purchased, firmware exists or a test passed. Its contents are retained without alteration so the source and its checksum remain auditable. Record subsequent requirements in the active docs.

The [archived schematic manifest](../../hardware/schematics/rev-a/README.md) identifies the Rev A drawing package derived from this original BOM.
