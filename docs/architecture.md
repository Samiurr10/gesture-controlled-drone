# Architecture Design

This design keeps human-interface logic, radio bridging, and real-time flight
control as separate responsibilities.

## Responsibility Split

| Subsystem | Processor | Owns | Does not own |
|---|---|---|---|
| Hand controller | ESP32-C3 | IMU sampling, filtering, gesture mapping, command packet generation, local safety input | Motor mixing, flight stabilization |
| Drone radio bridge | ESP32-C3 | BLE connection, packet validation, command forwarding, telemetry forwarding | Gesture interpretation, motor control |
| Flight controller | STM32H7 | Failsafe, control loops, estimator, mixer, PWM/DShot outputs | BLE stack, hand gesture classification |
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
    medium --> bleRx[Drone C3 NimBLE central or peripheral]
    bleRx --> bridge[BLE to serial bridge firmware]
    bridge --> wire[Virtual UART or SPI wire]
    wire --> h7Rx[STM32H7 USART/SPI + DMA]
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
            Serial[UART/SPI wire medium]
        end

        subgraph Drone_Radio_Machine[Machine 2: drone ESP32-C3]
            RadioFlash[ESP-IDF bridge firmware image]
            RadioPeripherals[BLE controller, UART/SPI]
        end

        subgraph Flight_Machine[Machine 3: STM32H7]
            H7Flash[flight firmware image]
            H7Peripherals[RCC/PWR, USART, DMA, GPIO, TIM/PWM, SPI/I2C]
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

## Command Frame Contract

The hand controller should send commands, not motor outputs.

```text
CommandFrame {
    sequence_number
    local_timestamp
    mode
    enable
    roll_request
    pitch_request
    yaw_request
    throttle_or_altitude_request
    crc
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
    participant Wire as UART/SPI wire
    participant H7 as STM32H7 FC
    participant ESC as ESC/motor sink

    Hand->>Hand: sample IMU and dead-man input
    Hand->>Hand: filter, decimate, map gesture
    Hand->>BLE: write-without-response command
    BLE->>Radio: deliver command with modeled latency/loss
    Radio->>Radio: validate sequence and CRC
    Radio->>Wire: forward framed command
    Wire->>H7: baud-timed bytes or SPI transaction
    H7->>H7: parse, validate age, update control target
    H7->>ESC: emit PWM/DShot motor outputs
    H7-->>Wire: telemetry frame
    Wire-->>Radio: telemetry bytes
    Radio-->>BLE: notification
    BLE-->>Hand: telemetry
```

## Key Design Rules

- Keep BLE command traffic one-way and low-latency: use write-without-response
  or notifications, not request/response control loops.
- Keep flight stabilization on the STM32H7, not the glove.
- Use per-hop sequence numbers and local age checks; do not compare timestamps
  across independent clocks.
- Use framed serial data with a start marker, length, and CRC, or use a proven
  framing scheme such as MAVLink or COBS.
- Simulate failure first: BLE cut, stale frames, garbage serial data, FIFO
  overflow, and sensor silence should all become CI scenarios.

## Build Order

```mermaid
flowchart LR
    W2W3[W2/W3: serial wire + scripted peer] --> M1[M1 hop-by-hop]
    W1[W1: STM32H7 platform] --> M1
    M1 --> M2[M2 wire closed]
    W4W5[W4/W5: C3 bus + IMU model] --> M3[M3 sensor in]
    M2 --> M3
    W6[W6: BLE impairments] --> M4[M4 failure modes]
    M3 --> M4
    W7[W7: ESC sink] --> M5[M5 loop out]
    M4 --> M5
```

