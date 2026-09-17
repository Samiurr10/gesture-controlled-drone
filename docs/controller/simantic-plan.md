# ESP32-S3 controller firmware and Simantic plan

Active platform snapshot: **September 16, 2026**. The controller working reference
is **ESP32-S3-DevKitC-1-N8R2 / ESP32-S3-WROOM-1-N8R2**, 8 MB flash and 2 MB quad
PSRAM. Start with one left-hand input, then five flex channels, external motion,
calibration and ENABLE. Add the right hand and a third ESP32-S3 BLE central hub
after one-hand acquisition works. This preserves BLE; no Wi-Fi/ESP-NOW migration
is selected.

The physical controller follows S0–S3. The later drone remains an STM32 virtual
system whose motor/actuator outputs drive dynamics and display. No physical
drone is planned. See the [migration](esp32-migration.md) and
[complete-drone feasibility record](../implementation-records/2026-09-16_esp32-full-drone-feasibility.md).

## Current evidence and its scope

**Updated September 17, 2026: enough is available to start one-hand firmware;
the complete controller stack is not yet qualified.**

| Capability | Evidence / remaining work |
|---|---|
| ESP-IDF boot, FreeRTOS, UART diagnostics | Full v5.5.2 application boots through ROM/flash and executes. |
| ADC1 inputs | Local PR #168 overlay passes 960 fresh public-driver reads across ten channels and four attenuation settings. Five planned flex inputs also pass. The PR is not merged into engine 0.5.7. Voltage-curve accuracy remains unqualified. |
| Periodic sampling and timestamps | A new public-API test confirms `esp_timer` callbacks and FreeRTOS task delay work through SYSTIMER. Use this path for initial acquisition; latency/jitter still needs measurement. |
| GPTimer / TIMG | Public driver setup returns success, but alarm callbacks do not occur and `gptimer_get_raw_count` stalls in the unmodified IDF snapshot wait. The selected model only stores main-timer/watchdog registers; this is a model gap. |
| GPIO7 ENABLE | Register-level firmware follows injected levels. Test the public GPIO driver, debounce and held-at-boot behavior in the hand application. |
| External motion sensors | Basic I2C repeated-start/NACK tests pass with a BME280 fixture. Exact LSM6DS3TR-C/LIS3MDL behavior and actual driver initialization/burst reads remain project work and validation. |
| Calibration storage / recovery | NVS persistence and watchdog recovery are not qualified. Successful boot does not prove watchdog behavior. |
| ESP32 BLE / hub | Selected stack and two concurrent hand links remain untested. |

The historical [ESP audit](../../simulation/simantic/capability-audit/esp32s3/README.md)
records earlier diagnostic results. Its ADC probe omitted a SENS clock-enable bit;
the corrected copy passes only with the ADC fix. Do not use that original test
alone to diagnose driver readiness. The [September 17 readiness record](../implementation-records/2026-09-17_hand-controller-readiness.md)
records the full ADC application and physical input tests.

The working simulation uses the N8R2 platform; the physical bench board was
identified as a Freenove ESP32-S3 WROOM with 8 MB flash and 8 MB PSRAM. PSRAM is
disabled in the current validation firmware. Freeze the deployed memory settings
when establishing the hand application's build configuration.

Detailed September 17 rerun and timer-debug scripts/results remain in ignored
`tmp/simantic/rerun-2026-09-17/` and `tmp/simantic/hand-setup-review/`; no bench
artifacts were added back to the ADC PR. STM32 drone work is deferred while the
hand controller is built and qualified.

## Coverage and ownership

| Boundary | Project work | Simulator behavior to establish |
|---|---|---|
| Five flex channels | Generate timestamped voltages for GPIO1/2/4/5/6; include open/short/settling scenarios | Correct ADC1 input binding, conversion/calibration path and used driver semantics |
| External motion | Supply exact #5543 LSM6DS3TR-C/LIS3MDL register responses at 0x6A/0x1C, including motion/fault traces | GPIO8/9 I2C transactions, repeated starts, status/interrupts and timeout behavior |
| ENABLE/CALIBRATE | Drive GPIO7 with edges/bounce/stuck/held conditions | Input routing and driver-visible level/interrupt behavior |
| Firmware execution | Build/pin ESP-IDF targets, manifests and fixtures | Boot/ROM/memory, timers, reset, watchdog and selected storage behavior |
| Two hands plus hub | Implement identity, calibration, BLE packets and fault/recovery logic | Selected ESP BLE stack plus two concurrent peripheral links |
| Host bridge | Implement command parser, expiry, stop/reset and adapters | ESP UART0 transport; native USB separately if selected |
| Future wearable power | Design circuit; supply explicit voltage/fault scenarios | Only modeled effects can be asserted; physical thresholds require measurements |
| Later drone | Own sensor providers, output decoder, physics, feedback and display | STM32 firmware execution and required actual motor/sensor peripheral behavior |

