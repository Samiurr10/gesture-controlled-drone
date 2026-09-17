# ESP32-S3 hand-controller simulation

**ESP32-S3 is the only hand-controller and hub platform.** Start with one hand.
The later virtual drone uses **STM32H743 (STM32H7)**. No physical drone is planned.

| Node | Platform | Scope |
|---|---|---|
| First hand | ESP32-S3-WROOM-1-N8R2 simulation reference | Five flex channels, external motion module, ENABLE and UART diagnostics |
| Physical bench | Freenove ESP32-S3 WROOM, 8 MB flash / 8 MB PSRAM | ADC validation firmware disables PSRAM; record board-specific memory/header settings |
| Second hand and hub | ESP32-S3 | Later two-peer BLE qualification and host command bridge |
| Virtual drone | STM32H743 / KakuteH7 candidate | Later MCU-output-driven dynamics and display |

## Current status

The [September 17 readiness record](../../docs/implementation-records/2026-09-17_hand-controller-readiness.md)
reports working full ESP-IDF boot, ADC with the PR #168 overlay, `esp_timer`,
selected GPIO inputs and UART. GPTimer is a confirmed model gap. Exact motion
fixtures/drivers, NVS, watchdog recovery and ESP BLE remain to be qualified.
Production hand-controller firmware has not yet been implemented.

## Implementation documents

- [Controller firmware and Simantic plan](../../docs/controller/simantic-plan.md)
- [ESP32-S3 platform decision](../../docs/controller/esp32-migration.md)
- [Current BOM](../../docs/controller/bom.md) and [bench wiring](../../docs/controller/build-guide.md)
- [ESP32-S3 and STM32H7 audit reports](capability-audit/README.md)
- [Remaining Simantic requirements](capability-audit/SIMANTIC-REQUESTS.md)
- [Full implementation checklist](../../README.md#full-implementation-checkpoints)
- [Later drone plan](../../docs/drone-simulation.md)

[hardware-inventory.json](hardware-inventory.json), schema 4, contains only the
active controller and virtual-drone plan. It is not an executable configuration
or a complete wiring netlist. The project supplies flex voltages, sensor register
fixtures and fault traces. Simantic must carry them through the actual MCU drivers.
The project also owns the command bridge, dynamics and display.

Reports and concise results are published; temporary harnesses, downloads,
compiled firmware and full bench logs stay local. The original source BOM and
Rev A drawings are archived reference material outside this simulation inventory.
