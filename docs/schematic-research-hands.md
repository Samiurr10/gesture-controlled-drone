# Historical nRF52840 hand nodes and hub power research

> **Controller replaced by ESP32-S3 on September 16, 2026.** All board selections, ADC settings, built-in sensor assumptions, Feather pins and battery/EN wiring below describe the former design. Use the [ESP32 migration record](controller/esp32-migration.md), [current BOM](controller/bom.md) and [build guide](controller/build-guide.md). Historical wording such as “active” or “retained” below is superseded by this notice.

> **Scope updated 2026-09-16.** The physical deliverable is the hand controller. First simulate and validate it in Simantic, then build the controller prototype. The second goal uses Simantic to model drone hardware/microcontroller outputs and feed those signals into an on-screen mechanical simulation. Physical drone construction and flight tests are outside scope. Pocket/ELRS/trainer hardware is not required.
>
> Follow the [project goals](../README.md), [current architecture](architecture.md), [controller simulation plan](controller/simantic-plan.md) and [controller build guide](controller/build-guide.md). This September 14 electrical research supports the retained hand/hub circuits; the original full-system Rev A drawings are [archived](../hardware/schematics/rev-a/README.md). Sources and calculations below are research evidence, not completed simulation or physical validation.

Research date: 2026-09-14; scope annotations updated 2026-09-16. The original reference was the September 14 BOM. Its aircraft and trainer sections no longer define required purchases. The active [controller BOM](controller/bom.md) determines prototype quantities and scope.

## Retained controller drawing inputs

Use one Adafruit Feather nRF52840 Sense #4516 per hand; use Feather nRF52840 Express #4062 at the hub. Current Sense Rev C uses LSM6DS3TR-C acceleration/gyro and LIS3MDL magnetic sensing. The board already connects and powers these sensors. No external IMU, I2C cable, extra BLE module or charger board is needed. Check the delivered board revision and use its matching sensor library. [Adafruit hardware/revision record](https://github.com/adafruit/Adafruit-Feather-nRF52840-Sense-PCB), [Sense downloads](https://learn.adafruit.com/adafruit-feather-sense/downloads).

### Exact pin allocation

