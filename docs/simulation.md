# Simulation

Every part of PalmPilot was developed and tested in the
[Simantic](https://simantic.com) simulator before any sensor was wired. The
simulator runs the same binaries that are flashed onto the boards: both gloves,
the hub and the drone's flight controller are full emulated chips executing their
real firmware. Tests change only the outside world: a voltage on a pin, a value on
a sensor bus, a button.

One rule holds throughout: the drone moves only because the simulated flight
controller's motor outputs moved it. Nothing turns a gesture straight into drone
motion.

## What runs

```text
LEFT glove  ESP32-S3 ─┐                              real hand firmware (firmware/apps/hand)
RIGHT glove ESP32-S3 ─┤ BLE (one simulated radio medium)
                      └─> HUB ESP32-S3               real hub firmware (firmware/apps/hub)
                            │ UART, one command line every 20 ms
                            v
                      bridge: rc_link.py + gcs_peer.py (Python, on the host)
                            │ MAVLink RC override every 20 ms
                            v
                      ArduCopter 4.7.1 on an emulated Matek F405-Wing (STM32F405)
                            │ motor PWM, read from the timer registers
                            v
                      quad_plant.py: rigid-body quad
                            │ IMU and barometer readings
                            └─> back into ArduCopter
```

| Piece | What it is | Where |
|---|---|---|
| Gloves and hub | The bootloader, partition table and application that are flashed on the boards. Only the boot wrapper differs (next section) | `firmware/apps/hand`, `firmware/apps/hub` |
| Stand-in glove | A glove's BLE side that sends packets a test script supplies, to give the hub exact inputs | `firmware/apps/replay` |
| Flight controller | ArduCopter 4.7.1, the stock `matekf405-wing` release. A Pixhawk 6X (STM32H753) can be selected instead with `PALMPILOT_DRONE=h7`; it flies the same but simulates about three times slower | `simulation/drone/fetch_arducopter.sh` |
| Bridge | Turns the hub's newest command into RC channels and sends them as a ground station would. It stops sending on an invalid command, or when no new command has arrived for 100 ms | `simulation/drone/rc_link.py`, `gcs_peer.py` |
| Physics | Integrates the airframe from the four motor pulses and answers the flight controller's sensor reads | `simulation/drone/quad_plant.py`, `imu_plant.py`, `baro_plant.py` |

The ESP32-S3 platform is Simantic's stock one, plus one fix not yet in a release:
the random number generator now gives new values after a reset, so a rebooted glove
starts a new session (`simulation/simantic/model-candidates/`).

## From source to a simulated chip

```text
firmware/apps/hand ── idf.py build ──> bootloader.bin, partition-table.bin, palmpilot_hand.bin
                                         │ esptool merge_bin
                                         v
                                      flash.bin   (what esptool writes to a real board)
                                         │ wrapped with the ESP32-S3 mask ROM
                                         v
                                      sim.elf
```

`firmware/tools/palmpilot.py build hand:left` runs the build with the pinned ESP-IDF
v5.5.2. The simulated chip then boots like a real one: the mask ROM loads the real
second-stage bootloader from simulated flash, which loads the application. Nothing
is compiled differently for simulation. `hand:left` and `hand:right` are the same
source with a different `sdkconfig` variant.

`palmpilot.py system <script>` starts all four machines in one simulation; each
ESP32-S3 has its own factory MAC, so the gloves advertise different Bluetooth
addresses and the hub finds, connects to and subscribes to them through the same
NimBLE code as on hardware. `palmpilot.py run <app> <script>` starts one board,
and `palmpilot.py drone <script>` starts only the flight controller.

## How a test drives the inputs

Tests are Python scripts (`firmware/tools/harness.py` for one board,
`firmware/tools/controller.py` for the whole system). They never write a reading
into the firmware's memory; every input goes through a simulated peripheral and is
read by the firmware's own driver.

| On the real device | In simulation | Read by |
|---|---|---|
| A finger bending a flex sensor | A voltage on that ADC channel | ESP-IDF's ADC driver and its calibration; the reading matches the injected voltage within ±5 mV |
| The glove tilting | Register values from scripted LSM6DS3TR-C and LIS3MDL devices at 0x6A and 0x1C | The firmware's I2C driver: identity, configuration, status, burst reads |
| Pressing ENABLE | The GPIO7 level | The GPIO input and its debounce |
| The drone's own sensors | IMU and barometer values computed from the physics state, with datasheet noise | ArduCopter's drivers |

When a simulated chip resets, the simulator clears the injected voltages and pin
levels; the harness sets them again, as real sensors would keep their state.

Outputs are read the way a bench reads them: every character the firmware prints on
its UART is captured. The hub's command line is exactly the line a physical hub
prints over USB.

## The drone loop

- The bridge turns the hub's latest command into RC channels. An invalid command, or
  silence for 100 ms, stops the overrides, and ArduCopter's radio failsafe takes over,
  as with a transmitter that has gone dead.
- ArduCopter receives the channels over MAVLink, as from a ground station. Arming
  and the flight mode are set by the host; ENABLE never arms.
- The motor outputs are read from the STM32 timer registers. `quad_plant.py` (a 1 kg,
  5-inch class quad using ArduPilot's thrust curve) turns them into forces, moves the
  airframe and answers the next sensor read.

ArduCopter settings every run needs, sent by the host: quad X frame
(`FRAME_CLASS=1`, `FRAME_TYPE=1`); arming checks reduced (`ARMING_SKIPCHK=0xFFFFE`),
because the board has no compass or accelerometer calibration; `FLTMODE_CH=0`,
because the bridge holds channel 5; `RC1..4_MIN=1000` and `RC1..4_MAX=2000`, since
the default 1100–1900 inflates stick inputs by about 25%; flight in AltHold.

## Checking the physics

1. Against closed-form results. `python3 simulation/drone/test_quad_plant.py` checks
   free fall with drag, hover, the thrust curve, motor directions, coordinated tilt,
   rate integration, ground contact, terminal climb and air pressure (27 checks, all
   pass), with limits fixed before the first run.
2. Against ArduPilot itself. `PALMPILOT_AIRFRAME=ardupilot` swaps in a port of
   ArduPilot SITL's default quad (`ardupilot_frame.py`, 3 kg). The same gesture flight
   then runs on the emulated F405 and in ArduPilot's native SITL (`sitl_reference.py`,
   replaying the same hub commands). The last comparison agreed within about 0.4° and
   0.05 m/s.

## The tests

`sh firmware/tests/run_all.sh` runs every suite and fails any run in which the
firmware panics. The full order, with commands and pass criteria, is in
[test-plan.md](test-plan.md).

| Suite | Machines | Checks |
|---|---|---|
| S1-A acquisition | one glove | channel identity, voltage within ±5 mV, open and short faults, ENABLE debounce |
| S1-B calibration | one glove | capture; rejection of too little travel, unstable or inverted captures; curl normalisation |
| S1-C control | one glove | ENABLE only grants permission with the throttle low; faults latch; a stalled sampler is caught |
| S1-D motion | one glove | IMU identity, configuration, data-ready gating, burst decode |
| S1-E attitude | one glove | tilt to command, deadband, saturation, HOLD and PRECISION flags |
| S1-F persistence | one glove | calibration saved, restored after a reboot, erased, corrupt data rejected |
| S1-G packet | one glove | the 59-byte packet, decoded independently in Python |
| S1-H watchdog | one glove | the watchdog is fed only after real work, and trips when it stops |
| S2-A link | both gloves + hub | BLE link, MTU, 50 packets/s, nothing rejected |
| S2-B controller | both gloves + hub | mapping, slew, HOLD, PRECISION, ENABLE, faults, a glove rebooting, CALIBRATE |
| S3-A drone | gloves + hub + F405 | ArduCopter reports the RC it was sent; a cut hub line stops it |
| S3-B replay | stand-in gloves + hub + F405 | scripted packets through the hub and bridge, checked against an independent model |
| `fly.py` | gloves + hub + F405 + physics | climb, hover, roll, pitch, yaw, descend and land in AltHold |

Latest run, 2026-11-17: 321 of 322 checks pass. The one miss: after a glove resets,
the hub took 160 ms to mark the command invalid, against a provisional 150 ms limit
(other runs measure 120 ms).

## Speed

On an Apple M4 laptop:

| Setup | Wall time per simulated second |
|---|---|
| Whole system, F405 drone (`fly.py`) | about 3.7 s |
| Whole system, Pixhawk 6X drone | about 11 s |
| F405 alone, in flight (`demo_speed.py`) | 1.46 s (about 0.68× real time) |
| F405 alone, first second after arming | 6.7 s |

That is why the laptop demo flies ArduPilot's native SITL, which runs in real time,
and keeps the emulated F405 for the tests. The emulated F405 can still drive the 3D
view (`demo_view.py --drone f405`); the "real time" figure on that page also counts
the view's own load on the laptop, so use `demo_speed.py` for the emulator's speed.

## Limits

The models are synchronous and noise-free. Not modelled: radio range and
interference (the BLE medium is lossless), ADC noise, the ESP32-S3 pin matrix,
power and brown-outs, battery, GPS and compass. Wiring mistakes, how a sensor is
mounted, a sensor locking up after a supply glitch, or a pin left floating cannot
show up in simulation; the physical bring-up found several of these
([bench-bringup.md](bench-bringup.md)).

Open items:

- After a manoeuvre, ArduCopter's attitude estimate is 1–3° off and the drone drifts
  slowly, on both emulated boards. Native SITL with GPS does not show it. Ruled out so
  far: the physics, sensor signs and scales, dropped samples, noise, parameters, the
  CPU and the flight-controller model.
- With four machines, a rare deadlock in the simulator can stop a run (about 1 run in
  10 on long tests). It is fixed upstream but not in the pinned engine;
  `palmpilot.py` stops a run that idles for 120 s or passes 60 minutes.
- The Pixhawk 6X loses parameter writes on reboot because of an SPI framing issue in
  the simulator; `simulation/drone/fram_peer.py` works around it.

## Toolchain

`firmware/tools/env.sh` sets every path: ESP-IDF v5.5.2 with GCC 14.2.0, the Simantic
engine 0.6.6 and Python SDK 0.4.0, the ESP32-S3 mask ROM, the platform and board
files, and the ArduCopter builds. They live in a gitignored `tmp/` directory and are
not all public yet; [firmware/README.md](../firmware/README.md) has the details.
