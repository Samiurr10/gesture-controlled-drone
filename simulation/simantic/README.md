# Simantic scope and inventory

> **September 17 follow-up:** see the [current hand-controller readiness record](../../docs/implementation-records/2026-09-17_hand-controller-readiness.md). ADC passes with corrected clock setup and PR #168; full ESP-IDF boot and `esp_timer` now pass. GPTimer remains a confirmed model gap. Earlier measurements below retain their original scope.

**Priority: simulate the hand controller first, then build its physical prototype.** The second goal is a virtual drone: its hardware and microcontroller run in Simantic, its motor/actuator outputs drive a mechanical/dynamics model, and that model supplies sensor feedback and the drone motion shown on screen. No physical drone is being built.

The active controller is **ESP32-S3** (DevKitC-1 N8R2 bench target), replacing nRF52840. Start with the [migration record](../../docs/controller/esp32-migration.md), [controller Simantic plan](../../docs/controller/simantic-plan.md) and [current feasibility assessment](../../docs/implementation-records/2026-09-16_esp32-full-drone-feasibility.md). The [project checklist](../../README.md#full-implementation-checkpoints) defines S0–S3, C0–C7 and D1–D4. The [drone plan](../../docs/drone-simulation.md) defines the output-to-mechanics boundary.

## Inventory status

[hardware-inventory.json](hardware-inventory.json) is a **planning and historical coverage register, not an executable simulation configuration or procurement list**. Its original 36 assemblies and 142 connection records cover the entire old Rev A physical design. We retain them for traceability while classifying their current relevance.

Schema version 3 adds `active_controller` for the ESP32-S3 nodes, external sensors, GPIO assignments and USB bench power. It reclassifies the old nRF52840 controller assemblies as `historical_controller_reference`. The original 36 assemblies, 142 connections, quantities, pins and power domains remain historical Rev A records; **none is an ESP32 wiring list**. Mixed assemblies need the distinctions below.

| Classification | Current use |
|---|---|
| `historical_controller_reference` | Former Feather circuits; functional roles inform the ESP32 design, but original pins/power do not apply |
| `optional_legacy_interface` | Pocket and PPM trainer buffer; not required to complete the controller |
| `virtual_drone_reference_candidate` | Former aircraft electronics/actuators may inform virtual models; exact hardware fidelity and required models remain to be chosen |
| `historical_aircraft_only` | Receiver, Remote ID and recovery buzzer; no current physical build or mandatory model |
| `mixed_controller_ble_and_historical_elrs` | BLE hand links remain active; ELRS is optional historical work |
| `mixed_wearable_physical_and_drone_virtual` | Build wearable/hub carriers; model drone mechanics. Do not print/build the historical airframe |
| `mixed_controller_bench_and_historical_aircraft_fixture` | Controller USB, tools and appropriate instruments remain relevant; aircraft propulsion fixtures do not |

Use the [controller BOM](../../docs/controller/bom.md) for actual prototype purchases. The historical total passive counts include trainer parts that the current controller does not need. The schema retains the source netlist hash and does not change its circuit assignments.

## What exists and what is pending

The [runtime audit](capability-audit/README.md) provides diagnostic tests, pass/fail evidence and [Simantic requests](capability-audit/SIMANTIC-REQUESTS.md). ESP32 results are kept separate from historical Nordic results. STM32 output/DMA findings remain relevant to the drone candidate. The prior SAADC/TWIM/USB defects describe nRF52840, not the new ESP32 controller. Scripted I²C/SPI and timestamped output observation establish useful integration mechanisms without qualifying every MCU driver.

The inventory itself is not an executable scenario. Production controller firmware, full board/stack validation, a production output adapter, mechanical engine and renderer remain pending. The user owns sensor inputs and the integration application; the audit's tiny scripted bus fixtures only prove attachment paths. Version their later sources/configuration and record model/engine/SDK versions, stimuli and results in [implementation records](../../docs/implementation-records/README.md). Keep credentials and disposable runtime downloads out of the repository.
