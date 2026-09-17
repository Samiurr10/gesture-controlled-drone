# Hand schematic review

> **Archived review snapshot — superseded 2026-09-16.** These findings concern an intermediate September 14 Rev A drawing generator. They are not current build tasks or proof of testing. The [Rev A package](../hardware/schematics/rev-a/README.md) is also an archived full-system record.
>
> Current work is controller simulation in Simantic, then a physical controller prototype, followed by virtual drone hardware/microcontroller outputs driving an on-screen mechanical simulation. Physical aircraft, Pocket/ELRS and trainer construction are outside the required scope. Use the [project goals](../README.md), [current architecture](architecture.md) and [controller validation](controller/validation.md). The original review below retains historical “required” and “current” wording only as part of that record.

Reviewed 2026-09-14 against `tools/build_palmpilot_schematic.py` and the source-linked `docs/schematic-research-hands.md`. The builder was still being extended during the initial review. Findings concern assembly clarity and consistency as well as electrical connectivity; no hardware testing is implied.

## Initial code-review findings

1. **Clarify every ADC/ground crossing on the two hand drawings.** At x=555, each horizontal ADC signal crosses the vertical local ground bus. Junction dots are absent, so the intended circuit has no connection at those five crossings; this is electrically conventional but easy for the intended beginner builder to misread. Add bridge/gap notation and a legend, or replace the vertical ground trunk with separate labeled local ground symbols. Connecting any such crossing would short that ADC to ground.
2. **Make the board endpoints of the sensor power buses visible.** The hand drawings label `L_3V`, `L_GND`, `R_3V`, `R_GND`, but the Feather rectangle presently exposes only A0–A4. Add explicit `U6 3V` / `U6 GND` and `U7 3V` / `U7 GND` at the bus heads or draw equivalent pin stubs. The table/netlist does give the correct endpoints; this change makes the schematic itself complete enough to follow.
3. **Label power-sheet ground symbols by domain.** The three EN switches presently terminate in generic ground symbols within separate cards. Label these `L_GND`, `R_GND`, `H_GND` to avoid a visual implication that the independently powered boards share a ground conductor.
4. **Correct source S14.** The URL ending `cores/nRF5/wiring_analog.cpp` now contains analogWrite/PWM implementation. Use `cores/nRF5/wiring_analog_nRF52.c` for `analogReadResolution`, `analogReference`, `analogSampleTime` and ADC defaults. Correct full URL: https://github.com/adafruit/Adafruit_nRF52_Arduino/blob/master/cores/nRF5/wiring_analog_nRF52.c.
5. **Synchronize both button descriptions and wire records with the planned passive circuit.** Initial builder still uses direct switches and `INPUT_PULLUP`; root is already replacing this. Final diagram, text, connection list and additions list should all show each GPIO with a local 10k pull-up, 100nF shunt capacitor and 1k series connection to its normally-open button. Two additional 10k resistors, two 1k resistors and two 100nF capacitors are required. With that circuit, pressed GPIO is nominally 0.30V, and GPIO should be configured as input rather than relying on an internal pull-up.

## Confirmed correct in initial builder

- Ten independent flex circuits, five per hand; each has one 47k shunt and one 100nF shunt, placed at the ADC end.
- Thumb/index/middle/ring/little map to A0/A1/A2/A3/A4 on both boards, with P0.04/P0.05/P0.30/P0.28/P0.02 mappings correct.
- Divider orientation is 3V → flex → ADC node → 47k → local GND. Capacitor parallels the 47k. The flex-strip terminal order is nonpolar.
- Netlist expands every channel into six records and explicitly returns resistor/capacitor ground to its own board.
- Three protected 1S batteries feed their own boards through supplied JST plugs. Batteries are not joined in series or parallel.
- EN switches close to local ground for regulator OFF; open enables the regulator. The unused SPDT throw is NC. The drawings correctly explain that this is not full battery/USB isolation.
- Left D5 hold-to-enable and hub D6 calibration do not conflict with hub D5 waveform and D9 buffer-enable allocation.
- A5 is spare and A6 factory battery monitoring. No external IMU wiring is needed.
- 25k/100k flex examples calculate to approximately 2.154V/1.055V. Open-sensor and shorted-flex end states are directionally correct.
- Explicit 12-bit resolution, internal nominal 3.6V conversion span and 10µs acquisition setup are correct. The physical analog pin must still remain between its local GND and VDD.

## Counts for final reconciliation

| Item | Hand + button total | Notes |
|---|---:|---|
| Sense boards | 2 | One per hand |
| Express boards | 1 | Hub |
| Flex sensors | 10 | Five per hand |
| Keyed flex mating connector pairs | 10 | Separate optional button connector pairs are additional |
| 47k resistors | 10 | One per ADC channel |
| 100nF sensor capacitors | 10 | One per ADC channel |
| 10k button pull-ups | 2 | Trainer /OE pull-up is additional |
| 1k button series resistors | 2 | Trainer output series resistor is additional |
| 100nF button capacitors | 2 | Trainer buffer bypass capacitor is additional |
| Protected 1S 500mAh batteries | 3 | One per board |
| Maintained power switches | 3 | EN-to-own-GND |
| External normally-open pushbuttons | 2 | Left enable and hub calibrate |

## Visual review status

Pending generated SVG/PDF sheets. The checks above reviewed drawing coordinates and connection-list generation in source; final rendered artifacts must be checked after the root completes the button sheet and rerenders.
