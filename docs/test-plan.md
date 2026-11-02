# Test plan

Tests run in this order. Every simulation step comes before its physical twin,
and the physical twin repeats the same checks on the board.

Rules for every step:

- Each result is **PASS**, **FAIL**, **BLOCKED** or **MOCKED-INPUT-ONLY**.
- Write numeric limits down before the run. A limit marked UNSET has to be set
  first.
- A simulation PASS never passes a physical step, and a physical PASS never
  passes a simulation step.
- Record versions and hashes: `palmpilot.py pack` prints the app and sim ELF
  SHA-256, and the engine version comes from `env.sh`.

## Part A — simulation, on the laptop

Run everything with `sh firmware/tests/run_all.sh`, or run one step with the
command shown. A suite fails if any of its checks fail, or if the UART of any
board shows a firmware panic.

### A0 — Toolchain

```sh
python3 firmware/tools/palmpilot.py run simulation/simantic/hardware-validation/esp32s3-adc firmware/tools/selftest.py
```

Pass: 8/8, with ADC injection reaching all five flex channels.

### A1 — One hand (S1)

`python3 firmware/tools/palmpilot.py run firmware/apps/hand firmware/tests/<suite>.py`

| Suite | What it checks |
|---|---|
| `s1a_acquisition` | Each flex channel lands on its own finger. Calibrated mV. Open and short faults. ENABLE debounce |
| `s1b_calibration` | Capture, plus rejection of too little travel, unstable or inverted captures. Curl normalisation |
| `s1c_control` | State machine, throttle-low interlock, latched faults, stalled acquisition |
| `s1d_motion` | LSM6DS3TR-C and LIS3MDL identity, configuration, data-ready gating, burst decode |
| `s1e_attitude` | Tilt mapping, deadband, saturation; HOLD and PRECISION flagged |
| `s1f_persistence` | NVS save, reload across a reboot, erase, CRC rejection |
| `s1g_packet` | Hand→hub packet framing, counters, bounds, frozen-sampling case |
| `s1h_watchdog` | The watchdog is fed only after real work; starving the loop trips it |

### A2 — Two hands and the hub (S2)

`python3 firmware/tools/palmpilot.py system firmware/tests/<suite>.py`

