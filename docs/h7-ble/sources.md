# Research Sources

Research completed: 2026-09-10

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

## Source 32

[PX4 v1.17: Collision Prevention](https://docs.px4.io/v1.17/en/computer_vision/collision_prevention)

Official behavior and parameter reference for Position-mode collision
prevention, 72 five-degree obstacle sectors, rangefinder-to-obstacle mapping,
`CP_DIST`, `CP_DELAY`, `CP_GUIDE_ANG`, `CP_GO_NO_DATA`, stale/lost range data,
Hold after complete data loss, and Gazebo simulation. It also warns that the
external companion-computer setup is currently untested.

## Source 33

[PX4 v1.17: Distance Sensors and Rangefinders](https://docs.px4.io/v1.17/en/sensor/rangefinders)

Official overview of rangefinder uses and simulation targets. It distinguishes
downward range aiding from horizontal obstacle sensing and provides the
`gz_x500_lidar_down`, `gz_x500_lidar_front`, and `gz_x500_lidar_2d` test
models.

## Source 34

[PX4 v1.17: Distance-Sensor Driver Modules](https://docs.px4.io/v1.17/en/modules/modules_driver_distance_sensor)

Official module reference showing the native `vl53l1x` driver and its external
I2C, address, bus, and rotation options. The prototype instead isolates four
same-address sensors behind a range hub.

## Source 35

[Pololu: VL53L1X Carrier, Item 3415](https://www.pololu.com/product/3415)

Current manufacturer product page for the selected collision sensor. It lists
active/preferred status, 13 x 18 x 2 mm size, 0.5 g mass without headers,
2.6-5.5 V carrier input, 20 mA typical/40 mA peak current, 4 cm minimum,
mode-dependent range/update rate, typical 27-degree FoV, I2C output, and the
active-low, non-5-V-tolerant `XSHUT` input.

## Source 36

[Seeed Studio: XIAO RP2040](https://wiki.seeedstudio.com/XIAO-RP2040/)

Official board reference for the selected range hub: dual-core RP2040 at up to
133 MHz, 264 KB SRAM, 2 MB flash, 11 GPIOs, I2C, UART, SPI, 3.3 V I/O, and
21 x 17.8 mm dimensions.

## Source 37

[PX4: Kakute H7 Mini Board Definition at v1.17.0](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/boards/holybro/kakuteh7mini/default.px4board)

Pinned source evidence that Kakute H7 Mini maps `TELEM1` to `/dev/ttyS0`,
`TELEM2` to `/dev/ttyS1`, GPS1 to `/dev/ttyS3`, and includes the common
distance-sensor and multicopter position-control configuration.

## Source 38

[Pololu: D24V5F3 3.3 V/500 mA Step-Down Regulator](https://www.pololu.com/product/2842/specs)

Current manufacturer product page for the dedicated ToF rail regulator. It
lists active/preferred status, 3.3 V output, 500 mA typical maximum output,
3.4-36 V input, 0.4 x 0.5 x 0.1 inch size, and 0.6 g mass without headers.

## Source 39

[Bitcraze: Multi-ranger Deck](https://www.bitcraze.io/multi-ranger-deck/)

Official comparison/reference design using five VL53L1X sensors and a PCA9534
reset expander for front, rear, left, right, and up ranging. Bitcraze lists
2.3 g mass and 35 x 35 x 5 mm size, and explicitly states that the deck supplies
sensor data rather than collision avoidance by itself.

## Source 40

[Pololu: VL53L7CX Wide-FoV Carrier, Item 3418](https://www.pololu.com/product/3418)

Official wide-FoV array candidate for a custom later phase. It lists a
60 x 60 degree square FoV, 3.5 m maximum range under favorable conditions,
4x4/8x8 zones, 100 mA typical/150 mA peak current, 0.5 g carrier mass, and the
LPn process for assigning several devices unique I2C addresses.

## Source 41

[LightWare: SF45/B Product Guide, Revision 3](https://lightwarelidar.com/wp-content/uploads/2025/07/SF45B-Product-Guide-v3.pdf)

Manufacturer specifications for the wider-coverage upgrade: 0.2-50 m range,
up to 5,000 readings/s and five sweeps/s, 5-5.5 V at 300 mA typical/<450 mA
startup, UART/I2C, 51 x 48 x 44 mm size, and 59 g mass excluding cables.

## Source 42

[PX4: LightWare SF45/B Rotating Lidar](https://docs.px4.io/main/en/sensor/sf45_rotating_lidar)

Official integration guide requiring a custom PX4 build with
`lightware_sf45_serial`, 921600-baud sensor configuration, an unused serial
port, orientation/update/yaw parameters, and obstacle-map verification. It also
notes 5 V/300 mA demand and possible cable voltage-drop failures.

## Source 43

[PX4 v1.17: Optical Flow](https://docs.px4.io/v1.17/en/sensor/optical_flow)

Official reference for GNSS-denied position/velocity aiding. It explains that
optical flow requires downward flow sensing plus distance data and must be
configured and fused by the estimator. This is an indoor-position dependency,
not a horizontal collision sensor.

## Source 44

[PX4 v1.17.0: LightWare SF45 Serial Driver](https://github.com/PX4/PX4-Autopilot/tree/v1.17.0/src/drivers/distance_sensor/lightware_sf45_serial)

Pinned source evidence that the selected PX4 v1.17.0 tree contains the SF45/B
serial-driver implementation even though it is not enabled in every default
board build.

## Source 45

[PX4 v1.17.0: Kakute H7 Mini NuttX Board Pin Definitions](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/boards/holybro/kakuteh7mini/nuttx-config/include/board.h)

Pinned source for the STM32H743 alternate-function assignments: USART1 on
PA9/PA10, USART2 on PD5/PD6, UART4 on PD1/PD0, USART3 on PD8/PD9, USART6 on
PC6/PC7, UART7 on PE7/PE8, I2C1 on PB6/PB7, SPI1, SPI2, SPI4, USB, and clock
configuration.

## Source 46

[PX4 v1.17.0: Kakute H7 Mini Timer/Output Configuration](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/boards/holybro/kakuteh7mini/src/timer_config.cpp)

Pinned source for motor output hardware: M1 PB0/TIM3_CH3, M2 PB1/TIM3_CH4,
M3 PB3/TIM2_CH2, M4 PB10/TIM2_CH3, and the reserved M5-M8 channels.

## Source 47

[PX4 v1.17.0: Kakute H7 Mini SPI Devices](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/boards/holybro/kakuteh7mini/src/spi.cpp) and
[board sensor startup](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/boards/holybro/kakuteh7mini/init/rc.board_sensors)

Pinned evidence that the flight IMU is factory-routed on SPI4 with PE4 chip
select and PE1 data-ready. Startup probes MPU6000, BMI270, then ICM-42688-P and
probes BMP280 before SPA06 to cover Kakute hardware revisions.

## Source 48

[PX4 v1.17.0: Generic Quadcopter X Airframe](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/ROMFS/px4fmu_common/init.d/airframes/4001_quad_x) and
[control-allocator rotor parameter definitions](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/control_allocator/module.yaml)

Pinned source for motor geometry and rotation: positive X is forward, positive
Y is right, positive moment coefficient is CCW, and negative is CW. This yields
Motor 1 front-right CCW, Motor 2 rear-left CCW, Motor 3 front-left CW, and
Motor 4 rear-right CW.

## Source 49

[PX4 v1.17: Actuator Configuration and Testing](https://docs.px4.io/v1.17/en/config/actuators)

Official workflow for defining geometry, assigning motor functions to physical
outputs, using Identify & Assign Motors, and conducting props-off actuator
tests.

## Source 50

[Seeed Studio: XIAO ESP32-C3 Pin Multiplexing and I/O Allocation](https://wiki.seeedstudio.com/XIAO_ESP32C3_Pin_Multiplexing/)

Official board warning that D6/GPIO21 is UART0 TX and emits bootloader text at
startup, plus boot/strapping cautions for D8/GPIO8 and D9/GPIO9. This supports
moving the aircraft CRSF transport away from UART0 TX.

## Source 51

[Espressif ESP-IDF v5.4: ESP32-C3 UART Driver](https://docs.espressif.com/projects/esp-idf/en/v5.4/esp32c3/api-reference/peripherals/uart.html)

Primary API reference for `uart_set_pin()`, `UART_NUM_1`, and routing UART
signals through the ESP32-C3 GPIO matrix to selected non-strapping pins.

## Source 52

[ARK Electronics: ARK SAM GPS Pinout](https://docs.arkelectron.com/products/gps/ark-sam-gps)

Manufacturer connector definition: pin 1 5 V, pin 2 RX, pin 3 TX, pin 4 SCL,
pin 5 SDA, and pin 6 ground, with 3.3 V UART/I2C signaling.

## Source 53

[Holybro: Kakute H7 Mini Overview](https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-mini/overview) and
[supported firmware](https://docs.holybro.com/autopilot/kakute-h7-v1-v2-mini/kakute-h7-mini/supported-firmware)

Current manufacturer documentation for the v1.5 revision and PX4 support. The
overview currently conflicts with Holybro's SKU 11082 store listing about the
exact IMU/barometer names, so the design requires purchase by SKU and receiving
verification using PX4-detected device IDs.

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
- Four narrow VL53L1X sensors support only four-direction braking. Axis locking
  and no-data blocking are required to avoid claiming unmeasured diagonal space.
- A dedicated RP2040 hub adds mass and firmware but isolates experimental ToF
  I2C traffic from the H7's flight-critical compass bus.
