# ESP32-S3 controller bench build guide

**Migration pin plan — September 16, 2026.** Use ESP32-S3-DevKitC-1-N8R2 as the
working board, USB powered at first. Simulate and validate drivers before the
physical C0–C7 stages. This document supplies the new bench assignments; the
Feather Rev A PDF is not the schematic for this board. A reviewed ESP schematic,
connection list and wearable power circuit remain required before permanent
assembly.

## C0 — Confirm the board and labels

Label three separate boards **LEFT**, **RIGHT**, **HUB**. Record the actual
DevKit PCB revision, module suffix, flash/PSRAM size and USB-port labels. Use the
Espressif J1/J3 pin numbering below, then verify it against the delivered board.
Clone boards with different headers require their own verified mapping.

All hand sensors share only their own board's 3V3 and GND. BLE is the link
between hand boards and hub; do not join supplies through a hand harness.
For soldering or continuity measurements, remove every power source.

## Active pin assignments

The table is for genuine DevKitC-1 headers. `GPIO1` is the pad marked `1`, not
header position 1. Left and right use identical sensor pins. These selections
avoid boot strapping pins, native USB and memory connections.

| Function | GPIO / ADC channel | DevKit header | Use |
|---|---|---|---|
| Thumb flex | GPIO1 / ADC1_CH0 | J3.4, marked 1 | Each hand |
| Index flex | GPIO2 / ADC1_CH1 | J3.5, marked 2 | Each hand |
| Middle flex | GPIO4 / ADC1_CH3 | J1.4, marked 4 | Each hand |
| Ring flex | GPIO5 / ADC1_CH4 | J1.5, marked 5 | Each hand |
| Little flex | GPIO6 / ADC1_CH5 | J1.6, marked 6 | Each hand |
| ENABLE | GPIO7 | J1.7, marked 7 | Left only, active low |
| CALIBRATE | GPIO7 | J1.7, marked 7 | Hub only, active low |
| External motion SDA | GPIO8 | J1.12, marked 8 | Each hand; configure explicitly |
| External motion SCL | GPIO9 | J1.15, marked 9 | Each hand; configure explicitly |
| Future battery sense | GPIO10 / ADC1_CH9 | J1.16, marked 10 | Reserved; **leave disconnected** |
| Sensor supply | 3V3 | J1.1 or J1.2 | Own local sensor rail |
| Ground | G | J1.22 or J3.1/21/22 | Own local ground |

Reserve GPIO19/20 for native USB and GPIO43/44 for the onboard USB-to-UART
bridge. Do not use GPIO0/3/45/46 for this sensor/button harness; they have
strapping functions. Leave memory pins and board RGB LED pins untouched.
Header mapping: [Espressif DevKitC-1 guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html).
Strapping: [module datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf).

## C1 — One USB-powered flex channel

Build the LEFT thumb first:

```text
LEFT 3V3 ---- flex terminal 1
                 flex sensor
LEFT GPIO1 -- flex terminal 2
      |
      +------ 47 kΩ ------ LEFT GND
      |
      +------ 100 nF ----- LEFT GND
```

The resistor and capacitor are independent parallel branches from the ADC node
to ground. Put the capacitor and resistor near the GPIO connection. The flex
strip has no electrical polarity. If adding a two-pin connector, consistently
assign cavity 1 = local 3V3 and cavity 2 = signal; mark both mating halves and
verify continuity instead of trusting wire colors.

| Bench connection | From | To |
|---|---|---|
| EF-L1-1 | LEFT 3V3 | Flex terminal 1 |
| EF-L1-2 | Flex terminal 2 | LEFT GPIO1 signal node |
| EF-L1-3 | Signal node | 47 kΩ lead 1 |
| EF-L1-4 | 47 kΩ lead 2 | LEFT GND |
| EF-L1-5 | Signal node | 100 nF lead 1 |
| EF-L1-6 | 100 nF lead 2 | LEFT GND |

These `EF-` labels identify this new bench plan, not the old Rev A wire IDs.
Check resistance/continuity unpowered. Then power through the board's
**USB-to-UART port**, with a data cable, and measure 3V3 and the signal node.
At exactly 3.300 V, 25 kΩ flex resistance gives about 2.154 V and 100 kΩ gives
about 1.055 V. These are calculated divider examples, not sensor calibration.

### ESP32 ADC settings and limits

Use ADC1 one-shot acquisition, 12-bit results and the pinned ESP core's high
attenuation setting. Espressif's Arduino API calls this `ADC_11db`; its
ESP32-S3 documented measurement range is 0–3100 mV. Use calibrated millivolt
conversion and compare it with a meter. The newer ESP-IDF attenuation enum name
must be selected from the pinned release, not copied blindly between cores.
[ESP32 ADC API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html).

