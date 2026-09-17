# ESP32 controller and STM32 drone simulation test record

Copy this file for each test, execution environment and hardware/firmware variant. Keep simulation and physical records separate even when they share a CTRL test ID. Leave measurements blank until observed. Use **NOT RUN**, **PASS**, **FAIL**, **BLOCKED**, **MOCKED-INPUT-ONLY**, or **NOT APPLICABLE (optional extension)**. Use MOCKED-INPUT-ONLY when application inputs bypass the required hardware/peripheral path; record the assertions' actual results separately. Only mark the corresponding checklist after a supported PASS. Store supporting captures and logs in the repository with relative links and avoid committing credentials or BLE bonding secrets.

The active controller is ESP32-S3. Historical nRF results qualify only their
original board/fixture; a matching CTRL ID is not an ESP pass. Start with USB
bench power. Full ESP wiring/power revision and wearable qualification remain
required before reporting a complete physical-controller result.

## Identity and setup

| Field | Recorded value |
|---|---|
| Test ID / title (for example, CTRL-010 or DRONE-002) | |
| Date / operator | |
| Status | NOT RUN |
| Evidence class: host logic / Simantic peripheral / injected application input / physical prototype / integrated virtual drone | |
| Milestone: S0–S3 / C0–C7 / D1–D4 / optional trainer | |
| Models substituted, unsupported or bypassed | |
| Applicable checklist / procedure link | |
| Drawing revision / connection-list revision | |
| Left / right / hub board model, module marking and PCB revision | |
| ESP32-S3 board baseline: N8R2 or recorded alternate; flash / PSRAM size/mode | |
| Pin manifest: flex GPIO1/2/4/5/6; I2C GPIO8/9; left/hub button GPIO7 | |
| External IMU part, PCB revision, addresses and mounting axes | |
| Device identities / hand sides (nonsecret identifiers) | |
| Firmware commit / build target | |
| ESP-IDF or optional Arduino-ESP32 release / Xtensa compiler / library versions | |
| ELF / flash-image hashes, bootloader/partition map and simulator load method | |
| BLE stack/version, maximum connections and actual concurrent peers | |
| ADC unit/channels/resolution/attenuation; calibration method and units | |
| Sensor register-response provider / ADC stimulus version and pin binding | |
| Simantic CLI / SDK / engine version (simulation) | |
| Model identifiers, source commits/hashes and simulation quantum | |
| Input-trace / scenario / assertion revision | |
| Command schema version / host bridge build / transport | |
| Physical UART0 through USB-to-UART connector / simulated UART-TCP / native USB | |
| Calibration version / file | |
| Optional trainer: Pocket model / hardware / EdgeTX version | |
| Optional trainer: radio model export / hash | |
| Power mode: USB bench / reviewed wearable circuit revision | |
| Battery/charger/regulator/monitor identity, measured rail and initial voltage (if fitted) | |
| GPIO10 reserved/disconnected, or approved monitor revision and transfer function | |
| Test instrument / probe / sample rate | |
| Optional trainer: JP301 state / radio connected? | |
| Host test sink or simulated drone MCU endpoint / dynamics configuration | |
| Drone MCU firmware, model and output-decoder versions (D1–D4) | |
| Dynamics / renderer versions, physical model parameters and assumptions | |
| Coordinate frames, units, simulation time step and clock synchronization | |
| Initial state, random seed and synchronized command / actuator / sensor / motion traces | |
| As-built photograph / setup diagram | |

## Procedure and acceptance limits — complete before testing

| Field | Recorded value |
|---|---|
| Preconditions / prior tests required | |
| Exact stimulus or fault injection | |
| Expected state and output | |
| Numeric pass limits / timing origin / endpoint | |
| Test duration / repetitions / worst-case load | |
| Stop condition / restoration procedure | |

## Measurements and evidence

| Measurement / observation | Expected limit | Actual result | Evidence link |
|---|---|---|---|
| | | | |
| | | | |
| | | | |
| | | | |

For active command-loss tests, include failure onset, hand sample age, hub detection, last fresh command, host expiry/invalidation and deliberate recovery. For the optional trainer extension, also include TR5 transition, last TR6 change and radio authority change. State the clock/instrument used; do not subtract unrelated clocks without synchronization. For power tests include the actual source, local `3V3`, ADC values and load; if a battery monitor is fitted, include its circuit revision and measured battery voltage. Never infer battery voltage from an unconnected input. For drone simulation, trace accepted commands through MCU actuator signals, mechanical state, sensor feedback and displayed motion; identify every model approximation or bypass.

## Decision and restoration

| Field | Recorded value |
|---|---|
| Pass / fail / blocked reason | |
| Unresolved limitation / issue link | |
| Corrective change | |
| Retest ID / evidence | |
| Final restored state (power, command session, host/simulator, test wiring; optional JP301/radio model) | |
| Reviewed by / date | |

**Completion rule:** missing evidence or an unmeasured limit is not a PASS. A successful wiring/firmware review does not replace a test. A simulated PASS proves only the declared model/logic coverage and must never mark a physical prototype check passed. Injected application inputs cannot mark a missing peripheral/driver check passed. Optional trainer checks do not gate C7.