The user/project owns input generation, exact sensor response providers and the
integration bridge. Simantic supplies the execution/peripheral mechanisms that
must carry those inputs through real drivers. A scripted sensor is a valid
explicit fixture; bypassing a missing peripheral by assigning application values
is **MOCKED-INPUT-ONLY**, not driver coverage. Previous SDK attachment tests help
identify APIs but do not automatically validate every ESP bus or GPIO binding.

## Firmware structure

Use ESP-IDF as the initial driver baseline and pin the exact release/toolchain
at S0. Evaluate the intended BLE stack with the real board/engine, then freeze
it. An Arduino-ESP32/Adafruit sensor adapter is optional and needs explicit
version/driver tests. Use ESP32-S3 pin definitions.

```text
S1: one ESP hand
  five ADC1 channels + external I2C motion + GPIO7 ENABLE
    -> acquisition validity -> calibration -> timestamped diagnostics

S2–S3: two ESP BLE hand peripherals -> ESP central hub
  identity / progress / freshness -> whole-command validity -> host test sink

Later STM32 drone
  accepted controller command -> drone MCU motor outputs
    -> dynamics -> sensor feedback and displayed motion
```

## S0 — Establish the ESP driver baseline

- [ ] Pin actual ESP32-S3 model/catalog identifier, source/hash, engine, SDK,
  ESP-IDF/Xtensa versions, N8R2 memory configuration and fixture hashes.
- [ ] Reproduce a minimal executable from a clean checkout; verify loading,
  boot/ROM assumptions and UART diagnostics. Extend the narrow diagnostic to
  actual ESP-IDF boot before declaring framework compatibility.
- [ ] Prove ADC1 one-shot reads through the intended driver: GPIO1 first, then
  channels 0/1/3/4/5. Assert changing calibrated values, completion/timeouts,
  channel selection and rail faults. Use 12-bit high attenuation configured by
  the pinned release; use the selected ESP32-S3 attenuation/calibration contract.
- [ ] Verify GPIO7 input and intended output observations, monotonic timing,
  reset/watchdog and calibration-storage operations through required drivers.
- [ ] Attach the exact external sensor fixture and assert driver initialization,
  identity, I2C write/read/repeated-start, burst data and error/timeout paths.
  A different sensor's successful I2C transaction is useful bus evidence only.
- [ ] Record each missing/incorrect behavior with a minimal deterministic probe;
  separate project implementation needs from engine issues. Keep BLE/host
  qualification in S2/S3 visible without blocking isolated acquisition work.

**Exit:** reproducible driver assertions with explicit model coverage. Current
narrow diagnostic results are partial evidence. Required unimplemented or failing
peripheral behavior remains open; success of a process or host mock is insufficient.

## S1 — One-hand firmware, then fault/calibration tests

