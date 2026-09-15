# Aircraft schematic research — verified 2026-09-14

Scope: selected BOM D01–D11. This records external board-level wiring, not unreleased PCB internals. Use Kakute H7 **v1.5, SKU11091**, not Mini or V2. ESC is Tekko32 F4 4in1 50A **AM32, SKU31102**, not Mini SKU31246.

## Recommended netlist

All aircraft grounds join through FC and ESC. Separate aircraft battery power from hand/hub power domains. Flight battery is 4S: 14.8 V nominal, 16.8 V full. Power leaves XT60 directly for ESC large power pads, not FC signal pads. Capacitor 1000 µF / 35 V supplied with stack: positive to ESC `+`, negative stripe lead to ESC `−`; install short leads close to pads and insulate.

### FC ↔ ESC supplied 8-conductor cable

The following **contact order** is verified in current manufacturer images; A1–A8 below are schematic contact labels, not an asserted JST manufacturer's pin-number standard. With FC top/component side facing viewer, USB right, ESC1 socket top: A1–A8 run **left to right**. With ESC AM32-logo/component face up, large battery pads left (`−` above `+`), 8-pin socket right: A1–A8 run **top to bottom**. The cable connects matching function at both ends. Inspect supplied cable and continuity-test every conductor disconnected from both boards; color alone is not evidence.

| Contact | ESC label | FC ESC port 1 label | Purpose |
|---|---|---|---|
| A1 | VBAT | B+ | 4S battery voltage feeding FC regulator; NOT regulated 5 V |
| A2 | TLM | R7 | Serial ESC telemetry output to UART7 RX |
| A3 | GND | GND | Common power/signal return |
| A4 | CURRENT | CURRENT | Analog total ESC current-sensor voltage |
| A5 | M1 | M1 | Motor 1 control signal |
| A6 | M2 | M2 | Motor 2 control signal |
| A7 | M3 | M3 | Motor 3 control signal |
| A8 | M4 | M4 | Motor 4 control signal |

ESC port 2 on FC is unused. Its otherwise similar fourth contact is **NC**, and outputs are M5–M8. Do not plug quad ESC into that port.

ESC motor phase-pad triplets in the same component-side view: top-left M3, top-right M4, bottom-left M1, bottom-right M2. Each group gets all three leads from its assigned motor; phases have no positive/negative wire. Keep each group separate. Swapping any two wires reverses a motor, or set direction in AM32; verify every motor location and direction with props removed. The physical board may be rotated to suit frame routing; pad labels remain authoritative.

