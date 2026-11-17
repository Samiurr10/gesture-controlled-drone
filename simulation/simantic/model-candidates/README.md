# Simantic model candidates

Simulator models this project needs that are not yet in a Simantic engine release. They load as overlays on engine 0.6.6 (`firmware/tools/env.sh`), in their own namespace (`RngFixed`), because the engine already contains a class of that name.

| Directory | Upstream | What it fixes |
|---|---|---|
| `rng-reset/` | [renode-infrastructure #271](https://github.com/simantic-dev/renode-infrastructure/pull/271) | `ESP32C3_Rng` restarted its sequence on every chip reset, so a rebooted board drew the same "random" values, and a hand reported the same session after a reset. `firmware/probes/rngreset` on 0.6.6: stock FAIL (3 repeated values), candidate PASS. |

Shipped and deleted, with their probes (git history has them): SYSTIMER (#257) and S3 MWDT (#258) in engine 0.5.15; BLE radio (#270) and STM32 UART TX DMA (#325) in 0.6.6, where the ble2link and stm32-uart-txdma probes passed on the stock models.

Build into `tmp/simantic/upstream-candidates/` (gitignored):

```sh
. firmware/tools/env.sh
export DOTNET_ROOT="$PWD/tmp/simantic/dotnet-sdk" DOTNET_CLI_HOME="$PWD/tmp/simantic/dotnet-home"
"$DOTNET_ROOT/dotnet" build simulation/simantic/model-candidates/rng-reset/RngFixed.csproj
```

Set `PALMPILOT_RNG_OVERLAY=` (empty) to run the engine's own model. Delete the candidate once an engine release contains its PR, and re-run `firmware/tests/run_all.sh`.

## RNG fix, recorded 2026-09-29

`Reset()` no longer rewinds the xorshift state. The sequence stays reproducible from run to run, but differs from boot to boot.

**Evidence:** the hand session across a reboot was `3b47c78c` → `3b47c78c` on the stock model and `3b47c78c` → `e3175b1b` with the candidate. With the stock model, S2-B's "rebooted hand reports a new session" check fails.
