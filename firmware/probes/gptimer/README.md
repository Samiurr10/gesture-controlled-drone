# Timer group: fixed

**Was, 2026-09-18:** `gptimer_get_raw_count` never returned.
`timer_ll_trigger_soft_capture` writes `T0UPDATE` and spins until the bit reads
back clear; the shipped model stored the bit, so the unmodified ESP-IDF driver
looped forever. No alarms fired, and the ESP-IDF task watchdog could not fire
at all because it is backed by the same timer group.

**Now:** the timer group is implemented and this probe completes.

```sh
python3 firmware/tools/palmpilot.py run firmware/probes/gptimer firmware/probes/gptimer/run.py
python3 firmware/tools/palmpilot.py run firmware/probes/gptimer firmware/probes/gptimer/run.py stock
```

The second form selects the shipped model and still hangs, so the difference
stays demonstrable.

## What the fix covers

Written against `ESP32C3_Systimer`, which was already a working model of the
same shape. Committed on branch `agent/esp32-timg-counter` in
`simantic-dev/renode-infrastructure`, with 14 peripheral unit tests.

- T0 counting from APB through `T0CONFIG.DIVIDER`, with enable and load
- the `UPDATE`/`VALUE` snapshot handshake, self-clearing as hardware does
- alarm compare, `ALARM_EN` clearing on fire, auto-reload
- T0 and watchdog interrupts, exposed as two IRQ lines
- MWDT prescaler, stage-0 timeout, feed and stage-0 interrupt

The C3 and S3 register maps are identical here and both platforms use the same
class.

Not modelled, and logged rather than silently ignored: watchdog stage actions
that reset the CPU or system, and down-counting.

## Observed after the fix

```json
{"type":"result","name":"get_raw_count","status":0}
{"type":"sample","index":0,"count":40499,"alarms":0,...}
{"type":"sample","index":1,"count":20499,"alarms":1,...}
{"type":"advance","first":10537,"second":10588,"advanced":1}
{"type":"done","alarms":10}
```

Samples 30 ms apart advance by 30000 counts at 1 MHz and wrap against the
50000-count reload. Two back-to-back reads differ, so the counter is live
rather than a static snapshot.

## Consequence: the interrupt watchdog

A working timer group also makes ESP-IDF's **interrupt** watchdog real, and it
then expires at its designed 300 ms even though the firmware is healthy. It
panics, and the resulting reset aborts the engine
([probes/reset](../reset/README.md)).

The interrupt watchdog measures how long interrupts stay disabled, which a
virtual-time emulator cannot represent faithfully. `CONFIG_ESP_INT_WDT=n` in
`firmware/apps/hand/sdkconfig.defaults` is therefore a **simulation-only
divergence from the production configuration**, recorded there and here.
Production must re-enable it; on silicon it is a real safety net. Whether the
300 ms expiry reflects a genuine timing divergence or something still missing
in the model has **not** been established.