Sources: [current AM32 ESC product and pin map](https://holybro.com/products/tekko32-f4-4in1-50a-esc), [current H7 v1.5 diagram](https://cdn.shopify.com/s/files/1/0604/5905/7341/files/KAKUTE_H7_V1.5_diagram.jpg?v=1748308666), [Holybro H7 pinout](https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-v1/pinout).

### RP1 V2 receiver — UART3

| RP1 pad | Kakute pad | Proposed color |
|---|---|---|
| 5V | 5V | Red |
| G / − | GND | Black |
| TX | R3 | Yellow |
| RX | T3 | White |

Attach included 65 mm 2.4 GHz T-antenna to RP1 U.FL. Use a full non-inverted UART for CRSF. Do not use analog RSI pad, SBUS receiver input, or a single-wire link. UART3 is a deliberate update from the BOM's provisional UART1 allocation because R3/T3 are accessible solder pads, whereas UART1 is in the VTX connector alongside 9 V. Leave VTX connector unused. The official receiver manual presents top view (U.FL side) with pad order RX, TX, 5V, G; bottom view with ELRS/ESP8285 markings shows −, 5V, TX, RX. Match printed pad names, not viewpoint memory.

Sources: [RadioMaster RP1 V2](https://radiomasterrc.com/products/rp1-expresslrs-2-4ghz-nano-receiver), [RadioMaster official RP1 manual](https://cdn.shopify.com/s/files/1/0609/8324/7079/files/RP1_User_Manual.pdf?v=1722923320), [ExpressLRS receiver wiring](https://www.expresslrs.org/quick-start/receivers/wiring-up/).

### Matek M10Q-5883 GNSS + compass — UART4 and I²C

| Module contact | Kakute pad | Supplied cable color in manufacturer photo |
|---|---|---|
| 5V | 5V | Red |
| RX | T4 | Yellow |
| TX | R4 | Blue |
| CL | SCL | Green |
| DA | SDA | White |
| G | GND | Black |

Matek has **two mirrored 6-contact JST-GH connectors on the underside**. They carry equivalent signal labels in opposite physical order. Use exactly one connector and leave the second empty. Antenna side picture, connector facing down toward viewer, labels above connector read **G, DA, CL, TX, RX, 5V** left-to-right. This orientation refers to Matek's photo, NOT a loose plug viewed from its wire side. Manufacturer underside comparison image: with supercapacitor at upper-right, left socket order top-to-bottom is **5V,RX,TX,CL,DA,G**; right socket top-to-bottom is **G,DA,CL,TX,RX,5V**. Use module labels and continuity to map cut cable conductors. Do not assume another GPS brand's GH pinout.

Input allowed 4–9 V; selected supply is regulated 5 V. UART handles GNSS; SCL/SDA separately handle QMC5883L magnetometer. Factory GNSS UART is 9600 baud and UBX is bidirectional, so connect TX and RX. Set flight firmware to configure GNSS. Do not power at 3.3 V just because I/O is 3.3 V. Matek says ArduPilot/Mission Planner compass rotation None for prescribed flat arrow-forward installation; validate actual heading. Manufacturer requests 10 cm clearance from power wiring, motors, ESC and ferromagnetic material; the current deck location remains a physical integration issue, not solved by wiring.

The page describes JST-GH as 1.27 mm but actual part SM06B-GHS-TB is the [JST GH 1.25 mm family](https://www.jst-mfg.com/product/index.php?lang=2&series=105), verified with JST. Use supplied cable or that exact compatible series; do not buy 1.0 mm JST-SH based on a generic six-pin appearance.

Sources: [Matek M10Q-5883 page](https://www.mateksys.com/?portfolio=m10q-5883), [official connector comparison illustration](https://www.mateksys.com/wp-content/uploads/2023/03/M10Q-5883_4.jpg), [official cable photo](https://www.mateksys.com/wp-content/uploads/2023/03/M10Q-5883_3.jpg).

### VIFLY Finder 2

| Finder cable function | FC pad | Color shown by maker |
|---|---|---|
| 5V | 5V | Red |
| GND | GND | Black |
| BZ | Z− | Yellow |

Three wires are required. `Z−` is the switched buzzer control, not permanent ground. Finder contains its own backup cell/charger; do not connect flight battery directly or add a separate cell. Use supplied harness so connector-side position cannot be accidentally mirrored. Official wiring image identifies only functional contacts, not an unambiguous loose-plug pin-number/orientation standard; label the harness by functions. Mount so button and light sensor remain accessible. Following normal flight battery disconnect, hold Finder disarm button for 1–5 seconds then release (three beeps confirm). Alternative reconnect method is documented by manufacturer; button method is simpler.

Sources: [VIFLY Finder 2 product](https://viflydrone.com/products/vifly-finder-v2-fpv-racing-drone-buzzer), [official 3-wire diagram](https://cdn.shopify.com/s/files/1/0690/1035/8568/products/vifly-drone-finder2-drone-buzzer_5.jpg?v=1672647144).

### Dronetag BS gen.2 — regulated power only

Use left **4-pin JST-SH** connector and a matching cable. Manufacturer identifies top/component view with U.FL antenna sockets at top and two wire sockets at bottom: four-pin is left. Its separate **front view looking into the board's 4-pin receptacle** labels contacts **1,2,3,4 left-to-right**. Keep the housing oriented exactly as [the official front-view drawing](https://help.dronetag.com/img/dronetag-bs/4pin-diagram.jpg); do not copy that order onto a loose plug's wire-entry/back view.

| Manufacturer pin | Name | Connection |
|---|---|---|
| 1 | VCC (red) | FC 5V |
| 2 | UART RX (green) | NC; individually insulate |
| 3 | UART TX (blue) | NC; individually insulate |
| 4 | GND (black) | FC GND |

Right 3-pin JST-SH connector stays empty (pin1 VCC, pin2 reserved, pin3 GND). Both connectors' VCC contacts are directly joined; never feed two supplies into them. Dronetag BS includes its own GNSS, so serial data is unnecessary for baseline Remote ID operation and Matek remains aircraft-navigation source. The selected regulated 5 V supply avoids placing a 17 V-maximum part across a 16.8 V battery with switching transients. Maker quotes supply must support 50 mA peaks at 3.3 V; budget conservatively at least 50 mA on chosen rail until measured.

Install included antennas before power: short black-insulated antenna = Bluetooth 2.4 GHz, left U.FL; longer grey-insulated antenna = GNSS 1.575 GHz, right U.FL, in manufacturer's connector-side orientation. Preserve protection/heat shrink and LED visibility. Avoid soldering random exposed underside pads; use connector harness. No Dronetag configuration/compliance status can be inferred from a completed electrical connection.

Sources: [BS gen.2 power connector pin table](https://help.dronetag.com/dronetag-bs-gen2/power-source-installation/), [BS gen.2 antennas](https://help.dronetag.com/dronetag-bs-gen2/enclosure-installation/), [BS gen.2 feature list](https://help.dronetag.com/dronetag-bs-gen2/list-of-features/).

## Power and firmware cautions affecting correctness

- FC current product page and v1.5 diagram state **5 V / 2 A** and **9 V / 3 A** regulators. Old documentation pin table says 1.5 A on 5 V. Keep design loading conservatively below 1.5 A pending received-board verification and include own FC consumption where appropriate; exact RP1 + Finder peak consumption not established by these manufacturer pages. USB-only peripheral power behavior is not verified here.
- ESC has **no output BEC**; B+ harness contact is raw battery voltage. All low-voltage accessories are powered by FC 5V pads, not ESC VBAT.
- The 50 A per-channel rating is a component rating, not a demonstrated safe 200 A vehicle draw. Motor/prop/battery current needs characterization from project plan.
- FC v1.5 uses ICM-42688-P and current SPA06 barometer. Manufacturer page has old broad INAV/ArduPilot supported-version statements; receiving hardware + firmware detection must be checked. Root is validating current ArduPilot configuration.
- UART2 is occupied by onboard Bluetooth. UART7 RX is occupied by ESC TLM. UART1 and UART6 stay unused in this design. Do not enable another function on the allocated UART.
- Analog current scale depends on **ESC PCB** revision, not FC revision. Holybro table for SKU31102: ESC v1.5/1.6/1.7 → Betaflight scale168; v1.8 →110; v1.9/v1.9T →120. Maker formula for ArduPilot/PX4 is 10000/BetaflightScale: approximately59.524,90.909,83.333 A/V respectively. Confirm actual ESC silkscreen before setting, then calibrate against measured current. Do not use advertised120 blindly for all boards.
- TLM is serial ESC telemetry; CURRENT is analog current. They are different nets, neither replaces motor-control wires. Bidirectional DShot/eRPM support does not eliminate the analog current wire.

Sources: [current H7 specs](https://holybro.com/products/kakute-h7), [ESC current scales](https://docs.holybro.com/esc/current-sensor-scale), [current ESC specs](https://holybro.com/products/tekko32-f4-4in1-50a-esc).

## Local source illustrations

All below relative to project root; downloaded from manufacturer URLs above and visually inspected:

- `tmp/schematic-research/kakute-h7-v1.5.jpg` — full current v1.5 overview, original 1468×1080.
- `tmp/schematic-research/tekko-pinmap.jpg` — current AM32 ESC photo with explicit eight contacts and motor triplets, original 2048×2048.
- `tmp/schematic-research/matek-4.jpg` — old M10, current M10Q and M8 comparison; **center column only** is selected part.
- `tmp/schematic-research/matek-3.jpg` — M10Q supplied cable photo.
- `tmp/schematic-research/vifly-5.jpg` — official three-wire functional hookup.
- `tmp/schematic-research/vifly-4.jpg` — packaging, not needed for schematic.
- `tmp/schematic-research/dronetag-4pin.jpg` — manufacturer socket-front view with pins1–4 left-to-right.
- `tmp/schematic-research/dronetag-connectors.png` — gen.2 top/bottom board photos; identifies 4-pin/3-pin ports and left BT/right GNSS U.FL.
- `tmp/schematic-research/rp1-manual.pdf` — current linked official RadioMaster manual with top and bottom pin labels.
- `tmp/schematic-research/matek-page.html` — downloaded manufacturer page because web opener got403, search crawl and direct download successful.

## Remaining precise uncertainties

1. Received ESC PCB revision and thus current-sensor conversion.
2. Received FC sensor/barometer support and USB-only rail behavior.
3. Actual loose connector housing orientation/pin numbers for Finder; supply labeled harness, do not invent numbering.
4. Actual GPS wire colors may differ; module pad labels and continuity are authoritative. Matek numerical pin numbering was not explicitly published, so use function names/contact order tied to view.
5. Dronetag pin1 viewpoint is now resolved by official socket-front illustration; verify actual cable continuity because loose cable viewing direction can still mirror it.
6. Rail peak-current measurement and installed compass electromagnetic clearance.
