# Research Sources

Research completed: 2026-09-09

## Method

The design uses manufacturer product pages, manufacturer datasheets/manuals,
and official PX4/Espressif/TBS documentation. Retail availability was accepted
only from the manufacturer or its current official storefront. Marketplace
listings and forum claims were not used to lock hardware.

Availability, price, inventory, and firmware status are time-sensitive. They
are recorded to make the decision auditable, not guaranteed for a future order.
Where official pages conflict, the design either uses the more conservative
value or creates a receiving-inspection gate.

## Source 1

[Seeed Studio: Getting Started with XIAO ESP32-C3](https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/)

Supports the XIAO selection, 160 MHz ESP32-C3, BLE 5, 400 KB SRAM, 4 MB flash,
pin capabilities, charging information, strapping-pin caution, and Seeed's
external 5 V diode guidance.

## Source 2

[Espressif ESP-IDF v5.4.4: BLE Connection](https://docs.espressif.com/projects/esp-idf/en/v5.4.4/esp32c3/api-guides/ble/get-started/ble-connection.html)

Primary reference for BLE connection interval, peripheral latency, supervision
timeout, roles, and negotiated connection behavior.

## Source 3

[Espressif ESP-IDF: ESP32-C3 BLE GAP API](https://docs.espressif.com/projects/esp-idf/en/v4.4.5/esp32c3/api-reference/bluetooth/esp_gap_ble.html)

Primary implementation reference for BLE security parameters, bonding,
authentication, encryption, allowlisting, and connection events. The eventual
firmware must use the matching API for its pinned ESP-IDF version.

## Source 4

[CEVA: BNO080/BNO085 Datasheet](https://www.ceva-ip.com/wp-content/uploads/BNO080_085-Datasheet.pdf)

Primary sensor reference for BNO085 interfaces, modes, electrical behavior,
reports, and UART-RVC framing requirements.

## Source 5

[Adafruit: BNO085 Product Guide](https://learn.adafruit.com/adafruit-9-dof-orientation-imu-fusion-breakout-bno085?view=all)

Breakout-level wiring and mode reference. The guide also documents the known
BNO08x I2C interoperability problem.

## Source 6

[Adafruit BNO085 guide: I2C compatibility warning](https://learn.adafruit.com/adafruit-9-dof-orientation-imu-fusion-breakout-bno085?view=all)

Adafruit states that BNO08x I2C behavior does not work well with Espressif
ESP32-family devices. This is why the selected hand interface is UART-RVC, not
the provisional I2C design.

## Source 7

[Adafruit: BNO085 UART-RVC for Arduino](https://learn.adafruit.com/adafruit-9-dof-orientation-imu-fusion-breakout-bno085/uart-rvc-for-arduino)

Reference for the 115200-baud UART-RVC mode and yaw/pitch/roll plus acceleration
output. The project parses the protocol under ESP-IDF rather than requiring the
Arduino example at runtime.

## Source 8

[Espressif: ESP32-C3 Datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf)

Primary SoC reference for electrical limits, strapping pins, UART/ADC resources,
radio, memory, and power behavior. Board-level limits still come from Seeed.

## Source 9

[Holybro Store: Kakute H7 Mini](https://holybro.com/products/kakute-h7-mini)

Current manufacturer listing. At the research date, v1.5 with ICM-42688-P was
available at $58.99. The page lists STM32H743 at 480 MHz, SPA06 barometer, six
UARTs, 128 Mbit flash, 2S-6S input, 20 x 20 mm mounting, 31 x 30 x 6 mm size,
and 5.5 g mass.

## Source 10

[PX4 v1.17: Holybro Kakute H7 Mini](https://docs.px4.io/v1.17/en/flight_controller/kakuteh7mini)

Official PX4 board support, serial-port mapping, bootloader requirement,
`holybro_kakuteh7mini_default` build target, external-magnetometer note, and
v1.14-or-newer support statement.

## Source 11

[T-HOBBY official store: V45A Lite 6S Four-in-One ESC](https://www.t-hobby.com/products/v45a-lite-6s-4in1-esc)

Current official listing. At the research date it reported the item in stock
and listed 3-6S input, 45 A continuous, 55 A/10 s peak, BLHeli_S, 30.5 x 30.5 mm
mounting, approximately 13 g, 41.6 x 39.4 x 6.3 mm, and no ESC telemetry.

## Source 12

[T-Motor official store: F1204 5000KV/6500KV Motor](https://store.tmotor.com/goods-1147-F1204.html)

Manufacturer motor selection and thrust data. The selected 5000KV version is
rated for 2-3S, weighs 6.1 g without cable, uses a 1.5 mm shaft, and is listed at
6 A peak/60 s and 72 W. Its GF2540/3S test data is used only for preliminary
sizing; the team's actual propeller must be tested.

## Source 13

[PX4 v1.17: ARK SAM GPS](https://docs.px4.io/v1.17/en/gps_compass/ark_sam_gps)

Official PX4 integration reference for the u-blox SAM-M10Q, IIS2MDC compass,
5 V power at 15 mA average/20 mA maximum, six-pin UART/I2C signals, mounting,
and configuration.

## Source 14

[ARK Electronics: ARK SAM GPS Mini](https://arkelectron.com/product/ark-sam-gps-mini/)

Current manufacturer product and availability page. At the research date it was
listed in stock at $75, 8 g, and 32.25 x 16 x 8 mm. The page and PX4 page differ
in connector-family wording, so the receiving inspection verifies the included
cable rather than relying on the connector name.

## Source 15

[PX4 v1.17 Release Documentation](https://docs.px4.io/main/en/releases/1.17)

Official release baseline used to pin flight firmware rather than follow a
moving development branch.

## Source 16

[PX4 v1.17: CRSF Telemetry](https://docs.px4.io/v1.17/en/telemetry/crsf_telemetry)

Official CRSF build, wiring, and parameter instructions. It states that CRSF is
not included by default, directs users to remove `rc_input` and enable
`crsf_rc`, and documents `RC_CRSF_PRT_CFG`, port unmapping, telemetry enable,
and ExpressLRS wiring.

## Source 17

[TBS: Official CRSF Protocol Specification](https://github.com/tbs-fpv/tbs-crsf-spec/blob/main/crsf.md)

Protocol authority for 420000-baud serial behavior, frame structure, packed RC
channels, addresses, lengths, CRC8 polynomial, and conversion/test vectors.

## Source 18

[PX4 v1.17: Safety Configuration and Failsafes](https://docs.px4.io/v1.17/en/config/safety)

Official reference for manual-control loss, failsafe actions, action delay,
position loss, and interaction of safety conditions. Parameter behavior must be
confirmed on the pinned build.

## Source 19

[PX4 v1.17: Geofence](https://docs.px4.io/v1.17/en/flying/geofence)

Official reference for distance/height fences, polygonal regions, actions,
source selection, and multicopter stopping-distance margin.

## Source 20

[PX4 v1.17: Multicopter Position Mode](https://docs.px4.io/v1.17/en/flight_modes_mc/position)

Official behavior for centered position hold, roll/pitch acceleration command,
vertical speed, yaw rate, required global position, `MPC_ACC_HOR_MAX`,
`MPC_VEL_MANUAL`, and vertical-speed parameters.

## Source 21

[PX4 v1.17: Flight Modes and RC Switches](https://docs.px4.io/v1.17/en/config/flight_mode)

Official QGroundControl/PX4 reference for flight-mode, arm, and kill switch
assignment. It distinguishes immediate kill from a controlled failsafe and
warns that a flying multicopter falls when motors are killed.

## Source 22

[Tattu: 450 mAh 3S 75C XT30 LiPo](https://genstattu.com/tattu-450mah-11-1v-75c-3s1p-lipo-battery-pack-with-xt30-plug.html)

Manufacturer product baseline for 3S/11.1 V, 450 mAh, 75C, XT30 discharge,
JST-XHR-4P balance connector, 45 x 24 x 21 mm dimensions, and listed 42 g
weight. C-rating is treated as a label, not a substitute for sag testing.

## Source 23

[ISDT: 608AC Charger](https://www.isdt.co/608ac.html?lang=en)

Manufacturer charger reference for AC/DC operation, 1-6S lithium support,
balance charging, and adjustable current. The selected 450 mAh pack starts at a
0.45 A (1C) balance charge unless the battery manufacturer requires less.

## Source 24

[Adafruit: Protected 3.7 V 500 mAh LiPo, Product 1578](https://www.adafruit.com/product/1578)

Controller-battery option. The design requires receiving inspection and
polarity verification before adapting its JST-PH connector to XIAO battery
pads.

## Source 25

[Adafruit: Mini 2-Axis Analog Thumbstick, Product 2765](https://www.adafruit.com/product/2765)

Current hand-control component: two self-centering 10 kohm potentiometers used
for vertical speed and yaw.

## Source 26

[Holybro Documentation: Kakute H7 Mini Pinout](https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-mini/pinout)

Primary connector/pad map for the H7, including ESC port, VTX/TELEM1 signals,
I2C, UARTs, 5 V and 3.3 V limits, motor outputs, and buzzer. This page lists the
5 V output at 1.5 A while the store page lists 2 A; the design uses 1.5 A until
the exact received revision is verified.

## Source 27

[Hobbywing official search: XRotor Nano 20A Four-in-One](https://www.hobbywing.com/en/Search?keys=XRotor)

The official manufacturer site marks the previously considered 2-4S XRotor
Nano 20A product discontinued. It is documented here to explain why it was
removed from the selected BOM.

## Source 28

[SpeedyBee: F405 Mini BLS 35A Stack / 35A Mini V2 ESC](https://www.speedybee.com/speedybee-f405-mini-bls-35a-20x20-stack/)

The manufacturer page provides useful ESC specifications but currently marks
the product discontinued. It is not the procurement baseline.

## Source 29

[ExpressLRS: Receiver Wiring](https://www.expresslrs.org/quick-start/receivers/wiring-up/)

Official later-phase reference for CRSF receiver power and TX/RX wiring. The
BLE build does not require ExpressLRS hardware.

## Source 30

[QGroundControl: PX4 Radio Setup](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/setup_view/radio.html)

Official setup reference for channel calibration, reversal, trim, and switch
verification. Perform all radio setup with propellers removed.

## Source 31

[BLHeli/BLHeli_S official source repository](https://github.com/bitdump/BLHeli/blob/master/BLHeli_S%20SiLabs/BLHeli_S.asm)

Primary firmware source documenting BLHeli_S support for DShot150, DShot300,
and DShot600. The received ESC firmware identity still has to be read and
archived before motor testing.

## Research Conclusions and Inferences

The following are engineering inferences rather than manufacturer promises:

- H7 compute headroom is useful for growth, but it does not improve BLE range
  or create position data.
- A 10 m BLE operating target is deliberately conservative but still requires
  test evidence in the actual body and RF environment.
- A 15 m geofence needs a physically clear area larger than 15 m because the
  action occurs after breach and the aircraft needs time and distance to stop.
- The V45A Lite is electrically oversized; it is selected for current official
  availability and voltage compatibility, not because the motors need 45 A.
- A 2:1 static thrust target is an initial controllability gate, not a guarantee
  of good handling or adequate flight time.
- The 450 mAh pack is a starting point. Measured all-up mass, hover current,
  voltage sag, and landed capacity determine the final battery.
