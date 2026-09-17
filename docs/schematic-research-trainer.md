# Ground hub to RadioMaster Pocket trainer — research and proposed circuit

> **Archived Rev A research — superseded 2026-09-16.** The active goals are (1) simulate the hand controller in Simantic, then build its physical prototype, and (2) model the drone hardware/microcontroller in Simantic and feed its actuator outputs into an on-screen mechanical simulation. There is no physical drone build or flight phase. Pocket, ELRS and a trainer interface are not required.
>
> Follow the [project goals](../README.md) and [current architecture](architecture.md). The original September 14 research below is retained for provenance, including its historical BOM, wiring and test instructions; those are not an active procurement or implementation checklist.

## Retained September 14 research

Date: 2026-09-14. Scope: current BOM H02 Adafruit Feather nRF52840 Express #4062, H10 interface, and Pocket ELRS/FCC. This is a complete **bench prototype circuit**, with one explicitly open qualification item: the Pocket's jack electrical input limits are not published in the official sources located. Keep JP301 open until the received radio's input interface has been verified. These are source findings/design choices, not instructions copied from the BOM.

## 1. What is established and what is assumed

- The Pocket A1.8 manual labels a **DSC Trainer Port** and a separate **3.5 Audio Jack**. Use DSC, not headphones. The manual also identifies SE as the momentary switch and separate radio batteries/charging. [RadioMaster Pocket A1.8 manual, first English sheet](https://cdn.shopify.com/s/files/1/0701/8066/7584/files/Pocket_A1.8.pdf?v=1770617495).
- RadioMaster's official trainer support article recommends a **3.5 mm mono TS plug**, with PPM at the tip and ground at the sleeve. Its image labels A = ground, B = insertion detection, C = PPM; A and B touch the same long sleeve of the pictured mono plug. The unused connector contact D is not wired. This manufacturer family article dates to 2020, before Pocket, so it establishes the expected RadioMaster interface; it is not a Pocket-specific schematic. [Official trainer pinout](https://radiomasterrc.freshdesk.com/support/solutions/articles/64000256682-trainer-port-pin-out).
- Do not use the radio's 6.6–8.4 V operating-battery rating as a trainer signal rating. The Pocket manual and trainer support page do **not** specify jack VIH/VIL, permitted injected current, pull resistors, or absolute maximum voltage. A 3.3 V waveform is the selected conservative bench starting point, not a manufacturer-verified operating limit.
- EdgeTX's Pocket target routes the trainer input to PC8/TIM3 channel 3, output to PC9/channel 4, and inverted insertion detection to PA8. This confirms a capture-input path, but cannot reveal conditioning components between the jack and MCU. [EdgeTX hal.h at inspected commit](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/targets/taranis/hal.h#L492).
- Hub pin identities D5 = P1.08, D6 = P0.07 and D9 = P0.26 are confirmed by Adafruit's board variant. [Adafruit Feather Express variant](https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/variants/feather_nrf52840_express/variant.cpp). The Feather's 3V header is the regulator output and EN pulled to ground disables it. [Adafruit pinouts](https://learn.adafruit.com/introducing-the-adafruit-nrf52840-feather/pinouts).

## 2. Proposed physical circuit: all terminals

All GND connections in this section are **HUB_GND**. HUB_GND and radio signal ground become connected by the trainer cable. No aircraft ground or power wire crosses the radio link. The buffer is not galvanic isolation.

| Ref | Selected part / value | Terminal 1 | Terminal 2 / other terminals |
|---|---|---|---|
| U301 | Texas Instruments SN74LVC1G125DBVR, SOT-23-5 | pin 1 `/OE`: HUB_D9 + R301.2 | pin 2 `A`: HUB_D5 + R302.1; pin 3 GND: HUB_GND; pin 4 `Y`: R303.1; pin 5 VCC: HUB_3V3 |
| R301 | 10 kΩ, 1%, ≥0.125 W | HUB_3V3 | U301.1 `/OE` and Feather D9 |
| R302 | 100 kΩ, 1%, ≥0.125 W | U301.2 `A` and Feather D5 | HUB_GND |
| R303 | 1 kΩ, 1%, ≥0.125 W | U301.4 `Y` | JP301.1 |
| C301 | 100 nF ceramic X7R, ≥10 V | U301.5 VCC / HUB_3V3 | U301.3 GND; place close to IC |
| JP301 | 2-pin 2.54 mm header + removable shunt | R303.2; add TP301 here | Cable signal conductor; add TP302 here; **leave shunt removed until verification** |
| J301 | Cable-end male 3.5 mm **TS mono** plug | TIP: JP301.2 through signal conductor | SLEEVE: HUB_GND through return/shield conductor |
| H02 | Feather nRF52840 Express #4062 | `3V`: HUB_3V3; `GND`: HUB_GND | `5` (D5): U301.2; `9` (D9): U301.1 |

No capacitor is fitted from the PPM output to ground: it would slow/distort edges. No pull-up is fitted from the cable tip to the Feather supply. No connection is made from the radio to Feather BAT, USB, 3V or EN. A shielded cable with signal and ground, approximately 0.3–0.5 m for the bench prototype, is a design choice; its loaded waveform must be checked.

```
 Feather #4062                       SN74LVC1G125DBVR
 3V ---------+-------------------------- 5 VCC
             +--- R301 10k ---+--------- 1 /OE
                             |
 D9 -------------------------+
 D5 -------------------------+--------- 2 A
                             |
                         R302 100k
                             |
 GND ------------------------+--------- 3 GND
   |                                      4 Y -- R303 1k -- JP301 -- TIP (DSC)
   +--------------------------------------------------------------- SLEEVE
             C301 100nF directly between pins 5 and 3
```

The buffer gives a separate replaceable line driver, reset-time disable, and specified Ioff power-off behavior. It does not make an unknown radio input electrically qualified. The series resistor limits fault/short current (about 3.3 mA for an ideal 3.3 V output shorted to ground); it is not a substitute for an input-voltage specification. [TI datasheet, pin functions and operating description](https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf).

### Carrier board: avoid the pin-5/pad-6 mistake

The SOT-23 board in **Adafruit #1230** supports SOT-23-5 and SOT-23-6 with 2.54 mm header holes. Use the 6-pad front, not the transistor back. With the board's `SOT23` text at the bottom and the IC viewed from above:

| Upper/middle/lower | Left row | Right row |
|---|---|---|
| Upper | U301 pin 1 `/OE` | U301 pin 5 `VCC` |
| Middle | U301 pin 2 `A` | EMPTY — no U301 leg here |
| Lower | U301 pin 3 `GND` | U301 pin 4 `Y` |

The six-pad footprint numbers run left 1–2–3 and right 6–5–4. Therefore **five-pin IC pin 5 lands on carrier footprint pad 6**, and footprint pad 5 is unused. In the official Eagle board, pad 1→JP2.1, pad 2→JP2.2, pad 3→JP2.3, pad 4→JP1.3, pad 5→JP1.2, pad 6→JP1.1. The actual board has no numbered header labels; verify continuity from each IC leg to its intended header before installing it. Do not assume adapter-hole numbers equal IC pin numbers. [Adafruit product #1230](https://www.adafruit.com/product/1230), [official carrier CAD](https://github.com/adafruit/Adafruit-SMT-Breakout-PCBs/blob/master/6-pin%20SOT-23.brd).

H06 button allocation coordinated with hand schematic: left-hand D5 = hold-to-enable; hub D6 = calibration; hub D5 = PPM; hub D9 = buffer enable. All three Feathers use EN-to-GND power-disable switches. The hub's D6 button has an external 10 kΩ pull-up and 1 kΩ series lead as specified in the hand-node research. No pin conflict.

## 3. PPM waveform design for firmware

Chosen protocol, not existing implemented firmware:

- AETR channel order: TR1 = aileron/roll, TR2 = elevator/pitch, TR3 = throttle, TR4 = rudder/yaw. The radio must map these explicitly; do not rely on its default order.
- TR5 = hand-data-valid: 1000 µs invalid, 2000 µs valid. TR6 = health heartbeat: alternate 1000/2000 µs every **two freshly generated frames**, with fresh validated data from both hand nodes. Optional TR7/TR8 = fixed 1500 µs to make an 8-channel frame. **TR5 is trainer validity, not the ELRS arm channel.**
- Fixed frame period 22,500 µs; marker pulse 300 µs; channel edge-to-edge interval 1000–2000 µs; centers 1500 µs. For active-high PPM, hold HIGH 300 µs, then LOW `channel_us − 300` before the next marker. Add the final marker and low sync interval so the last-marker-to-next-frame-marker interval equals `22,500 − sum(channel_us)`.
- Eight channels at 2000 µs each leave a sync edge interval 6500 µs; all at 1000 leave 14,500 µs. These are inside the inspected EdgeTX decoder's sync interval `>4000 && <19000`; decoded channel intervals must be 800–2200 µs. This is compatible timing by source inspection, not a measured radio test. [EdgeTX input decoder](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/targets/common/arm/stm32/trainer_driver.cpp#L77).
- Constant-width marker edges yield the same channel spacing if polarity is inverted. Start with positive markers and confirm exact received values; the jack circuit may invert the waveform. The software input driver uses input capture, not UART data. [EdgeTX timer input setup](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/targets/common/arm/stm32/stm32_pulse_driver.cpp#L360).
- Use hardware-timed output with a finite frame lifecycle. Do not indefinitely repeat a DMA/PWM buffer containing old commands and an apparently alive heartbeat. Heartbeat advancement and valid=1 require new checked application data. On a detected stale BLE source, send valid=0 immediately on the next complete frame and freeze heartbeat; the radio gate returns authority to manual inputs. Have a separately serviced MCU watchdog and start disabled after resets.
- Boot sequence: `/OE` remains HIGH through R301; initialize D9 HIGH, D5 LOW, application checks, then begin a complete invalid frame stream; only drive D9 LOW once timing is ready. Enable valid data only after both sensors, identity, sequence numbers, age, calibration and physical enable pass. A process crash must not hold live output indefinitely.

At 1000/2000 µs the inspected decoder produces roughly ±97.7% at 100% weighting because it scales 500 to a nominal full range 512. Calibrate and check actual receiver endpoints in the FC; adjust EdgeTX weight or endpoints as required. Do not silently substitute 988/2012 µs throughout the firmware without updating these timing checks.

## 4. Trainer authority and dropout: critical finding

The inspected EdgeTX `trainer.cpp` sets a **100 × 10 ms = 1 second** trainer-valid timeout and announces loss when it expires. Stopping PPM alone therefore does not provide immediate fallback. A live PPM stream repeating stale commands may remain valid indefinitely. [EdgeTX trainer-valid timer](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/trainer.cpp#L23).

Set the Pocket model to **Master/Jack**. Use the radio-level trainer table to replace just Ail/Ele/Thr/Rud from TR1–TR4 and calibrate neutral. Keep arm and flight-mode switches sourced from Pocket switches in the radio output mixes. Release of the Pocket SE momentary switch must remove gesture authority regardless of hub behavior. Arm must never depend on a finger gesture alone. [EdgeTX trainer model setup](https://manual.edgetx.org/v2.8/edgetx-user-manual/user-manual-for-color-screen-radios/model-settings/model-setup/trainer), [monochrome trainer settings](https://manual.edgetx.org/bw-radios/radio-settings/trainer).

Required software gate, expressed independently of UI numbering:

```
gesture_authority = SE_held
                 AND trainer_link_active
                 AND (TR5 > +50%)
                 AND heartbeat_changed_recently
                 AND no_latched_fault
```

One bench configuration candidate for stale-heartbeat detection uses two logical switches: `TR6 > 0` with delay 0.1 s and duration 0; `TR6 < 0` with delay 0.1 s and duration 0. OR them to form heartbeat_stuck. A healthy 45 ms half-cycle should prevent either delay completing. Unlike a duration pulse from a difference trigger, these delayed level checks do not rely on retrigger behavior. EdgeTX's source resets a pending delay when its expression becomes false. This gate still needs **radio bench validation**, including scheduling resolution, reconnection behavior, malformed input and startup. [Logical-switch manual](https://manual.edgetx.org/bw-radios/model-select/logical-switches), [delay evaluation source](https://github.com/EdgeTX/edgetx/blob/346c837d77d23932d860fe8b4c794b3f6ba074fb/radio/src/switches.cpp#L643).

Use a latched authority fault so a recovered hub cannot automatically resume gestures while SE remains held; release SE and deliberately re-enable. Exact final EdgeTX model configuration and wearable/hub firmware are separate deliverables still required. A schematic alone cannot provide these behaviors. Manual takeover can change throttle abruptly if the manual stick and gesture throttle differ; match positions/qualify transfer behavior with props removed. Do not claim automatic failure response within 100 ms until measured.

## 5. Verification record before closing JP301

1. Batteries/USB unplugged: inspect board revision; verify plug TIP/SLEEVE continuity to the two cable conductors and verify no short. Confirm it is a mono TS plug in the DSC port. A TRS headphone cable is not the selected build.
2. Keep JP301 open, radio disconnected. Power hub from its LiPo. Verify U301 pins 5–3 ≈3.3 V, `/OE` HIGH at reset, and no output PPM until explicitly enabled. Inspect waveform at TP301 with an oscilloscope/logic analyzer sharing HUB_GND; measure periods, levels, and malformed frame recovery. Repeat resets and simulated stale data.
3. Confirm the actual Pocket trainer-input electrical specification from RadioMaster or a competent circuit-level examination/measurement. A DMM reading of idle voltage alone cannot establish a safe VIH/absolute maximum or prove acceptance. For a reference waveform, the radio's own Slave/Jack output may be observed with a high-impedance scope and the hub disconnected; it is useful evidence, not proof of input tolerance. Return radio to Master/Jack before injection.
4. If 3.3 V signaling is confirmed compatible, close JP301 with both devices off, connect sleeve/ground and tip, then power radio and hub. Check TP302 loaded levels and all received channel values. If it does not decode at 3.3 V, do not raise to 5 V without an actual input specification.
5. Props removed: test physical SE takeover, each hand off/disconnected/stale, hub off/reset/frozen, stopped PPM, repeated valid old frame, heartbeat stuck HIGH/LOW, cable disconnected, partial bad frames, and radio restart. Log time from failure to manual authority at FC output. Check arm/mode remain from the radio.
6. Use a radio operator for initial gesture trials; establish ordinary manual flight control first. The current BOM supplies a proposed custom architecture, not firmware already demonstrating autonomous safe handling.

## Research evidence files

Local source copies reviewed: `/tmp/palmpilot-trainer_driver.cpp`, `/tmp/palmpilot-stm32_pulse_driver.cpp`, `/tmp/palmpilot-trainer.cpp`, `/tmp/palmpilot-hal.h`, `/tmp/palmpilot-switches.cpp`, `/tmp/palmpilot-sot23-breakout.brd`, `/tmp/palmpilot-trainer-plug.png`. These temporary files support the research; the permanent URLs above are the deliverable references. EdgeTX inspected commit: `346c837d77d23932d860fe8b4c794b3f6ba074fb`. Installed radio firmware version is unknown and must be recorded/tested.
