# Simantic model candidates

Simulator models this project needs that are not yet in a Simantic engine release. They are loaded as overlays on engine 0.6.3 by default (`firmware/tools/env.sh`). Each copy uses its own namespace (`BleFixed`, `RngFixed`, `UartFixed`), because the engine already contains classes with those names. The SYSTIMER (#257) and S3 MWDT (#258) candidates shipped in engine 0.5.15; on 0.5.20 every single-hand suite passed without them, and they were deleted.

| Directory | Upstream | What it fixes |
|---|---|---|
| `ble-radio/` | [renode-infrastructure #270](https://github.com/simantic-dev/renode-infrastructure/pull/270) | `ESP32C3_Radio` (the ESP32-C3/S3 BLE radio) assumed one connection per radio. A central could not hold two links, so the hub could not connect both hands. See the fixes listed below. |
| `rng-reset/` | [renode-infrastructure #271](https://github.com/simantic-dev/renode-infrastructure/pull/271) | `ESP32C3_Rng` restarted its sequence on every chip reset, so a rebooted board drew the same "random" values, and a hand reported the same session after a reset. |
| `stm32-uart-tx-dma/` | renode-infrastructure #325 (issue simantic-core #635; fixture sim-fixtures #387) | `STM32_UART` (STM32F4 USART) pulsed its TX DMA request only when TXE rose after a write. Silicon holds it as a level (DMAT and TXE), so a stream enabled while the transmitter was idle never started, and ArduCopter's MAVLink telemetry never left the drone. |

Build them into `tmp/simantic/upstream-candidates/` (gitignored):

```sh
. firmware/tools/env.sh
export DOTNET_ROOT="$PWD/tmp/simantic/dotnet-sdk" DOTNET_CLI_HOME="$PWD/tmp/simantic/dotnet-home"
"$DOTNET_ROOT/dotnet" build simulation/simantic/model-candidates/ble-radio/BleFixed.csproj
"$DOTNET_ROOT/dotnet" build simulation/simantic/model-candidates/rng-reset/RngFixed.csproj
"$DOTNET_ROOT/dotnet" build simulation/simantic/model-candidates/stm32-uart-tx-dma/UartFixed.csproj
```

To run the engine's own model instead, set the matching `PALMPILOT_*_OVERLAY=` variable to an empty string. Delete a candidate once an engine release contains its PR, and re-run `firmware/tests/run_all.sh`.

## BLE radio fixes, recorded 2026-09-29

A central holding two links (the hub) failed on the stock `ESP32C3_Radio` in three ways, each fixed here:

1. **The initiator answered any connectable advertiser.** It should answer only the peer the link layer named. That address is in the init control structure at +0x2C: it read …:12 on the attempt that targeted …:12, and …:22 on the one that targeted …:22. Without the fix, the central asked for one peripheral and linked the other.
2. **The new link's anchor ignored the offset the link layer planned** to keep it clear of an existing link (`rec[4]`, which is 0 with no other link). The second link's transmit window then opened 1.25 ms early, so the second connection never established.
3. **Frames were delivered regardless of access address.** A connection event now drops frames carrying another link's access address. Without this, one link received the other link's packets.

Measured with `firmware/probes/ble2link` (one central, two peripherals, all ESP32-S3), removing one fix at a time:

| Radio model | Result |
|---|---|
| stock | FAIL: second link never; in some runs link 1 goes to the wrong peripheral |
| without fix 1 | FAIL 4/4: wrong peripheral takes link 1 |
| without fix 2 | FAIL 2/2: second link never establishes |
| without fix 3 | FAIL 2/2: 3–6 of the other link's packets on link 1 |
| all three | PASS 3/3: both links at 50/s, no cross-link packets, repeats or drops |

Three more changes were tried and left out, because no test fails without them:
- CONNECT_IND filtered by AdvA on the advertiser: 4/4 pass without it.
- Per-link SN/NESN state.
- The SN-error RX flag.

The 130-fixture ESP regression shows the same outcomes on the engine with and without these fixes. The only differences are three timing fixtures that flip on repeat runs of either engine, and two of them run on the P4, which uses neither model.

## RNG fix, recorded 2026-09-29

`Reset()` no longer rewinds the xorshift state. The sequence stays reproducible from run to run, but differs from boot to boot.

**Evidence:** the hand session across a reboot was `3b47c78c` → `3b47c78c` on the stock model and `3b47c78c` → `e3175b1b` with the candidate. With the stock model, S2-B's "rebooted hand reports a new session" check fails.

## STM32 UART TX DMA, recorded 2026-10-05

Drone: stock ArduCopter 4.7.1 (MatekF405-Wing) on engine 0.5.20's STM32F405RG, telemetry on USART1 through DMA2 streams 2 (RX) and 7 (TX).

| UART model | Result |
|---|---|
| 0.5.20 stock | RX works (our MAVLink frames are in ArduCopter's RX buffer). The TX stream is enabled with NDTR = 64 and never moves: no heartbeat ever leaves. |
| candidate | heartbeats at 1 Hz; RC_CHANNELS reports exactly the overrides sent (1111/1222/1333/1444 µs); ArduCopter goes to failsafe (status 5) when they stop |

The candidate sets `DMATransmitRequest` to `DMAT && TXE` on every change, which is what `STM32F7_USART` already does.

**Evidence:** `firmware/probes/stm32-uart-txdma` is bare-metal USART2 TX by DMA on the STM32F446RE, run with the DMA armed in both orders.

- Stock: both cases stop at NDTR = 27.
- Candidate: both drain to 0.
- Engine rebuilt from source with and without #325: the 163 STM fixtures give identical outcomes.

The silicon run on a NUCLEO board is pending (sim-fixtures #387).