- [ ] Freeze [bench GPIO assignments](build-guide.md#active-pin-assignments),
  sensor addresses/units/axes and board memory settings in source manifests.
- [ ] Implement GPIO1 acquisition first, then all five channels, external
  acceleration/gyro/magnetic data, ENABLE debounce and diagnostic records.
- [ ] Use explicit USB bench-power status; leave GPIO10 disconnected. Define a
  future wearable power-state/monitor interface without inventing battery data.
- [ ] Test startup settling, alternating channels, sensor disconnect/near-rail,
  stale acquisition, IMU failures and ENABLE held during boot/fault/recovery.
- [ ] Implement comfortable open/bent capture, motion neutral, filtering,
  calibration integrity/version/identity, rejected captures and deliberate enable.
- [ ] Separate deterministic modeled voltage/sensor assertions from physical
  noise, mounting, magnetic interference and later battery-floor measurements.

**Exit:** actual MCU driver and shared application behavior passes the declared
one-hand cases. Full wearable hardware remains dependent on new power design.

## S2 — Two hands and ESP BLE hub

- [ ] Configure/pin the selected ESP BLE stack, boot one link, then assert two
  simultaneous known hand connections to the central hub in project firmware.
- [ ] Freeze [FW-04](firmware-plan.md)'s packet/session/identity rules and queue
  bounds. Reject duplicate roles, wrong fields and obsolete sessions.
- [ ] Validate acquisition progress, hub-local freshness and hand-to-hand skew;
  unsynchronized remote timestamps must not be subtracted from the hub clock.
- [ ] Inject delay/drop, duplicates/reorder, buffered old samples, frozen
  acquisition, reset/wrap, wrong identity and reconnect with ENABLE held.
- [ ] Freeze mapped axes/throttle and boot/calibration/waiting/permitted/fault/
  recovery states. Neither hand failure nor a held button may preserve validity.

**Exit:** actual ESP BLE/driver/application coverage of the two-link topology and
whole-command invalidation. A raw-radio pass or one example link does not pass S2.

## S3 — Host command output and regression

- [ ] Implement and freeze [FW-06](firmware-plan.md)'s framing/schema, bounds,
  sessions, acquisition progress, validity and expiry policy.
- [ ] Send ESP UART0 bytes to a host test sink through the named Simantic adapter;
  independently decode and assert valid/invalid commands. Native USB requires
  its own model/driver test if selected. Physical USB-to-UART follows at C6.
- [ ] Run three ESP instances with deterministic normal/fault traces. Freeze
  acquisition, BLE, mapping and output separately; test watchdog/reset, host
  process loss, delayed/replayed data and independent receiver expiry.
- [ ] Assert explicit stop/reset and deliberate recovery. A held ENABLE cannot
  start/resume the later virtual drone.
- [ ] Archive versions, hashes, time quantum, fixtures, limits, decoded traces
  and assertions. Keep PASS, FAIL, BLOCKED and MOCKED-INPUT-ONLY distinct.

**Exit:** repeatable controller output behavior at the sink with the required
peripheral paths exercised. Full project qualification cannot be inferred from
narrow boot/GPIO/I2C results.

## C0–C7 — Build and qualify the physical controller

Follow [build guide](build-guide.md) and [validation](validation.md). First verify
the delivered DevKit headers and one USB-powered flex input, then five inputs,
external motion and ENABLE. Complete the ESP schematic/netlist and reviewed
wearable power design before permanent wearable assembly and C3 acceptance.
Repeat on RIGHT; add the USB-powered ESP hub and physical serial bridge. Freeze
operating limits from actual measurements and rerun related simulation cases.

C7 establishes the physical controller command boundary. Optional historical
Pocket/PPM wiring is outside the active controller assignments and milestones.

## Later — STM32 drone, dynamics and display

Follow [drone simulation](../drone-simulation.md) and the
[full-drone feasibility record](../implementation-records/2026-09-16_esp32-full-drone-feasibility.md).
The controller remains the delivery priority while authorized drone feasibility
probes may proceed independently. Feed commands to the STM32 firmware, decode
its motor/actuator outputs, advance dynamics and return sensor feedback on a
documented timeline. The display consumes that state. Do not bypass the MCU by
animating gesture-derived pose. Missing flight-controller startup, motor routing,
DMA or feedback behavior remains a separate unresolved dependency.

## Reference links

- [Espressif DevKitC-1 v1.0 board/ordering reference](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.0.html).
- [Espressif DevKitC-1 v1.1 header reference](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html).
- [ESP32-S3 ADC API and calibrated millivolts](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html).
- [Selected Adafruit motion module](https://www.adafruit.com/product/5543).
- [Official Simantic Python SDK](https://github.com/simantic-dev/pippy).
- [ESP32-S3 / STM32H7 audit](../../simulation/simantic/capability-audit/README.md), retained with its original platform limitations.

The next required firmware milestone is still **S0 for ESP32-S3**. No S0–S3 or
C0–C7 checkbox is completed merely by selecting the replacement board.
