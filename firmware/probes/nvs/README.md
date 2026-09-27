# NVS write/erase model gap — ESP32-S3 in Simantic

> **Superseded 2026-09-27.** On engine 0.5.14 with the SYSTIMER candidate
> (renode-infrastructure #257), `nvs_erase_key` returns in the hand application and
> the multi-task phase of this probe completes. The hang was the dead FreeRTOS
> tick: the erase path yields with `vTaskDelay`. Erase, CRC rejection and reboot
> restore are now asserted in S1-F. The original record follows.


**Finding, 2026-09-18:** NVS reads and blob writes complete, but some write and
erase operations **never return** when the application has other tasks running.
The task stops silently: no error, no panic, no further output, for at least
**60 simulated seconds**. Unlike the FPU and reset gaps, the engine does not
abort — the guest simply stops making progress.

## What was observed

In a quiet single-task probe, the whole cycle completes:

```json
flash_init 0 -> open_readwrite 0 -> set_blob 0 -> commit 0
           -> open_readonly 0 -> get_blob 0
           -> open_readwrite 0 -> erase_key 0 -> commit 0
```

In the hand application, which runs a 100 Hz acquisition task and a 50 Hz
control task alongside the main UART task:

| Operation | Result |
|---|---|
| `nvs_flash_init`, restore at boot | completes |
| `nvs_open` (read-only and read-write) | completes |
| `nvs_get_blob` | completes |
| `nvs_set_blob` + `nvs_commit` | completes — **29 consecutive saves** all returned |
| `nvs_erase_key` + `nvs_commit` | **never returns** |
| read-only open, then `nvs_set_blob` | **never returns** |

Extending this probe to start an `esp_timer` at 100 Hz and a background task
also stopped its output immediately after the tasks were created, before the
next print. That end of the probe is therefore **inconclusive** and is not
evidence of where the fault lies.

## What this does and does not establish

**Established:** in the hand application, `nvs_erase_key` does not complete,
while `nvs_set_blob` does. Reproducible across runs.

**Not established:** the mechanism. A plausible explanation is ESP-IDF's
cache-disable and scheduler-suspend around flash operations not being fully
modeled, so code that must run from IRAM during that window stalls. **That is a
hypothesis, not a diagnosis** — no engine source was inspected, and the probe's
own background-task stage did not produce a usable trace. The precise
difference between the quiet probe and the hand application has not been
isolated.

**Not established:** anything about silicon. A real ESP32-S3 performs these
operations normally; this says nothing about it.

## Effect on the controller

Calibration persistence is implemented in `firmware/apps/hand/main/persist.c`
and the path a user depends on — save a profile, load it back, reject a corrupt
one — works. But persistence as a whole is **NOT QUALIFIED**:

| Behavior | Status |
|---|---|
| Save, load, contents preserved | verified, `firmware/tests/s1f_persistence.py` |
| Restore after reboot | **BLOCKED** — `esp_restart` aborts the engine (`probes/reset`) |
| CRC rejection of a corrupt profile | **BLOCKED** in the hand app — corrupting the stored blob needs a write that hangs |
| Erase | **BLOCKED** — hangs |

All four must be tested physically at C2/CTRL-022. The CRC check itself is
plain integer code and is exercised wherever a load rejects a mismatch; what
cannot be exercised here is deliberately producing that mismatch on-device.

## Follow-up

| Item | Owner | Action |
|---|---|---|
| `nvs_erase_key` does not return | Simantic | Reproduce; check flash cache-disable / scheduler-suspend emulation |
| Isolate quiet vs busy difference | Project | Probe stage 2 needs stage markers around task creation to be usable |
| Persistence qualification | Project | Physical only, C2/CTRL-022 |

Firmware consequence: **do not call a flash write from the live control path.**
Real ESP-IDF flash writes suspend the scheduler, so persisting a profile
belongs in the service/calibration state where output is already inhibited.
