# Aircraft schematic review — 2026-09-14

> **Archived review snapshot — superseded 2026-09-16.** These findings concern an intermediate September 14 Rev A drawing generator. They are not current build tasks or proof of testing. The [Rev A package](../hardware/schematics/rev-a/README.md) is also an archived full-system record.
>
> Current work is controller simulation in Simantic, then a physical controller prototype, followed by virtual drone hardware/microcontroller outputs driving an on-screen mechanical simulation. Physical aircraft, Pocket/ELRS and trainer construction are outside the required scope. Use the [project goals](../README.md), [current architecture](architecture.md) and [controller validation](controller/validation.md). The original review below retains historical “required” and “current” wording only as part of that record.

Reviewed `tools/build_palmpilot_schematic.py` while root author was adding connector/motor/firmware sheets. Scope was P/E/A/M connection records, `aircraft_power`, `peripheral_page`, and aircraft sources S02–S08. This is a source/code review, not physical electrical testing or a rendered-layout review. Parent reported label corrections in progress; findings below describe the snapshot inspected.

## Findings to close before delivery

| Priority | Location | Finding and correction |
|---|---|---|
| Required, already in progress | `PERIPHERALS`, `peripheral_page` | Matek supply **pin name is 5V**, not `4-9V`. The latter is the allowed input range, not the board marking. Change all endpoints and visual labels consistently. |
| Required, already in progress | Dronetag A11/A12 and visual U5 | Use manufacturer **4-pin connector pin1 VCC → FC5V; pin4 GND → FCG**. Pins2 RX/3 TX individually insulated NC; separate3-pin connector empty. Current generic IN/G plus “R/T/reserved” merges two different connectors and must be replaced. |
| Required, already in progress | Finder A15 and visual BZ1 | Finder terminal is **BZ**, connected to FC Z−. BZ− is a common FC-side label, not this Finder connector's published label. Correct both schedule and explanatory box. |
| Required | `peripheral_page` text near USB/microSD | Delete “GPS PPS pad: NC.” Selected M10Q has a PPS LED; manufacturer photos show utility pads **3.3, G, RST**, not an exposed PPS pad. State that the unused second GH socket and utility pads remain unconnected. |
| Required | Source register S05/S07/S08 | Replace outdated/unverified URLs with exact current manufacturer links in next section. Remove S07 note “Verify final URL” and wrong IN/G wording. Source S08 note should use BZ, not BZ−. |
| Recommended for easy assembly | A05–A10 cable description | User will likely cut one end of the supplied Matek GH cable. Current proposed white GPS-TX, blue GPS-RX and yellow SDA differ from manufacturer supplied-cable photo. Prefer actual photo mapping: **red5V, yellowRX, blueTX, greenCL, whiteDA, blackG**. Treat wire colors as expected, verify actual cable function. |
| Recommended completeness | `WIRES` and connection-list output | Add three RF connection records: RP1U.FL→included65mm2.4GHzT antenna; Dronetag BT U.FL→short black wire antenna; Dronetag GNSS U.FL→long grey wire antenna. Current schematic text mentions them, but they are absent from the full connection list. These are cable assemblies, not soldered signal wires. |
| Verify in new connector sheets | Contact numbers | A1–A8 ESC index is a project contact index tied to the displayed board view, not a manufacturer-declared connector pin numbering standard. Same caution for Matek GH positions. Dronetag **does** explicitly publish manufacturer pins1–4. Label viewpoints and distinguish these cases. |
| Verify in new motor sheets | Photo orientation versus aircraft front | In the official ESC photo, battery tabs left, connector right, banks are M3 upper-left/M4 upper-right/M1 lower-left/M2 lower-right. Selected aircraft layout M1RR/M2FR/M3RL/M4FL corresponds to rotating that photo90° counterclockwise (battery tabs to aircraft rear, connector to aircraft front), if motor leads take the nearest bank. Any other board rotation needs correctly routed leads. FC orientation arrow is independently forward. Do not treat “top of ESC photo” as aircraft front. |

## Correct source links

- **S02 verified valid:** [Holybro Kakute H7 v1.5 stack](https://holybro.com/products/kakute-h7-v1-stacks). Current page identifies11091+31102 and v1.5 sensors/5V2A rail.
- **S03 verified valid, older schematic details:** [Holybro H7 pinout](https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-v1/pinout). Cite current v1.5 image alongside it because text includes old1.5A rail figure.
- **S04 verified valid:** [Tekko32 F4 4in1 50A AM32](https://holybro.com/products/tekko32-f4-4in1-50a-esc).
- **S05 replacement:** [RadioMaster RP1 V2](https://radiomasterrc.com/products/rp1-expresslrs-2-4ghz-nano-receiver); [official manual](https://cdn.shopify.com/s/files/1/0609/8324/7079/files/RP1_User_Manual.pdf?v=1722923320).
- **S06 verified:** [Matek M10Q-5883](https://www.mateksys.com/?portfolio=m10q-5883). Web opener returned403, but direct official HTML download and search crawl succeeded; local evidence is saved.
- **S07 replacement:** [Dronetag BS gen.2 power-source installation](https://help.dronetag.com/dronetag-bs-gen2/power-source-installation/). [Board receptacle front-view pin numbering](https://help.dronetag.com/img/dronetag-bs/4pin-diagram.jpg) is reused by manufacturer's gen.2 page and labels1–4 left-to-right.
- **S08 replacement:** [VIFLY Finder2](https://viflydrone.com/products/vifly-finder-v2-fpv-racing-drone-buzzer); [manufacturer wiring diagram](https://cdn.shopify.com/s/files/1/0690/1035/8568/products/vifly-drone-finder2-drone-buzzer_5.jpg?v=1672647144).
- Include **Holybro current scale** as a named source when calibration sheet is added: [ESC current-sensor scale](https://docs.holybro.com/esc/current-sensor-scale).
- Include **Dronetag antenna identification** if source list must directly cover every cable: [BS gen.2 enclosure/antennas](https://help.dronetag.com/dronetag-bs-gen2/enclosure-installation/).

## Electrical coverage confirmed

- P01/P02 correctly send battery to ESC heavy pads, bypassing small FC wiring. Capacitor is parallel and polarity is correct.
- Eight E records match exact official function order: VBAT/B+, TLM/R7, GND, CURRENT, M1–M4. TLM and current are distinct.
- RP1 uses correct crossed full-duplex UART3 and regulated5V.
- Matek uses correct crossed UART4 plus separate I²C SCL/SDA and regulated5V.
- Finder uses separate steady ground and switched negative buzzer control.
- Dronetag can operate with only power connected because it has its own GNSS; it does not need Matek navigation data for this baseline wiring.
- Twelve motor phase wires are all represented. Artificial U/V/W labels are explicitly identified as build labels, appropriate for unmarked3-phase motor leads.
- No missing active aircraft power/data conductor was found after the specific endpoint label fixes above.
- Shared5V/G nodes are electrically valid as drawn. If a distribution joint is used instead of separate FC pads, describe the real feeder/pigtail on its assembly detail so “every wire” remains literal.
- 5V branch load and power-up behavior need measurement; firmware sensor support and ESC PCB revision/current scale remain properly unresolved until received parts are checked.

## Review limits

ArduPilot parameters, new motor-test-letter sheet, final connector sheets and final rendered PDF were still being authored and are outside this snapshot's verification. No flight-readiness conclusion is implied.