The finger assignment is this project's design choice; the silkscreen-to-MCU mapping is verified against Adafruit's board variant. Use the silkscreen/Arduino names when building and programming. A0 does **not** mean GPIO 0. [Sense variant](https://raw.githubusercontent.com/adafruit/Adafruit_nRF52_Arduino/master/variants/feather_nrf52840_sense/variant.cpp).

| Function | Left board pin | Right board pin | Nordic pin | Arduino number |
|---|---|---|---|---:|
| Thumb flex | A0 | A0 | P0.04 | 14 |
| Index flex | A1 | A1 | P0.05 | 15 |
| Middle flex | A2 | A2 | P0.30 | 16 |
| Ring flex | A3 | A3 | P0.28 | 17 |
| Little flex | A4 | A4 | P0.02 | 18 |
| External hold-to-enable button | D5 (silkscreen 5) | No connection | P1.08 | 5 |
| Spare analog input | A5, no connection | A5, no connection | P0.03 | 19 |
| Battery voltage monitor | Factory connection, A6 | Factory connection, A6 | P0.29 | 20 |

Use exactly two external H06 buttons: one normally-open ENABLE button on the left wearable, one normally-open CALIBRATE button on the hub. This lets both hands remain still during hub-initiated calibration. Right hand has no added external button. The on-board user/reset buttons remain their usual service controls.

| Hub function | Express silkscreen/code | Nordic pin |
|---|---|---|
| External calibration button | 6 / D6 | P0.07 |
| Former trainer waveform; unused in current controller scope | 5 / D5 | P1.08 |
| Former trainer buffer enable; unused in current controller scope | 9 / D9 | P0.26 |
| Battery monitor | A6, factory connection | P0.29 |

The Express mappings are separately confirmed in its [board variant](https://raw.githubusercontent.com/adafruit/Adafruit_nRF52_Arduino/master/variants/feather_nrf52840_express/variant.cpp).

## One finger circuit, repeated ten times

```text
Feather 3V ------- Jx pin 1 ----- flex sensor terminal 1
                                   variable resistance
ADC node -------- Jx pin 2 ----- flex sensor terminal 2
   |
   +------------- Feather Ax
   |
   +---- 47 kohm, 1% ------------ local GND
   |
   +---- 100 nF ceramic --------- local GND
```

The flex sensor is a two-terminal variable resistor and has no electrical polarity. Label connector pin 1 as `3V`, pin 2 as the finger's signal. Connector numbering is a project convention: mark the chosen housing's cavity 1 and confirm it on the drawing/continuity test. Never infer a connector cavity from a generic left/right image.

The resistor and capacitor are parallel branches from the ADC node to ground; **neither goes in series with the ADC wire**. Put both near the Feather/prototype board. One 47 kohm resistor is needed per sensor, not per hand. Join the five resistors' lower ends and five capacitors' lower ends to the same local ground bus. Join all five connector pin-1 terminals to that hand's regulated `3V` bus.

### Complete connector/ADC schedule

| Connector | Signal net at cavity 2 | ADC endpoint | Cavity 1 endpoint | Shunt resistor | Shunt capacitor |
|---|---|---|---|---|---|
| JL1 | L_THUMB | Left A0 | Left 3V | RL1 47k to L_GND | CL1 100nF to L_GND |
| JL2 | L_INDEX | Left A1 | Left 3V | RL2 47k to L_GND | CL2 100nF to L_GND |
| JL3 | L_MIDDLE | Left A2 | Left 3V | RL3 47k to L_GND | CL3 100nF to L_GND |
| JL4 | L_RING | Left A3 | Left 3V | RL4 47k to L_GND | CL4 100nF to L_GND |
| JL5 | L_LITTLE | Left A4 | Left 3V | RL5 47k to L_GND | CL5 100nF to L_GND |
| JR1 | R_THUMB | Right A0 | Right 3V | RR1 47k to R_GND | CR1 100nF to R_GND |
| JR2 | R_INDEX | Right A1 | Right 3V | RR2 47k to R_GND | CR2 100nF to R_GND |
| JR3 | R_MIDDLE | Right A2 | Right 3V | RR3 47k to R_GND | CR3 100nF to R_GND |
| JR4 | R_RING | Right A3 | Right 3V | RR4 47k to R_GND | CR4 100nF to R_GND |
| JR5 | R_LITTLE | Right A4 | Right 3V | RR5 47k to R_GND | CR5 100nF to R_GND |

Each Jx mates to a cable with two conductors to that sensor's terminals. No wires run between wearables or from a wearable to the hub. The planned wearable-to-hub transport is BLE. Each wearable has its own battery and ground domain. The hub passes controller commands to the computer; the active controller documentation defines that interface. No aircraft or trainer circuit is needed.

### Calculated behavior and component ratings

Adafruit lists approximately 25 kohm relaxed and 100 kohm strongly flexed; real units require measurement and calibration. Its delicate crimp/terminal area needs strain relief. Leave the sensing length able to slide and do not cut it. [Flex sensor #1070](https://www.adafruit.com/product/1070).

Calculated from VADC = V3V × 47k/(Rflex + 47k):

| Condition | Rflex used | Expected VADC at V3V=3.300V |
|---|---:|---:|
| Typical relaxed example | 25k | 2.154V |
| Typical bent example | 100k | 1.055V |
| Flex unplugged/broken lead | Infinite | Near 0V |
| Sensor terminals shorted | 0 | Near 3.300V |

These values are examples, not calibrated thresholds or guaranteed sensor extremes. A disconnected ADC-to-board wire can float and is not reliably detected by this network; place the resistor/capacitor at the ADC board end. A stuck sensor or in-range short between channels may also escape simple range detection. Firmware must use packet age, sequence and sensor-health checks in addition to ADC range checks.

Maximum resistor dissipation under a shorted sensor is 3.3²/47000 = 0.232mW; 1/8W or 1/4W resistors comfortably meet the electrical load. Specify 100nF ceramic, at least 10V. Five relaxed dividers together draw about 229µA. With 100nF, normal source resistance is 16.32–31.97k, RC time constant 1.63–3.20ms, and single-pole cutoff roughly 98–50Hz. Worst-case open-sensor time constant is 4.7ms. Allow at least 50ms after power stabilizes before accepting calibration or control samples.

## ADC firmware assumptions that affect the circuit

The Nordic nRF52840 acquisition-time table allows 40k source resistance at 5µs and 100k at 10µs. Select 10µs for margin and correct open-fault sampling. Analog voltages must remain between ground and VDD even when the conversion range is nominally 3.6V. [Nordic nRF52840 product specification, SAADC](https://docs-be.nordicsemi.com/bundle/nRF52840_PS_v1.8/raw/resource/enus/nRF52840_PS_v1.8.pdf).

Explicitly configure the Adafruit Arduino core: the source inspected on September 14 defaulted to 10-bit readings and 3µs acquisition, while the guide's displayed default-resolution text differed. Verify against the implementation version used for the prototype. The inspected core implements these settings. [Adafruit ADC source](https://raw.githubusercontent.com/adafruit/Adafruit_nRF52_Arduino/master/cores/nRF5/wiring_analog_nRF52.c).

```cpp
analogReadResolution(12);
analogReference(AR_INTERNAL);  // internal 0.6V, gain 1/6: nominal 3.6V span
analogSampleTime(10);          // microseconds
```

Keep GPIO pulls disabled on A0–A4. The 100nF capacitors help supply the ADC sampling charge; they do not justify assuming maximum ADC speed or skipping settling checks. Verify readings while rapidly alternating between a low-valued and high-valued channel, on battery, with BLE active. Record each finger's open and closed comfortable positions and a plausible range with margin. Near-rail readings trigger a sensor fault, not maximum commanded motion. Determine final thresholds using measured rail and sensor values; a preliminary bench check can flag below 0.1V or above 0.95×VDD but is not comprehensive fault detection.

The battery divider is factory-wired to A6 and needs no external resistors. For 12-bit internal-reference readings, battery voltage is approximately `2 × reading × 3.6 / 4096`; verify against a meter. Do not copy the guide's divisor 1024 after explicitly selecting 12 bits. Read the actual battery level and require adequate reserve before enabling gestures.

## Power and charging: repeat once on each of the three Feathers

| Wire/connection | Endpoint 1 | Endpoint 2 |
|---|---|---|
| Battery positive | #1578 supplied red lead, original JST-PH plug | Feather JST battery + / BAT |
| Battery negative | #1578 supplied black lead, original JST-PH plug | Feather JST battery − / GND |
| Power switch conductor 1 | Feather EN | SW_PWR terminal A |
| Power switch conductor 2 | Feather GND | SW_PWR terminal B |
| Charging/programming | Feather Micro-USB receptacle | Suitable 5V USB supply/data host via Micro-USB cable |

Select three maintained SPST switches. Label **closed = OFF; open = ON**. If using SPDT slide switches, use the common and one throw, isolate the unused throw, and verify continuity rather than assuming center-lug assignment. Do not route battery current through EN. USB and battery remain electrically present with EN grounded; this is a regulator-off switch, not complete battery isolation. Unplug the battery and USB before modifying wiring. The switch arrangement allows charging with the application electronics off. Adafruit documents EN-to-ground shutdown and the `3V`, `BAT`, `USB`, ground roles. [Sense power management](https://learn.adafruit.com/adafruit-feather-sense/power-management), [Express power management](https://learn.adafruit.com/introducing-the-adafruit-nrf52840-feather/power-management-2).

Keep each #1578's original correctly polarized plug. Measure polarity before first insertion; an apparently mating connector from another supplier may be reversed. #1578 includes protection and specifies a maximum charge current of 500mA. [Battery #1578](https://www.adafruit.com/product/1578).

**Do not label Sense charging as 100mA.** The published Rev C schematic uses MCP73831 with R4=4.7k from PROG to GND, implying approximately 1000/4.7 = 213mA constant-current charging. This is below the selected battery's 500mA limit. It is a nominal circuit calculation; delivered hardware and temperature can change actual current. No external charger is needed and no charge-rate resistor modification is requested. [Sense Rev C schematic](https://raw.githubusercontent.com/adafruit/Adafruit-Feather-nRF52840-Sense-PCB/master/Adafruit%20Feather%20nRF52840%20Sense%20Rev%20C.sch), [MCP73831 data sheet](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP73831-Family-Data-Sheet-DS20001984H.pdf).

The hub Express Rev E also uses MCP73831 and 4.7k R4 at PROG, so the same nominal 213mA calculation applies. [Express Rev E schematic](https://raw.githubusercontent.com/adafruit/Adafruit-nRF52-Bluefruit-Feather-PCB/master/Adafruit%20nRF52840%20Bluefruit%20Feather%20Express%20Rev%20E.sch). Adafruit's downloads page explicitly corrects an older schematic battery-monitor label `D5` to `A6`; the hub's external D5 is unused in the active controller design. [Express downloads/correction](https://learn.adafruit.com/introducing-the-adafruit-nrf52840-feather/downloads).

Use the own-board `3V` pin for sensor dividers and button pulls. Do not tie a Feather's `3V` to its BAT or USB. The original aircraft's 4S pack is outside scope and must not feed any Feather pin. Wearables are separately charged, off the body, with USB access and battery inspection available.

## Both external pushbuttons: complete circuit

```text
Local 3V ----- 10k -----+------ input GPIO
                        |
                        +------ 100nF ------ local GND
                        |
                        +------ 1k ------ normally-open button ------ local GND
```

Left circuit: input GPIO = left D5; label button `HOLD TO ENABLE`.

Hub circuit: input GPIO = hub D6; label button `CALIBRATE`.

Each switch has two electrical contacts; a common four-legged tactile switch has two pairs internally connected. Meter-identify its two separate contact groups. Wire one group to the series resistor and the other to ground; do not use two legs from the same permanently connected group.

The pull-up holds an open/disconnected button inactive. A pressed button reads approximately 0.30V (10k/1k divider), valid logic low. External pulls are used so the inactive level is defined before firmware initialization. Use input mode and software debounce, e.g. start by requiring 20ms stable state. Broken ENABLE wire means disabled; a short to ground can imitate a press, so require release followed by press after boot/reconnect. ENABLE permits gesture-command acceptance; it must not bypass the simulator's separate run/reset state. CALIBRATE is accepted only with command output disabled. No automatic enabling after reconnect.

Firmware at the hub must invalidate both-hand control as soon as either hand becomes stale/invalid and require a new deliberate enable. The computer interface must expose command validity and freshness so the simulator can stop accepting stale commands. Define and verify the disabled/reset behavior in the [controller validation plan](controller/validation.md) and [current architecture](architecture.md). Circuit diagrams alone do not implement or validate that behavior; Pocket takeover and PPM trainer frames are historical design choices only.

## Additional small-parts quantities for the drawings

Beyond the BOM's 10 sensor channels, specify two 10k 1% pull-ups, two 1k series resistors, and two additional 100nF capacitors for the two buttons. These are project-selected parts within H05/H06, not included on the Feather. Historical trainer-interface parts are excluded from the active controller BOM. Sensor connectors: ten keyed two-contact mating pairs, plus two-contact button connectors if desired (extra to the ten sensor pairs).

## Unused external pins

Wearable A5, AREF, SCK, MOSI, MISO, TX, RX, 2, 6, 9, 10, 11, 12, 13, SDA and SCL receive no external wires in this design; right-hand 5 is also unused. `BAT` and `USB` header pads need no extra wire because the native JST and USB sockets supply power. Preserve on-board sensors and their internal connections. Do not bridge AREF to 3V. On-board LEDs/NeoPixel can show status without extra wiring. Leave the hub's former trainer pins D5/D9 unconnected; do not assemble the archived trainer buffer for the active simulation/controller milestones.