| Suite | What it checks |
|---|---|
| `s2a_link` | Both hands linked, MTU, 50 Hz from each, no rejected packets |
| `s2b_controller` | Mapping, slew, HOLD, PRECISION, deadman, either-hand faults, latch, hand reboot, hub CALIBRATE. Reset-to-invalid ≤ 150 ms (provisional; see [simulation limits](simulation.md#known-limits-and-open-items)) |

### A3 — Controller into ArduCopter (S3)

| Suite | Command | What it checks |
|---|---|---|
| `s3a_drone` | `palmpilot.py system firmware/tests/s3a_drone.py` | Real hands and hub. ArduCopter reports back the RC channels the hub commanded. When the hub line is cut, overrides stop within 0.2 s and ArduCopter goes to RC failsafe |
| `s3b_replay` | `palmpilot.py system --replay firmware/tests/s3b_replay.py` | Scripted packets from two stand-in hands. Hub command, bridge channels and ArduCopter RC are each compared with an independent expected model (38 checks) |

### A4 — Physics model self-test

```sh
python3 simulation/drone/test_quad_plant.py
```

No simulator. Pass: all checks (27) against closed-form results. Run it after any
change in `simulation/drone/`.

### A5 — Closed-loop gesture flight

```sh
python3 firmware/tools/palmpilot.py system firmware/probes/drone-flight/fly.py
PALMPILOT_AIRFRAME=ardupilot python3 firmware/tools/palmpilot.py system firmware/probes/drone-flight/fly.py
SITL_SENSORS=board tmp/ardupilot-venv/bin/python simulation/drone/sitl_reference.py
```

Real hand and hub firmware fly ArduCopter in AltHold through climb, hold, roll,
pitch, yaw, descend and land. The first run uses our airframe, the second
ArduPilot's. The third replays the same hub commands into native SITL and prints a
per-phase table (climb rate, roll, pitch, speed, yaw rate, altitude) for the two
flights.

Limits: UNSET. Set them before a qualifying run. The last comparison agreed within
about 0.4° and 0.05 m/s. The open estimate drift (1–2.5°) shows up here.

`shake.py`, `tilt.py` and `spin.py` in the same folder are single-axis checks: motor
pulses decoded from the timers against `SERVO_OUTPUT_RAW`, the sign of each axis,
and yaw.

### A6 — In-flight failsafe (to build)

These are planned and not built. Set limits first.

- A hand drops in flight.
- ENABLE is released in flight.
- The hub line is lost in flight.

Each one must stop the overrides. ArduCopter must then reach RC failsafe and land.
That needs a lower `RC_OVERRIDE_TIME` than the default 3 s.

### A7 — Long runs

```sh
python3 firmware/probes/drone-flight/soak.py <seconds> <tag>
python3 firmware/probes/drone-flight/stress.py <seconds> <tag>
```

These check that simulated time keeps advancing and that, at the end, the hub
reports both hands linked and delivering. Use the engine with the stall fix
(renode-infrastructure #340), or the run is a test of the engine bug.

## Part B — physical controller, on the bench

Wiring for every step is in [docs/wiring](wiring/README.md). USB power only. Each
board gets its own cable, and no wire joins two boards. Never connect 5 V or a
battery to an ADC pin. GPIO10 stays unconnected.

| Step | Build | Measure / check | Mirrors |
|---|---|---|---|
| **B0 — Board check** | One bare DevKit | Record module marking, PCB revision, flash/PSRAM and which USB port is the UART bridge. Check the header map against the [pin table](wiring/README.md#pins); a Freenove board needs its own map. Flash `simulation/simantic/hardware-validation/esp32s3-adc` and compare with its committed physical captures | A0 |
| **B1 — One flex** | LEFT thumb on GPIO1: flex, 47 kΩ, 100 nF | Unpowered: continuity and resistance. Powered: 3V3 and node voltage on a meter, calibrated mV from `sample` against the meter, straight and bent readings. Unplug the flex and short it: both must read as faults, never as full travel | S1-A |
| **B2 — Full LEFT hand** | Five flex channels and the #5543 breakout ([one-hand-s1](wiring/README.md#one-hand-on-the-bench-s1-a-and-s1-b)) | Each finger lands on its own channel. Alternate high/low channels to look for coupling. `motion`: IMU identity at 0x6A/0x1C and the mounting axes. `cal extended / curled / neutral / finish / save`, then a reboot restores the profile | S1-A, S1-B, S1-D, S1-E, S1-F |
| **B3 — ENABLE** | Button circuit on GPIO7 | Reads high when released and low when pressed. Debounce. Held at boot has no effect until it is released and pressed again. A new press is refused unless throttle is low | S1-C |
| **B4 — RIGHT hand** | Same as B2, no button | Repeat B1–B2. Its own side identity and calibration | S1 |
| **B5 — Hub and BLE** | Hub with the CALIBRATE button | `status` shows both hands `ready=1` with a rising `accepted` count. Remove one hand's USB: the command goes invalid within the limit set beforehand and stays latched until ENABLE is pressed again. Press CALIBRATE: neutral is captured and output is inhibited while held | S2-A, S2-B |
| **B6 — Hub to laptop** | Hub UART USB port to the laptop | Decode the command lines on the laptop at 115200 baud. Opening the port must not reset the hub (DTR/RTS). Unplugging the hub must expire commands on the laptop side | S3-A expiry |
| **B7 — Controller acceptance** | Everything | Run all three boards for a duration set beforehand, with the fault cases from B5–B6. Save logs, binaries, calibration and the wiring revision | — |

Wearable battery power is out of scope until a reviewed power design exists. The
hands stay on USB.

## Part C — physical controller, simulated drone

The physical hub replaces the simulated controller. Its serial lines feed the same
bridge code (`rc_link`), and the drone runs as ArduCopter SITL in real time
(`simulation/drone/sitl_live.py`). A 3D view shows the airframe's true state. The bring-up, the operator steps and what is still to build are in the
[demo plan](demo.md).

| Step | Check |
|---|---|
| C1 | The demo runner reads the physical hub and ArduCopter reports the commanded RC channels back, as in S3-A |
| C2 | A gesture flight with the physical controller, AltHold, landing |
| C3 | Hand loss, ENABLE release and hub unplug in flight, as in A6 |
| C4 | A repeatable demo: launch procedure, versions, recorded command and motion traces |
