# How the Simantic simulation works

PalmPilot's firmware was developed and tested in [Simantic](https://simantic.com),
a hardware simulator built on Renode, before any board was wired. This document
walks through what actually runs when a simulation test starts, from source code
to a passing check. For the list of models, the physics verification and the known
limits, see [simulation.md](simulation.md); for the order of tests, see
[test-plan.md](test-plan.md).

The short version: **the simulator runs the same binaries that are flashed onto
the boards.** Hands and hub are full ESP32-S3 machines executing the real
bootloader, partition table and application. The drone is a full STM32F405 machine
executing the stock ArduCopter 4.7.1 release. Tests change only the outside world:
voltages on pins, bytes on a sensor bus, a button level.

## 1. From source to a simulated chip

```text
firmware/apps/hand  ──idf.py build──>  bootloader.bin, partition-table.bin, palmpilot_hand.bin
                                          │ esptool merge_bin @ 0x0 / 0x8000 / 0x10000
                                          v
                                       flash.bin (the image esptool writes to a board)
                                          │ esp32s3_build_image.py + ESP32-S3 mask ROM
                                          v
                                       sim.elf  (ROM @ 0x40000000, flash mapped @ 0x30000000,
                                                 entry at the ROM's reset vector)
```

`python3 firmware/tools/palmpilot.py build hand:left` runs the first two steps with
the pinned ESP-IDF v5.5.2. `palmpilot.py sim` adds the third. The only thing that
differs from a physical board is that last wrapper: the simulated chip boots from
the real mask ROM, which then loads the real second-stage bootloader from the
simulated flash, which loads the application. Nothing is linked differently for
simulation.

`hand:left` and `hand:right` are the same source built with a different
`sdkconfig` variant (`CONFIG_PALMPILOT_HAND_LEFT` / `_RIGHT`).

## 2. The machines

`palmpilot.py system <script>` starts four machines in one Renode emulation:

| Machine | Platform | Firmware |
|---|---|---|
| LEFT | ESP32-S3-WROOM-1-N8R2 (stock 0.6.6 platform + RNG model candidate) | `hand:left` |
| RIGHT | same | `hand:right` |
| HUB | same | `hub` |
| DRONE | STM32F405 with a Matek F405-Wing board description (`PALMPILOT_DRONE=f405`, default) or STM32H753 Pixhawk 6X (`h7`) | ArduCopter 4.7.1 |

Each ESP32-S3 gets its own factory MAC in eFuse, so the three chips advertise
different Bluetooth addresses, as three real boards would. The three ESP32-S3
machines share one simulated BLE medium; the hub's NimBLE central finds the two
hands by name, connects, negotiates MTU and subscribes, using the same code path
as on hardware.

`palmpilot.py run <app> <script>` starts a single machine instead (the S1 suites,
one hand). `palmpilot.py drone <script>` starts only the flight controller.

## 3. How a test drives the outside world

A test is a Python script using `firmware/tools/harness.py` (one board) or
`firmware/tools/controller.py` (`ControllerSim`, the whole system). It never
writes into the firmware's memory to fake a reading. Every stimulus enters through
a modelled peripheral and is read by the firmware's own driver:

| Physical input | In simulation | Read by |
|---|---|---|
| A finger bending a flex sensor | A voltage set on the ADC1 channel (Renode `SetVoltage`, microvolts) | ESP-IDF's `esp_adc` one-shot driver and its curve-fitting calibration |
| The hand tilting | Register values served by scripted LSM6DS3TR-C and LIS3MDL I2C devices at 0x6A and 0x1C | The firmware's I2C master driver: identity, configuration, status, burst reads |
| Pressing ENABLE / CALIBRATE | GPIO7 level | GPIO input with debounce |
| Exact BLE packets (S3-B) | The `replay` app, a stand-in hand that sends bytes a script supplies | The hub's real BLE central and packet decoder |
| The drone's own sensors | IMU, barometer and SD card answered from `quad_plant.py`'s state | ArduCopter's own drivers |

When a simulated chip resets, Renode clears injected voltages and GPIO levels;
`harness.ExternalInputs` drives them again, as real sensors would keep their state.

Output is read the way a bench would read it. Every UART character is captured
from Renode's `CharReceived` event (the SDK's `read_uart` duplicates fragments
on this engine, so it is not used for assertions). The hub's UART0 carries one
JSON command line every 20 ms, exactly the line a physical hub prints on USB.

## 4. The drone loop

```text
HUB UART0 line ──> rc_link.py ──> gcs_peer.py ──MAVLink RC_CHANNELS_OVERRIDE──> ArduCopter (F405 UART)
                    (newest command, 100 ms expiry)                                  │
                                                                                     │ motor PWM from the
                                                                                     │ timer compare registers
quad_plant.py  <─────────────────────────────────────────────────────────────────────┘
   │ integrates a rigid-body quad X from the four pulses
   └──> IMU / barometer register values ──> ArduCopter's sensor drivers
```

- `rc_link.py` turns the hub's latest command into RC channel values. An invalid
  command, or no new command for 100 ms of its own clock, stops the overrides, so
  ArduCopter's radio failsafe takes over, as it would with a dead transmitter.
- ArduCopter receives those channels over MAVLink on SERIAL1, exactly as from a
  ground station. Arming and the mode change are separate host actions; ENABLE
  never arms.
- The flight controller's motor outputs are read from the STM32 timer compare
  registers. `quad_plant.py` turns them into thrust and torque, integrates the
  airframe and answers the next sensor read. The drone moves only because the
  flight controller's motor outputs moved it.
