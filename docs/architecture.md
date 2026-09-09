# Architecture Design

This design keeps human-interface logic, radio bridging, and real-time flight
control as separate responsibilities.

## Responsibility Split

| Subsystem | Processor | Owns | Does not own |
|---|---|---|---|
| Hand controller | ESP32-C3-MINI-1-N4X | IMU sampling, filtering, gesture mapping, 18-byte command notifications, local safety input | Motor mixing, flight stabilization |
| Drone radio bridge | ESP32-C3-MINI-1-N4X | BLE central, packet validation, BLE-to-CRSF conversion, telemetry forwarding | Gesture interpretation, arming authority, motor control |
| Flight controller | STM32H753VIT6 | CRSF input, arming, failsafe, control loops, estimator, mixer, PWM/DShot outputs | BLE stack, hand gesture classification |
| Simulation harness | pyrite / rn-engine | Virtual clock, multi-machine lockstep, scenario inputs, impairment injection, trace capture | Product firmware policy |

## End-To-End Control Path

```mermaid
flowchart LR
    trace[Scenario IMU trace] --> imu[IMU device model]
    imu --> handDriver[Hand C3 IMU driver]
    handDriver --> gesture[Gesture filtering and mapping]
    gesture --> cmd[Command frame]
    cmd --> bleTx[Hand C3 NimBLE peripheral]
    bleTx --> medium[BleMedium with impairments and pcap tap]
    medium --> bleRx[Drone C3 NimBLE central]
    bleRx --> bridge[BLE-to-CRSF gateway firmware]
    bridge --> wire[Virtual CRSF UART at 420000 baud]
    wire --> h7Rx[STM32H753 USART + DMA]
    h7Rx --> fc[Flight-control firmware]
    fc --> mixer[Mixer and output scheduler]
    mixer --> esc[ESC / motor sink]

    fc --> telemetry[Telemetry frame]
    telemetry --> wire
    bridge --> bleRx
```

## Simulation Boundary

```mermaid
flowchart TB
    subgraph Pyrite_Emulation[pyrite Emulation: one virtual clock]
        subgraph Hand_Machine[Machine 1: hand ESP32-C3]
            HandFlash[ESP-IDF hand firmware image]
            HandPeripherals[I2C/GPSPI2, GPIO, BLE controller]
        end

        subgraph Air_Medium[Machine-to-machine media]
            BLE[BleMedium]
            Serial[CRSF UART wire medium]
        end

        subgraph Drone_Radio_Machine[Machine 2: drone ESP32-C3]
            RadioFlash[ESP-IDF bridge firmware image]
            RadioPeripherals[BLE controller, CRSF UART]
        end

        subgraph Flight_Machine[Machine 3: STM32H753]
            H7Flash[PX4 or flight firmware image]
            H7Peripherals[RCC/PWR, USART, DMA, GPIO, TIM/DShot, SPI/I2C]
        end

        SensorFeed[scenario sensor feed]
        IMUModel[IMU model]
        ESCSink[ESC/motor sink]

        SensorFeed --> IMUModel --> HandPeripherals
        HandPeripherals --> BLE --> RadioPeripherals
        RadioPeripherals --> Serial --> H7Peripherals
        H7Peripherals --> ESCSink
    end
```

## BLE Command Frame Contract

The hand controller should send commands, not motor outputs.

```text
CommandFrameV1 {
    protocol_version_u8
    flags_u8
    sequence_u16
    sender_tick_ms_u32
    pitch_i16
    roll_i16
    thrust_i16
    yaw_i16
    crc16_ccitt_u16
}
```

The drone side should reject frames that are stale, duplicated, corrupt, or
outside the expected mode/state transition rules.

## Recommended Protocol Shape

```mermaid
sequenceDiagram
    participant Hand as Hand ESP32-C3
    participant BLE as BleMedium
    participant Radio as Drone ESP32-C3
    participant Wire as CRSF UART
    participant H7 as STM32H753 FC
    participant ESC as ESC/motor sink

    Hand->>Hand: sample IMU and dead-man input
    Hand->>Hand: filter, decimate, map gesture
    Hand->>BLE: 18-byte command notification
    BLE->>Radio: deliver command with modeled latency/loss
    Radio->>Radio: validate length, sequence, CRC, range, and age
    Radio->>Wire: publish CRSF while input is fresh
    Wire->>H7: receive at 420000 baud
    H7->>H7: PX4 CRSF input and independent RC-loss check
    H7->>ESC: emit PWM/DShot motor outputs
    H7-->>Wire: CRSF telemetry
    Wire-->>Radio: selected telemetry
    Radio-->>BLE: telemetry characteristic
    BLE-->>Hand: telemetry
```

## Key Design Rules

- Use the hand C3 as the BLE peripheral and the drone C3 as the central. Send
  command notifications at 100 Hz with a 10 ms connection interval.
- Keep flight stabilization on the STM32H7, not the glove.
- Use per-hop sequence numbers and local age checks; do not compare timestamps
  across independent clocks.
- Use CRSF over full-duplex UART between the drone C3 and H753. Stop CRSF output
  when BLE input is stale; never hold the final command indefinitely.
- Keep arming and motor-output authority exclusively on the H753.
- Simulate failure first: BLE cut, stale frames, garbage serial data, FIFO
  overflow, and sensor silence should all become CI scenarios.

## Verification Layers

Use complementary layers so H753 emulator bring-up does not block control-system
validation:

1. Host tests for framing, CRC, mapping, sequence wrap, and state transitions.
2. Pyrite with both exact C3 images, the BLE medium, and a scripted CRSF peer.
3. PX4 SITL with recorded gesture traces and vehicle physics.
4. H753 HITL for real clocks, DMA, UART, interrupts, and watchdog behavior.
5. Targeted H753 Pyrite support for deterministic peripheral fault injection.

## Build Order

```mermaid
flowchart LR
    W2W3[W2/W3: CRSF UART + scripted peer] --> M1[M1 hop-by-hop]
    W1[W1: STM32H7 platform] --> M1
    M1 --> M2[M2 wire closed]
    W4W5[W4/W5: C3 bus + IMU model] --> M3[M3 sensor in]
    M2 --> M3
    W6[W6: BLE impairments] --> M4[M4 failure modes]
    M3 --> M4
    W7[W7: ESC sink] --> M5[M5 loop out]
    M4 --> M5
```
