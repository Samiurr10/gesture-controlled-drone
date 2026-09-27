#!/usr/bin/env python3
"""Score the timer-group MWDT against limits fixed before the run.

    python3 firmware/tools/palmpilot.py run firmware/probes/mwdt firmware/probes/mwdt/run.py [stock]

`stock` runs the platform's own timer-group model; otherwise the harness loads
the timer-group overlay selected by env.sh (PALMPILOT_S3_MWDT_OVERLAY first).
"""
import sys

from harness import PalmPilotSim

PROGRAMMED_MS = 200
TOLERANCE_US = 3000           # one 500 us tick plus ISR and polling latency
FEEDS = 20                    # fed every 50 ms: 1 s with no interrupt allowed
ESP_RST_INT_WDT, ESP_RST_TASK_WDT = 5, 6       # esp_reset_reason_t
CORE_MWDT0, CORE_MWDT1 = 7, 8                  # esp32s3 soc/reset_reasons.h

stock = len(sys.argv) > 1 and sys.argv[1] == "stock"
checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    if not ok:
        failures.append(name)


def command(sim, line, timeout=6.0):
    mark = len(sim.stream)
    sim.send_line(line)
    sim.wait_for_type("done", timeout=timeout, step=0.05, since=mark)
    return [r for r in sim.records(mark) if r.get("type") in ("result", "fed")]


def on_time(result):
    return result["fired"] == 1 and abs(result["elapsed_us"] - PROGRAMMED_MS * 1000) <= TOLERANCE_US


with PalmPilotSim(timg=not stock) as sim:
    sim.wait_for_type("ready", timeout=6.0)
    for record in sim.records():
        if record.get("type") == "intr":
            check(f"TG{record['group']} WDT interrupt allocated", record["status"] == 0,
                  f"source {record['source']}")

    for group in (0, 1):
        print(f"\nTG{group}:", flush=True)
        try:
            (result,) = command(sim, f"int {group} {PROGRAMMED_MS}")
            check(f"TG{group} stage-0 interrupt at {PROGRAMMED_MS} ms", on_time(result),
                  f"fired={result['fired']} elapsed={result['elapsed_us']} us")

            fed, result = command(sim, f"feed {group} {PROGRAMMED_MS} {FEEDS}")
            check(f"TG{group} feeding postpones it", fed["fired_while_fed"] == 0,
                  f"{fed['feeds']} feeds, fired={fed['fired_while_fed']}")
            check(f"TG{group} fires {PROGRAMMED_MS} ms after the last feed", on_time(result),
                  f"elapsed={result['elapsed_us']} us")

            (result,) = command(sim, f"locked {group} {PROGRAMMED_MS}")
            check(f"TG{group} locked write cannot disable it", on_time(result),
                  f"fired={result['fired']} elapsed={result['elapsed_us']} us")
        except Exception as exc:                  # noqa: BLE001 - reported as a failure
            check(f"TG{group} interrupt scenarios", False, f"{type(exc).__name__}: {exc}")

    for group, reason, rom in ((1, ESP_RST_INT_WDT, CORE_MWDT1), (0, ESP_RST_TASK_WDT, CORE_MWDT0)):
        print(f"\nTG{group} stage-0 system reset:", flush=True)
        try:
            mark = len(sim.stream)
            sim.send_line(f"reset {group} 100")
            boot = sim.wait_for_type("boot", timeout=4.0, step=0.05, since=mark)
            check(f"TG{group} system reset reboots the chip", True)
            check(f"TG{group} reset reason", boot["reset_reason"] == reason and boot["rom_reason"] == rom,
                  f"reset_reason={boot['reset_reason']} rom_reason={boot['rom_reason']} "
                  f"(expected {reason}/{rom})")
            sim.wait_for_type("ready", timeout=6.0, step=0.05, since=mark)
        except Exception as exc:                  # noqa: BLE001
            check(f"TG{group} system reset reboots the chip", False, f"{type(exc).__name__}: {exc}")
            break

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