- `PALMPILOT_AIRFRAME=ardupilot` swaps in a port of ArduPilot SITL's default quad,
  so the same flight can be compared with native SITL (`sitl_reference.py`).

## 5. What the suites check

`sh firmware/tests/run_all.sh` runs every suite twice through the driver and fails
any run whose UART shows a firmware panic. The suites, in order:

| Suite | Machines | Checks (summary) |
|---|---|---|
| S1-A acquisition | one hand | channel identity, calibrated mV within ±5 mV of the injection, open/short classification, ENABLE debounce |
| S1-B calibration | one hand | capture; travel, stability and inversion rejection; curl normalisation |
| S1-C control | one hand | state machine, throttle-low interlock on ENABLE, latched faults, stalled acquisition |
| S1-D motion | one hand | LSM6DS3TR-C and LIS3MDL identity, configuration, data-ready gating, burst decode |
| S1-E attitude | one hand | tilt mapping, deadband, saturation; HOLD/PRECISION flagged |
| S1-F persistence | one hand | NVS save and reload, restore after reboot, erase, CRC rejection |
| S1-G packet | one hand | hand→hub packet framing, counters, bounds, frozen-sampling case, decoded independently in Python |
| S1-H watchdog | one hand | the watchdog is serviced only after real work, and trips when it stops |
| S2-A link | both hands + hub | BLE link, MTU, 50 Hz, no rejected packets |
| S2-B controller | both hands + hub | mapping, slew, HOLD, PRECISION, deadman, faults, latch, hand reboot, hub CALIBRATE |
| S3-A drone | hands + hub + F405 | ArduCopter reports the RC it was sent; expiry on a cut hub line |
| S3-B replay | stand-in hands + hub + F405 | scripted packets → hub → bridge → ArduCopter, against an independent model |

Acceptance limits are set before a test is run. A suite's PASS is evidence about
the firmware against Simantic's models; it is not a hardware result (see
[bench-bringup.md](bench-bringup.md) for what the physical boards then showed).

## 6. The live 3D view on the emulated F405

`simulation/drone/demo_view.py --drone f405` runs the same emulated F405 and
`quad_plant` behind the browser view used for the laptop demo
(`simulation/drone/f405_live.py`):

```sh
sh -c '. firmware/tools/env.sh && exec "$PALMPILOT_SIM_PYTHON" simulation/drone/demo_view.py --drone f405 --manual'
# with the physical hub instead of the keyboard (needs pyserial on that interpreter):
sh -c '. firmware/tools/env.sh && exec "$PALMPILOT_SIM_PYTHON" simulation/drone/demo_view.py --drone f405 --hub /dev/cu.usbserial-XXXX'
```

One thread owns the simulation and advances it in 20 ms slices as fast as the
host allows; it never waits for wall time except when a slice finishes early.
Position, attitude and motors come from `quad_plant` after each slice. The page's
"× real time" chip divides simulated time by wall time over the last few seconds.

### How fast the emulated F405 runs, and how to read the number

| Measurement | Setup | Result |
|---|---|---|
| `firmware/probes/drone-flight/demo_speed.py`, 2026-11-01 | F405 + quad_plant only, no view, M4, load average 3–4 | flight 1.38–1.59 s wall per simulated second (overall 1.47); first second after arming 6.8–7.1; mode change 2.7–2.8 |
| Live view with a physical hub, 2026-11-17 | the above, plus the view's HTTP server, the hub reader and a browser rendering the 3D scene on the same laptop | 0.78–0.81× real time on the pad before arming; 0.52× shortly after arming |

The live-view figures are not a benchmark of the emulated F405. They include
whatever else the laptop is doing: the Python view server shares the process with
the simulation, and the browser's WebGL rendering competes for the same CPU and
memory bandwidth. The 0.52× reading was also taken during the post-arming slowdown
that `demo_speed.py` measures on its own (6.8–7.1× for one second). Use
`demo_speed.py`, run with no view open, for the emulator's own speed.

Re-run on 2026-11-17 (Apple M4, engine 0.6.6, no view or browser, load average 10.5
falling at the start because firmware builds had just finished):

| Phase | Wall s per simulated s | As "× real time" |
|---|---|---|
| Boot, parameters, reboot, alignment (22.5 s simulated) | 0.76 | 1.31 |
| Standby, disarmed | 1.40 | 0.71 |
| Mode change | 1.24 | 0.81 |
| First second after arming | 6.70 | 0.15 |
| Armed on the ground | 1.66 | 0.60 |
| Flight (climb, hover, roll, pitch, yaw, descend) | 1.37–1.66, overall 1.46 | about 0.68 |

This agrees with 2026-11-01 (1.47 overall in flight). A stick step reached 90% of
the airframe's change in 0.38–0.46 simulated seconds for roll and pitch, which is
0.55–0.67 s on screen at this speed. So the emulated F405 flies at about two thirds
of real time on this laptop, with one slow second after arming. The 0.52× seen in
the live view was most likely that post-arming second averaged in, plus the view's
own load; it was not measured separately.

The laptop demo therefore uses native ArduPilot SITL, which holds 1.00× real time,
and keeps the emulated F405 for the test suites and for side-by-side comparison
(`simulation/drone/compare.py`).

## 7. What simulation cannot tell you

The models are synchronous and noise-free. RF range and interference, ADC noise,
the ESP32-S3 GPIO matrix, power and brown-out, battery, GPS and compass are not
modelled; the BLE medium is lossless. Wiring mistakes, mounting orientation, a
sensor that locks up after a supply glitch, or a pin left floating cannot appear in
simulation. The physical bring-up found several of those; they are recorded in
[bench-bringup.md](bench-bringup.md).
