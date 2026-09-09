# Component List and Procurement Gates

Research and availability check: 2026-09-09

## Purchase Strategy

Order development electronics only after the body team confirms both the
2.5-inch propulsion envelope and the mixed electronics mounting patterns. Buy
at least one spare motor and several batteries. Do not buy custom PCBs for the
first flight.

Availability is a snapshot, not a guarantee. Reopen every manufacturer link
immediately before ordering and verify the exact revision, input voltage,
connector, dimensions, and stock.

## Aircraft BOM

| Qty | Component | Selected part | Key requirement | Status |
|---:|---|---|---|---|
| 1 | H7 flight controller | Holybro Kakute H7 Mini v1.5, ICM-42688-P | STM32H743, PX4 target, 20 x 20 mm | Buy exact v1.5 [[9]](sources.md#source-9) |
| 1 | Four-in-one ESC | T-Motor V45A Lite | 3-6S, 45 A x4, BLHeli_S, 30.5 x 30.5 mm | Buy; current manufacturer inventory [[11]](sources.md#source-11) |
| 5 | Motors | T-Motor F1204 5000KV | 2-3S, 1.5 mm shaft, 2.5-3 inch | Four installed plus one spare [[12]](sources.md#source-12) |
| 1 | BLE gateway | Seeed XIAO ESP32-C3 | BLE central and CRSF UART | Buy or use existing [[1]](sources.md#source-1) |
| 1 | Position module | ARK SAM GPS Mini | SAM-M10Q GNSS + IIS2MDC compass | Buy exact unit [[13]](sources.md#source-13) |
| 3 | Flight batteries | Tattu 450 mAh 3S 75C XT30 | Standard LiPo, balance lead | Start with three [[22]](sources.md#source-22) |
| 1 | Power connector lead | Genuine XT30 pigtail, 18 AWG silicone | Replace ESC's supplied XT60 lead | Buy from reputable distributor |
| 1 | Input capacitor | 470 uF low-ESR, at least 25 V | Directly across ESC battery pads | Use ESC-supplied part only if rating is verified |
| 1 | Buzzer | 5 V active piezo compatible with H7 buzzer pads | Audible fault/arming indication | Buy |
| 1 | Receiver harness | JST-SH 1.0 mm 6-pin pigtail plus locking 4-pin receiver plug | Replaceable BLE/ELRS CRSF interface | Fabricate and continuity-test |
| 1 | ESC harness | JST-SH 1.0 mm 8-pin pigtail | H7 signals to cross-vendor ESC wiring | Re-pin; never plug blindly |
| 1 set | Wire | 30 AWG silicone signal, 18 AWG battery, motor wire matching motor leads | Flexible, heat resistant | Buy |
| 1 set | Insulation and strain relief | Heat-shrink, fabric tape, cable ties, adhesive mounts | No exposed conductors or wire load at pads | Buy |
| 1 set | Mounting | M2/M3 hardware, nylon spacers, H7 grommets, printed adapter as needed | Separate 20 mm and 30.5 mm patterns | Body-dependent |
| 1 | Body and guards | Team design | Fits all board envelopes and protects 2.5-inch props | Team supplied; must pass gate |
| 2 CW + 2 CCW minimum | Propellers | Team design | 1.5 mm motor shaft interface, known material/RPM limit | Team supplied; thrust-test required |

### Why this ESC looks oversized

Each selected motor is specified for only 6 A peak, so a 45 A channel rating is
far more than the electrical requirement. The V45A Lite is selected because it
is currently sold by the manufacturer, supports 3S, accepts DShot-class inputs,
and has ample margin. The tradeoffs are a 41.6 x 39.4 mm board, 30.5 mm mount,
13 g mass, and no ESC telemetry. [[11]](sources.md#source-11)

Two smaller candidates found during research were rejected because their
manufacturer pages mark them discontinued: the Hobbywing XRotor Nano 20A and
the SpeedyBee 35A Mini stack. [[27]](sources.md#source-27)
[[28]](sources.md#source-28) Do not source an old design from an unknown seller
just to save board area.

### ESC procurement gate

Before ordering, the body CAD must show:

- A clear 42 x 40 x 7 mm ESC envelope plus capacitor and solder-joint space.
- A 30.5 x 30.5 mm M3 mounting pattern.
- A separate 20 x 20 mm location for the H7, with USB access.
- Airflow across the ESC and no contact with printed plastic, battery, or wires.
- Short motor leads and a short XT30 battery lead.
- No GNSS/compass directly above the ESC, battery lead, or motors.

If the board does not fit, stop and select a currently stocked 3S-capable ESC
with published dimensions and DShot compatibility. Do not change to an unknown
marketplace ESC without a new electrical and thermal review.

## Hand Controller BOM

| Qty | Component | Selected part | Notes |
|---:|---|---|---|
| 1 | Controller MCU/radio | Seeed XIAO ESP32-C3 | BLE peripheral; external antenna kept clear [[1]](sources.md#source-1) |
| 1 | Hand IMU | Adafruit BNO085 breakout | Use UART-RVC, not I2C with ESP32 [[6]](sources.md#source-6) |
| 1 | Two-axis self-centering stick | Adafruit Mini 2-Axis Analog Thumbstick, product 2765 | Two 10 kohm axes; yaw and vertical [[25]](sources.md#source-25) |
| 1 | Deadman switch | Momentary normally-open button or lever | Must require continuous deliberate pressure |
| 1 | ARM switch | Momentary button, physically distinct | Requires state-machine sequence; not a maintained raw arm line |
| 1 | KILL switch | Guarded momentary red button | Must be hard to press accidentally and easy to identify by touch |
| 1 | Controller battery | Protected 3.7 V 500 mAh LiPo, Adafruit 1578 or equivalent | Verify polarity before adapting to XIAO pads [[24]](sources.md#source-24) |
| 1 | Master power switch | Rated for battery current | Physically disconnects controller battery |
| 1 | Status LED | High-efficiency LED plus 1 kohm resistor | Link/ready/fault patterns only |
| 5 | Button resistors | 10 kohm, 1% | External defined-state pulls even if firmware is not running |
| 2 | ADC capacitors | 10 nF ceramic | Optional joystick wiper filtering after response test |
| 1 set | Connectors and enclosure | JST-PH polarity adapter, headers, strain relief, hand enclosure | No exposed cell or shortable contacts |

Haptic feedback is optional after the basic controller works. If added, use a
transistor/driver and flyback protection appropriate to the actuator; never
drive a vibration motor directly from a GPIO.

## Charging and Bench Equipment

| Qty | Item | Selected/required capability | Purpose |
|---:|---|---|---|
| 1 | Balance charger | ISDT 608AC or equivalent, LiPo 1-6S | Charge 3S packs at 0.45 A (1C) through main and balance leads [[23]](sources.md#source-23) |
| 1 | Charge adapter | XT60-to-XT30 lead, correctly gendered and insulated | Connect charger output to battery |
| 1 | Fire-resistant battery container | LiPo charging/storage bag or metal vented container | Reduce consequence of battery failure |
| 1 | Bench supply | Current-limited, at least 0-15 V / 5 A for electronics | Bring up avionics without a flight pack; not for full motor thrust |
| 1 | Smoke stopper | Resettable current limiter rated for 3S | First battery power-up only |
| 1 | Digital multimeter | Continuity, voltage, current | Harness and power checks |
| 1 | Inline power analyzer | At least 15 V / 40 A | Measure full-system battery current and sag |
| 1 | Oscilloscope or logic analyzer | At least 10 MHz for UART/DShot sanity checks | Timing and noise diagnosis |
| 1 | USB BLE sniffer | Nordic-compatible sniffer or equivalent | Packet, interval, and disconnect characterization |
| 1 | Thrust stand and scale | At least 250 g thrust and 10 A current per motor | Validate actual propeller |
| 1 | Non-contact tachometer | Above expected prop RPM | Propeller RPM validation |
| 1 | IR thermometer/thermal camera | Motor, ESC, connector temperature | Thermal gate |
| 1 | Physical test enclosure | Netted on all sides and overhead | First powered hops and indoor movement |
| 1 | Safety equipment | Eye protection, small LiPo-rated fire response equipment | Required during battery and propulsion work |

Do not use a 1S/2S-only charger for the selected 3S flight pack. Inspect every
pack before and after use. Never charge unattended, hot, swollen, punctured, or
damaged cells.

## Propulsion Sizing

### Motor data

The F1204 5000KV official test with a GF2540 prop at about 12.2 V reports:

| Throttle | Thrust | Current | Electrical power |
|---:|---:|---:|---:|
| 50% | 58.85 g | 1.41 A | 17.20 W |
| 60% | 78.63 g | 2.07 A | 25.26 W |
| 80% | 120.67 g | 3.69 A | 44.83 W |
| 100% | 156.57 g | 5.63 A | 68.06 W |

These are selection data, not acceptance data, because the team supplies a
different propeller. [[12]](sources.md#source-12)

### Mass budget

| Item | Planning mass |
|---|---:|
| Four motors, cables trimmed | 25-28 g |
| H7 flight controller | 5.5 g |
| ESC | 13 g |
| Aircraft XIAO C3 and wiring | 4-7 g |
| ARK SAM GPS Mini and wiring | about 8-10 g |
| 3S 450 mAh battery | 42 g nominal [[22]](sources.md#source-22) |
| Capacitor, connector, buzzer, hardware | 8-12 g |
| Team body, guards, and props | 25-45 g target |
| **Planned all-up range** | **130-160 g** |

Weigh the assembled aircraft. Do not use this table as the final mass.

### Acceptance math

At 160 g all-up weight:

- Hover thrust is `160 / 4 = 40 g` per motor.
- A minimum 2:1 static thrust ratio requires `80 g` per motor.
- The published four-motor peak is about `4 x 156.57 = 626 g` with the vendor
  prop, but that number is not transferable to the team's prop.
- Published peak current is `4 x 5.63 = 22.52 A`.
- A 450 mAh 75C label implies 33.75 A, but actual sag and temperature decide
  whether the pack is acceptable.

### Propeller gate

The team's propeller must pass all conditions on one motor before four are
installed:

- Correct 1.5 mm shaft/hub fit with no slip or eccentricity.
- At least 80 g static thrust for a 160 g aircraft.
- No more than 6 A per motor in the approved operating range.
- No visible cracking, hub deformation, or contact with guards.
- No unsafe vibration in the motor mount or H7 log.
- Motor, ESC, connector, and winding temperatures remain within manufacturer
  limits after the defined test duration.
- Measured RPM remains below the propeller's documented safe limit. If the team
  cannot state that limit, the propeller is not approved for free flight.

If all-up mass exceeds 160 g, recompute the per-motor target and repeat testing.
Do not compensate for an underpowered combination by removing guards or raising
software limits.

## Battery Decision

Start with the Tattu 450 mAh 3S 75C XT30 pack: 11.1 V nominal, 42 g listed
weight, 45 x 24 x 21 mm, XT30 discharge, and JST-XHR-4P balance connector.
[[22]](sources.md#source-22)

Use measured hover current to estimate usable duration:

```text
estimated_minutes = 60 * usable_capacity_Ah / average_current_A
```

Use no more than the capacity recovered during a conservative recharge, not the
label capacity. Land before critical voltage and keep a per-pack cycle log.

## Do Not Purchase Yet

- A custom H7 PCB.
- A second aircraft IMU merely for a specification-sheet feature.
- ExpressLRS hardware before BLE flight requirements are measured, unless the
  team wants it independently as a conventional backup development controller.
- Optical flow/UWB hardware without first defining the indoor coordinate frame,
  coverage, update rate, accuracy, latency, and loss behavior.
- Camera/VTX equipment for the first hover; it adds mass, power, RF noise, and
  regulatory/test complexity without helping the initial objective.
