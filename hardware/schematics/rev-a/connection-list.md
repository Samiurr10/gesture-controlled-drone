# PalmPilot / Manta Flow - connection list, Rev A

Baseline: [PalmPilot_BOM.pdf](../../../docs/reference/PalmPilot_BOM.pdf), 14 September 2026. Use with the [PDF schematic](PalmPilot_Full_Schematic_and_Build_Guide.pdf).

**Trainer is a bench prototype:** the exact Pocket input tolerance and dropout behavior require validation before connecting/enabling it. All power domains are independent; only hub and Pocket share trainer ground.

Connection count includes local component leads, factory battery leads, and the separate twelve motor phase leads. A shared net requires a real soldered junction.

| ID | Net | From | To | Wire | Note |
|---|---|---|---|---|---|
| P01 | VBAT | BT1 mating XT60 + | U2 VBAT large + pad | 12 AWG red | One 4S pack; connector + mark controls polarity |
| P02 | AIR_GND | BT1 mating XT60 - | U2 GND large - pad | 12 AWG black | Short return paired with P01 |
| P03 | VBAT | C1 + | U2 VBAT large + pad | Capacitor lead | 1000 uF / 35 V; short and insulated |
| P04 | AIR_GND | C1 - striped side | U2 GND large - pad | Capacitor lead | Secure capacitor body |
| E01 | VBAT | U2 harness VBAT | U1 ESC1 B+ | Supplied 8-pin harness | RAW battery supply to FC, not 5 V |
| E02 | ESC_TLM | U2 harness TLM | U1 ESC1 R7 | Supplied 8-pin harness | ESC UART telemetry; no TX7 connection |
| E03 | AIR_GND | U2 harness GND | U1 ESC1 GND | Supplied 8-pin harness | Common signal ground |
| E04 | ESC_CURRENT | U2 harness CURRENT | U1 ESC1 CURRENT | Supplied 8-pin harness | Analog current signal, not power |
| E05 | MOTOR1 | U2 harness M1 | U1 ESC1 M1 | Supplied 8-pin harness | FC output -> ESC channel 1 |
| E06 | MOTOR2 | U2 harness M2 | U1 ESC1 M2 | Supplied 8-pin harness | FC output -> ESC channel 2 |
| E07 | MOTOR3 | U2 harness M3 | U1 ESC1 M3 | Supplied 8-pin harness | FC output -> ESC channel 3 |
| E08 | MOTOR4 | U2 harness M4 | U1 ESC1 M4 | Supplied 8-pin harness | FC output -> ESC channel 4 |
| A01 | AIR_5V | U1 5V | U3 RP1 5V | 26 AWG red | Receiver power |
| A02 | AIR_GND | U1 G | U3 RP1 GND | 26 AWG black | Receiver reference |
| A03 | CRSF_UP | U3 RP1 TX | U1 R3 | 28 AWG white | Receiver commands -> FC |
| A04 | CRSF_DOWN | U1 T3 | U3 RP1 RX | 28 AWG blue | FC telemetry -> receiver |
| A05 | AIR_5V | U1 5V | U4 Matek 5V | 26 AWG red | 4-9 V allowed; use regulated 5 V |
| A06 | AIR_GND | U1 G | U4 Matek G | 26 AWG black | GNSS and compass ground |
| A07 | GPS_UP | U4 Matek TX | U1 R4 | Supplied blue | GNSS data -> FC; verify supplied color |
| A08 | GPS_DOWN | U1 T4 | U4 Matek RX | Supplied yellow | FC configuration -> GNSS; verify supplied color |
| A09 | I2C_SCL | U1 SCL | U4 Matek CL | 28 AWG green | Compass clock; do not add 5 V pull-ups |
| A10 | I2C_SDA | U1 SDA | U4 Matek DA | Supplied white | Compass data; 3.3 V logic; verify color |
| A11 | AIR_5V | U1 5V | U5 4-pin contact 1 VCC | 26 AWG red | Standalone module power |
| A12 | AIR_GND | U1 G | U5 4-pin contact 4 GND | 26 AWG black | Contacts 2/3 NC; leave 3-pin connector empty |
| A13 | AIR_5V | U1 5V | BZ1 Finder 2 5V | 26 AWG red | Buzzer supply/charging |
| A14 | AIR_GND | U1 G | BZ1 Finder 2 GND | 26 AWG black | Must connect real GND |
| A15 | BUZZ_LOW | U1 Z- | BZ1 Finder 2 BZ | 28 AWG yellow | Switched negative trigger, not GND |
| RF1 | ELRS_RF | U3 RP1 U.FL | Supplied 2.4 GHz T antenna | Factory coax | Push straight down; strain-relieve coax |
| RF2 | RID_BT | U5 left U.FL (marked BT) | Short black Bluetooth antenna | Factory coax | Board view: RF sockets top, wire sockets bottom |
| RF3 | RID_GNSS | U5 right U.FL (marked GNSS) | Long grey GNSS antenna | Factory coax | Do not interchange with BT antenna |
| M1U | PHASE_1U | U2 motor bank 1 phase 1 | M1 rear-right lead U | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M1V | PHASE_1V | U2 motor bank 1 phase 2 | M1 rear-right lead V | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M1W | PHASE_1W | U2 motor bank 1 phase 3 | M1 rear-right lead W | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M2U | PHASE_2U | U2 motor bank 2 phase 1 | M2 front-right lead U | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M2V | PHASE_2V | U2 motor bank 2 phase 2 | M2 front-right lead V | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M2W | PHASE_2W | U2 motor bank 2 phase 3 | M2 front-right lead W | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M3U | PHASE_3U | U2 motor bank 3 phase 1 | M3 rear-left lead U | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M3V | PHASE_3V | U2 motor bank 3 phase 2 | M3 rear-left lead V | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M3W | PHASE_3W | U2 motor bank 3 phase 3 | M3 rear-left lead W | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M4U | PHASE_4U | U2 motor bank 4 phase 1 | M4 front-left lead U | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M4V | PHASE_4V | U2 motor bank 4 phase 2 | M4 front-left lead V | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| M4W | PHASE_4W | U2 motor bank 4 phase 3 | M4 front-left lead W | Match motor lead AWG | U/V/W are build labels; swap any two phases if direction is wrong |
| L1a | L_3V | U6 3V | JL1.1 -> FL1 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| L1b | L_A0 | FL1 terminal 2 -> JL1.2 | U6 A0 | 30 AWG signal | thumb; node NL1 |
| L1c | L_A0 | U6 A0 | RL1.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| L1d | L_GND | RL1.2 | U6 GND | Local trace/jumper | Divider lower leg |
| L1e | L_A0 | U6 A0 | CL1.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| L1f | L_GND | CL1.2 | U6 GND | Local trace/jumper | Place RC by ADC header |
| L2a | L_3V | U6 3V | JL2.1 -> FL2 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| L2b | L_A1 | FL2 terminal 2 -> JL2.2 | U6 A1 | 30 AWG signal | index; node NL2 |
| L2c | L_A1 | U6 A1 | RL2.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| L2d | L_GND | RL2.2 | U6 GND | Local trace/jumper | Divider lower leg |
| L2e | L_A1 | U6 A1 | CL2.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| L2f | L_GND | CL2.2 | U6 GND | Local trace/jumper | Place RC by ADC header |
| L3a | L_3V | U6 3V | JL3.1 -> FL3 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| L3b | L_A2 | FL3 terminal 2 -> JL3.2 | U6 A2 | 30 AWG signal | middle; node NL3 |
| L3c | L_A2 | U6 A2 | RL3.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| L3d | L_GND | RL3.2 | U6 GND | Local trace/jumper | Divider lower leg |
| L3e | L_A2 | U6 A2 | CL3.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| L3f | L_GND | CL3.2 | U6 GND | Local trace/jumper | Place RC by ADC header |
| L4a | L_3V | U6 3V | JL4.1 -> FL4 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| L4b | L_A3 | FL4 terminal 2 -> JL4.2 | U6 A3 | 30 AWG signal | ring; node NL4 |
| L4c | L_A3 | U6 A3 | RL4.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| L4d | L_GND | RL4.2 | U6 GND | Local trace/jumper | Divider lower leg |
| L4e | L_A3 | U6 A3 | CL4.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| L4f | L_GND | CL4.2 | U6 GND | Local trace/jumper | Place RC by ADC header |
| L5a | L_3V | U6 3V | JL5.1 -> FL5 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| L5b | L_A4 | FL5 terminal 2 -> JL5.2 | U6 A4 | 30 AWG signal | little; node NL5 |
| L5c | L_A4 | U6 A4 | RL5.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| L5d | L_GND | RL5.2 | U6 GND | Local trace/jumper | Divider lower leg |
| L5e | L_A4 | U6 A4 | CL5.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| L5f | L_GND | CL5.2 | U6 GND | Local trace/jumper | Place RC by ADC header |
| R1a | R_3V | U7 3V | JR1.1 -> FR1 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| R1b | R_A0 | FR1 terminal 2 -> JR1.2 | U7 A0 | 30 AWG signal | thumb; node NR1 |
| R1c | R_A0 | U7 A0 | RR1.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| R1d | R_GND | RR1.2 | U7 GND | Local trace/jumper | Divider lower leg |
| R1e | R_A0 | U7 A0 | CR1.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| R1f | R_GND | CR1.2 | U7 GND | Local trace/jumper | Place RC by ADC header |
| R2a | R_3V | U7 3V | JR2.1 -> FR2 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| R2b | R_A1 | FR2 terminal 2 -> JR2.2 | U7 A1 | 30 AWG signal | index; node NR2 |
| R2c | R_A1 | U7 A1 | RR2.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| R2d | R_GND | RR2.2 | U7 GND | Local trace/jumper | Divider lower leg |
| R2e | R_A1 | U7 A1 | CR2.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| R2f | R_GND | CR2.2 | U7 GND | Local trace/jumper | Place RC by ADC header |
| R3a | R_3V | U7 3V | JR3.1 -> FR3 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| R3b | R_A2 | FR3 terminal 2 -> JR3.2 | U7 A2 | 30 AWG signal | middle; node NR3 |
| R3c | R_A2 | U7 A2 | RR3.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| R3d | R_GND | RR3.2 | U7 GND | Local trace/jumper | Divider lower leg |
| R3e | R_A2 | U7 A2 | CR3.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| R3f | R_GND | CR3.2 | U7 GND | Local trace/jumper | Place RC by ADC header |
| R4a | R_3V | U7 3V | JR4.1 -> FR4 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| R4b | R_A3 | FR4 terminal 2 -> JR4.2 | U7 A3 | 30 AWG signal | ring; node NR4 |
| R4c | R_A3 | U7 A3 | RR4.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| R4d | R_GND | RR4.2 | U7 GND | Local trace/jumper | Divider lower leg |
| R4e | R_A3 | U7 A3 | CR4.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| R4f | R_GND | CR4.2 | U7 GND | Local trace/jumper | Place RC by ADC header |
| R5a | R_3V | U7 3V | JR5.1 -> FR5 terminal 1 | 30 AWG red | Flex sensor is nonpolar |
| R5b | R_A4 | FR5 terminal 2 -> JR5.2 | U7 A4 | 30 AWG signal | little; node NR5 |
| R5c | R_A4 | U7 A4 | RR5.1 | Local trace/jumper | 47 kohm, 1%, 0.125 W or higher |
| R5d | R_GND | RR5.2 | U7 GND | Local trace/jumper | Divider lower leg |
| R5e | R_A4 | U7 A4 | CR5.1 | Local trace/jumper | 100 nF, X7R, >=10 V |
| R5f | R_GND | CR5.2 | U7 GND | Local trace/jumper | Place RC by ADC header |
| LP1 | L_BAT | BT2 + | U6 JST BAT + | Factory battery lead | Adafruit #1578, protected 1S 500 mAh |
| LP2 | L_GND | BT2 - | U6 JST BAT - | Factory battery lead | Check connector polarity; never series-connect cells |
| LP3 | L_EN | U6 EN | SWL common | 28 AWG signal | SPDT slide used as SPST |
| LP4 | L_GND | SWL OFF throw | U6 GND | 28 AWG black | Other throw NC; closed EN-GND means OFF |
| RP1 | R_BAT | BT3 + | U7 JST BAT + | Factory battery lead | Adafruit #1578, protected 1S 500 mAh |
| RP2 | R_GND | BT3 - | U7 JST BAT - | Factory battery lead | Check connector polarity; never series-connect cells |
| RP3 | R_EN | U7 EN | SWR common | 28 AWG signal | SPDT slide used as SPST |
| RP4 | R_GND | SWR OFF throw | U7 GND | 28 AWG black | Other throw NC; closed EN-GND means OFF |
| HP1 | H_BAT | BT4 + | U8 JST BAT + | Factory battery lead | Adafruit #1578, protected 1S 500 mAh |
| HP2 | H_GND | BT4 - | U8 JST BAT - | Factory battery lead | Check connector polarity; never series-connect cells |
| HP3 | H_EN | U8 EN | SWH common | 28 AWG signal | SPDT slide used as SPST |
| HP4 | H_GND | SWH OFF throw | U8 GND | 28 AWG black | Other throw NC; closed EN-GND means OFF |
| SW4.1 | L_3V | U6 3V | R201.1 | 28 AWG / local trace | 10k external pull-up |
| SW4.2 | left_enable | R201.2 | U6 D5 | 28 AWG / local trace | GPIO configured INPUT; active low |
| SW4.3 | left_enable | U6 D5 | R202.1 | 28 AWG / local trace | 1k in series toward button |
| SW4.4 | SW4_LEAD | R202.2 | SW4 contact 1 | 28 AWG / local trace | Normally open pushbutton |
| SW4.5 | L_GND | SW4 contact 2 | U6 GND | 28 AWG / local trace | Opposite contacts; not joined same-side legs |
| SW4.6 | left_enable | U6 D5 | C201.1 | 28 AWG / local trace | 100nF X7R >=10 V |
| SW4.7 | L_GND | C201.2 | U6 GND | 28 AWG / local trace | Capacitor at MCU pin |
| SW5.1 | H_3V | U8 3V | R203.1 | 28 AWG / local trace | 10k external pull-up |
| SW5.2 | hub_calibration | R203.2 | U8 D6 | 28 AWG / local trace | GPIO configured INPUT; active low |
| SW5.3 | hub_calibration | U8 D6 | R204.1 | 28 AWG / local trace | 1k in series toward button |
| SW5.4 | SW5_LEAD | R204.2 | SW5 contact 1 | 28 AWG / local trace | Normally open pushbutton |
| SW5.5 | H_GND | SW5 contact 2 | U8 GND | 28 AWG / local trace | Opposite contacts; not joined same-side legs |
| SW5.6 | hub_calibration | U8 D6 | C202.1 | 28 AWG / local trace | 100nF X7R >=10 V |
| SW5.7 | H_GND | C202.2 | U8 GND | 28 AWG / local trace | Capacitor at MCU pin |
| H01 | H_3V | U8 3V | U301 pin 5 VCC | Local wire | SN74LVC1G125DBVR; verify adapter map |
| H02 | H_GND | U8 GND | U301 pin 3 GND | Local wire | Logic supply reference |
| H03 | PPM_A | U8 D5 (P1.08) | U301 pin 2 A | Local wire | PPM waveform input |
| H04 | PPM_OEn | U8 D9 (P0.26) | U301 pin 1 /OE | Local wire | LOW enables buffer; HIGH disables |
| H05 | H_3V | U8 3V | R301.1 | Local trace | 10k pull-up |
| H06 | PPM_OEn | R301.2 | U301 pin 1 /OE | Local trace | Holds output disabled in reset |
| H07 | PPM_A | U301 pin 2 A | R302.1 | Local trace | 100k input pull-down |
| H08 | H_GND | R302.2 | U8 GND | Local trace | Defines idle input |
| H09 | H_3V | U301 pin 5 VCC | C301.1 | Local trace | 100nF, at IC |
| H10 | H_GND | C301.2 | U301 pin 3 GND | Local trace | Decoupling return |
| H11 | PPM_Y | U301 pin 4 Y | R303.1 | Local trace | 1k series resistor |
| H12 | PPM_PRE | R303.2 | JP301.1 / TP301 | Local trace | Test here with jumper removed |
| H13 | PPM_CABLE | JP301.2 / TP302 | J301 TS tip | Shielded signal | JP301 shunt OPEN until Pocket compatibility verified |
| H14 | H_GND | U8 GND | J301 TS sleeve | Shield / return | Only shared ground between hub and Pocket |