Keep the signal within local GND–3V3 electrically. The 3.1 V measurement span
is distinct from that electrical boundary. A flex short can push the node to
3V3 and saturate the ADC; treat near-rail readings as faults, not a command.
Never connect 5 V or a LiPo directly to any ADC pin. Do not apply the old nRF
`raw × 3.6 / 4096`, `analogReference(AR_INTERNAL)` or `analogSampleTime()` setup.

Disable GPIO pulls on flex inputs. Allow a provisional 50 ms settling interval
after the supply becomes stable, then validate settling and channel switching.
An unplugged sensor should pull the board-side node toward GND through 47 kΩ;
a broken wire between that node and the MCU may still float. Record raw counts,
calibrated millivolts and measured straight/bent ranges.

## C2 — Five flex inputs and external motion

Repeat the entire resistor/capacitor channel for GPIO2, GPIO4, GPIO5 and GPIO6.
Keep the five signal nodes separate. Use the same scheme on RIGHT later, with
its own rail and ground. Test each channel alone and then alternate high/low
inputs to expose coupling or settling errors.

Use **Adafruit #5543 LSM6DS3TR-C + LIS3MDL**, not a bare sensor chip or assumed
onboard IMU:

| DevKit connection | Breakout connection |
|---|---|
| 3V3 | VIN |
| GND | GND |
| GPIO8 (J1.12) | SDA |
| GPIO9 (J1.15) | SCL |

Leave breakout `3Vo` unconnected. For the initial polled I2C setup leave interrupt pins unconnected
and the address jumpers in their factory positions. The breakout supplies its I2C pull-ups; check the
actual board and do not add another set without reviewing total bus loading.
Default addresses: accelerometer/gyro **0x6A**, magnetometer **0x1C**.
[Breakout pinouts](https://learn.adafruit.com/adafruit-lsm6ds3tr-c-lis3mdl-precision-9-dof-imu?view=all).

Configure SDA/SCL explicitly and begin at 100 kHz. Verify sensor identity
registers using the exact selected drivers before trusting data. Record board
mounting axes. Accelerometer/gyro alone do not establish absolute yaw; magnetic
heading also needs calibration and interference checks. No sensor fixture or
historic Feather result counts as this physical test.

## C3 — ENABLE, then reviewed wearable power

LEFT button, and later HUB CALIBRATE, each use their own GPIO7 network:

```text
local 3V3 -- 10 kΩ --+-- GPIO7
                    |
                    +-- 100 nF -- local GND
                    |
                    +-- 1 kΩ -- normally-open button -- local GND
```

Pressed = low. Configure as input with the fitted external pull-up, then
software-debounce. Require release and deliberate press after boot/fault;
BOOT/GPIO0 is not the gesture-enable button. RIGHT has no extra ENABLE button.

Remain USB powered until a new wearable power schematic is reviewed. DevKitC-1
has no assumed LiPo charger, BAT socket or factory battery divider. Its RST/EN
resets/disables the ESP chip; it is not the Feather regulator-EN switch and is
not a battery disconnect. GPIO10 remains disconnected until a correctly scaled
external battery monitor is designed. Review charging, regulation/current peaks,
USB coexistence, switch placement and low-battery behavior before fitting a cell.

Mount sensors with strain relief and leave flex sensing lengths free to move.
The large DevKit is a bench reference; any later compact carrier/board is a
separate pin/power/mechanical revision. C3 cannot pass until power and wearability
are actually qualified.

## C4–C7 — Right hand, hub and host

- **C4:** repeat five inputs, external motion, reviewed power and calibration on
  RIGHT; assign its own immutable side/device identity.
- **C5:** use an ESP32-S3 hub with GPIO7 CALIBRATE and USB power. It needs no flex
  divider or IMU. Validate two simultaneous BLE peripheral connections.
- **C6:** first qualify UART0 byte transport through the actual onboard
  USB-to-UART bridge. The simulator may expose UART over TCP; label that adapter.
  Native USB is an alternative needing its own driver/model test. Independently
  decode commands, reject stale/corrupt data and require deliberate recovery.
- **C7:** complete [validation](validation.md) and archive actual firmware,
  calibration, transport, measurements and wiring revision. Drone mechanics and
  rendering follow controller completion.

## Superseded wiring

Do not translate Feather A0/D5/A6 labels by position. The historical
[Rev A PDF/SVG/netlist](../../hardware/schematics/README.md) remains a record of
the nRF circuit only. Its battery/charger/EN and onboard IMU connections do not
apply to these ESP boards. Optional PPM/Pocket circuitry has no assigned ESP
pins in this baseline and is outside C7.
