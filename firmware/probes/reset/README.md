# Software reset model gap — ESP32-S3 in Simantic

**Finding, 2026-09-18:** calling `esp_restart()` aborts the simulation engine.
The guest does not fault and the firmware reports no error; the host call
raises:

```
simantic.mcu.SimError: Collection was modified; enumeration operation may not execute.
```

This is the **same host error as the FPU gap** (`firmware/probes/fpu`), so the
two may share a cause. That is a similarity in the error text, not a verified
common root — neither has been traced to engine source.

## Reproduce

```sh
python3 firmware/tools/palmpilot.py run firmware/probes/reset firmware/probes/reset/run.py
```

Observed:

```json
{"type":"boot","fixture":"palmpilot-reset-probe","reset_reason":1}
{"type":"stage","name":"before_esp_restart"}
ENGINE ABORTED: Collection was modified; enumeration operation may not execute.
```

The probe restarts exactly once and the restarted instance would print
`{"type":"restarted"}`. That record never appears, so the restart does not
complete. `reset_reason` 1 is `ESP_RST_POWERON`, the first boot.

## Environment

Simantic CLI/engine 0.5.7, SDK 0.3.1, ESP-IDF v5.5.2, platform
`ESP32-S3-WROOM-1-N8R2`, `CONFIG_FREERTOS_UNICORE=y`, PSRAM disabled.

## What this blocks

Anything whose behavior is only observable **across** a reset:

| Blocked | Consequence |
|---|---|
| Calibration persistence across reboot | NVS save, load, CRC rejection and erase are all verified in `firmware/tests/s1f_persistence.py`, but **restore-after-restart is not**. It must be tested physically at C2/CTRL-022. |
| Watchdog **recovery** | A watchdog reset is a reset. Timeout *detection* is testable; the reset and the state the firmware comes back in are not. |
| Reset reason reporting | `esp_reset_reason()` is only ever observed as power-on here. |

NVS itself works: writes reach the modeled SPI flash and read back, and a
corrupted blob is rejected by CRC. Only the reboot step is unavailable.

## What this does not establish

Which component is at fault, whether other reset paths (RTC watchdog, brownout,
`esp_restart_noos`, external reset) behave the same, whether other platforms or
engine versions are affected, or how the physical board behaves — **silicon was
not tested.** A real ESP32-S3 restarts normally; this says nothing about it.

## Follow-up

| Item | Owner | Action |
|---|---|---|
| Engine abort on `esp_restart` | Simantic | Reproduce with this probe; identify the mutated collection |
| Shared cause with the FPU gap | Simantic | Same error text; confirm or rule out |
| Reboot persistence | Project | Physical only, C2/CTRL-022 |
| Watchdog recovery | Project | Physical only; simulation covers detection alone |