## Sources

- **S01:** [Project baseline - attached PalmPilot_BOM.pdf](../../../docs/reference/PalmPilot_BOM.pdf) - 34 pages; aircraft pp1-2, hand kit pp5-6, electrical pp23-28.
- **S02:** [Holybro Kakute H7 v1.5 stack and specifications](https://holybro.com/products/kakute-h7-v1-stacks) - Exact 11091+31102 stack; current v1.5 specification.
- **S03:** [Holybro Kakute H7 pinout](https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-v1/pinout) - Pad names; ESC and VTX port functions. Older rail figures noted.
- **S04:** [Holybro Tekko32 F4 4in1 50A ESC](https://holybro.com/products/tekko32-f4-4in1-50a-esc) - AM32 version and published connector drawing.
- **S05:** [RadioMaster RP1 V2 receiver](https://radiomasterrc.com/products/rp1-expresslrs-2-4ghz-nano-receiver) - RP1 V2 power, CRSF and antenna.
- **S06:** [Matek M10Q-5883](https://www.mateksys.com/?portfolio=m10q-5883) - Supply, UART, compass pads and separation guidance.
- **S07:** [Dronetag BS gen.2 power connectors](https://help.dronetag.com/dronetag-bs-gen2/power-source-installation/) - 4-pin VCC/RX/TX/GND; second connector reserved contact.
- **S08:** [VIFLY Finder 2](https://viflydrone.com/products/vifly-finder-v2-fpv-racing-drone-buzzer) - 5V/GND/BZ connection and self-powered function.
- **S09:** [Feather Sense pinouts](https://learn.adafruit.com/adafruit-feather-sense/pinouts) - Analog pins, power pins, A6 internal battery sense.
- **S10:** [Feather Sense board files](https://github.com/adafruit/Adafruit-Feather-nRF52840-Sense-PCB) - Revision-specific schematic and physical layout.
- **S11:** [Feather nRF52840 Express pinouts](https://learn.adafruit.com/introducing-the-adafruit-nrf52840-feather/pinouts) - Ground hub header pins and power.
- **S12:** [Adafruit Short Flex Sensor #1070](https://www.adafruit.com/product/1070) - Two-wire variable resistance sensor.
- **S13:** [Adafruit protected 500 mAh LiPo #1578](https://www.adafruit.com/product/1578) - Cell and charge compatibility.
- **S14:** [Adafruit nRF52 Arduino analog implementation](https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/cores/nRF5/wiring_analog_nRF52.c) - Explicit ADC reference, resolution and acquisition settings.
- **S15:** [RadioMaster Pocket](https://www.radiomasterrc.com/products/pocket-radio-controller-m2) - DSC port and official manual; see trainer research for mono wiring.
- **S16:** [EdgeTX trainer settings](https://manual.edgetx.org/bw-radios/radio-settings/trainer) - Radio trainer calibration and mapping.
- **S17:** [EdgeTX trainer validity source](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/trainer.cpp) - Reviewed source timeout; not a claim about installed radio firmware.
- **S18:** [ArduPilot Kakute H7 documentation](https://ardupilot.org/copter/docs/common-holybro-kakuteh7.html) - Serial mapping, battery scaling and output groups.
- **S19:** [ArduPilot KakuteH7 hardware definition at reviewed commit](https://github.com/ArduPilot/ardupilot/blob/dbe792162d06cab66c3475fd5556bf7a120f119e/libraries/AP_HAL_ChibiOS/hwdef/KakuteH7/hwdef.dat) - GPIO and UART verification; driver probes.
- **S20:** [ArduPilot Crossfire and ELRS wiring](https://ardupilot.org/copter/docs/common-tbs-rc.html) - Crossed full-duplex UART and protocol 23.
- **S21:** [ArduPilot motor connection guide](https://ardupilot.org/copter/docs/connect-escs-and-motors.html) - Motor identification and props-off motor tests.
- **S22:** [ArduPilot motor matrix implementation](https://github.com/ArduPilot/ardupilot/blob/master/libraries/AP_Motors/AP_MotorsMatrix.cpp) - BetaFlightX locations, directions and test order.
- **S23:** [ArduPilot DShot setup](https://ardupilot.org/copter/docs/common-dshot-escs.html) - Digital ESC configuration; no PWM endpoint calibration.
- **S24:** [KakuteH7 current stable firmware record](https://firmware.ardupilot.org/Copter/stable/KakuteH7/) - Reviewed 4.7.1 listing on 14 September 2026; recheck before installing.
- **S25:** [TI SN74LVC1G125 datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf) - Five-pin buffer, /OE, supply and power-off behavior.
- **S26:** [RadioMaster official trainer port pinout](https://radiomasterrc.freshdesk.com/support/solutions/articles/64000256682-trainer-port-pin-out) - Mono TS tip PPM / sleeve ground; family guidance, not Pocket input rating.
- **S27:** [Adafruit SOT23 adapter #1230](https://www.adafruit.com/product/1230) - Five-pin IC on six-pad carrier; verify leg-to-header continuity.
- **S28:** [Holybro current sensor scale by ESC revision](https://docs.holybro.com/esc/current-sensor-scale) - Convert Betaflight scale to A/V; received ESC revision determines value.
- **S29:** [Pocket A1.8 official manual](https://cdn.shopify.com/s/files/1/0701/8066/7584/files/Pocket_A1.8.pdf?v=1770617495) - DSC versus audio jack; independent batteries and SE momentary control.
- **S30:** [Current Kakute H7 v1.5 diagram](https://cdn.shopify.com/s/files/1/0604/5905/7341/files/KAKUTE_H7_V1.5_diagram.jpg?v=1748308666) - Physical pad/connector locator used in this package.
- **S31:** [Matek cable and connector photo](https://www.mateksys.com/wp-content/uploads/2023/03/M10Q-5883_3.jpg) - Supplied cable colors and module contact labels.
- **S32:** [Dronetag connector front-view diagram](https://help.dronetag.com/img/dronetag-bs/4pin-diagram.jpg) - Looking into board receptacle: 1 to 4 left-to-right as pictured.
- **S33:** [EdgeTX logical-switch setup](https://manual.edgetx.org/bw-radios/model-select/logical-switches) - Delay gating is a prototype proposal that needs actual-radio validation.
- **S34:** [Dronetag gen.2 antenna installation](https://help.dronetag.com/dronetag-bs-gen2/enclosure-installation/) - Bluetooth and GNSS antenna sockets are distinct.
- **S35:** [Sense pin-to-GPIO variant](https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/variants/feather_nrf52840_sense/variant.cpp) - External pin names and internal A6 monitoring.
- **S36:** [Express pin-to-GPIO variant](https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/variants/feather_nrf52840_express/variant.cpp) - D5/D6/D9 and battery monitor mapping.
- **S37:** [Adafruit SOT23 carrier CAD](https://github.com/adafruit/Adafruit-SMT-Breakout-PCBs/blob/master/6-pin%20SOT-23.brd) - Header-to-footprint mapping; IC pin5 uses carrier pad6.
- **S38:** [EdgeTX PPM input decoder](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/targets/common/arm/stm32/trainer_driver.cpp#L77) - Channel and sync timing acceptance used for the proposed waveform.
- **S39:** [Nordic nRF52840 product specification](https://docs-be.nordicsemi.com/bundle/nRF52840_PS_v1.8/raw/resource/enus/nRF52840_PS_v1.8.pdf) - SAADC source resistance and acquisition time.
