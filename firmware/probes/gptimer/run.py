#!/usr/bin/env python3
"""Does the timer group count and raise alarms? Pass "stock" to skip the overlay."""
import sys
from harness import PalmPilotSim

use_overlay = "stock" not in sys.argv
with PalmPilotSim(timg=use_overlay) as sim:
    print(f"TIMG model: {'overlay under test' if use_overlay else 'stock'}\n")
    try:
        for _ in range(20):
            sim.run_for(0.25)
            if any(r.get("type") == "done" for r in sim.records()):
                break
    except Exception as exc:                    # noqa: BLE001 - this is the finding
        print(f"ENGINE ABORTED: {type(exc).__name__}: {exc}")
    records = sim.records()
    stages = [r["name"] for r in records if r.get("type") == "stage"]
    results = {r["name"] for r in records if r.get("type") == "result"}
    blocked = [s for s in stages if s not in results]
    seen = set()
    for record in records:
        if record.get("type") == "isr_log":
            if "isr_log" in seen:
                continue
            seen.add("isr_log")
        if record.get("type") in ("result", "count", "sample", "advance", "isr_log", "done"):
            print("  ", record)
    print(f"\nentered but never returned: {blocked or 'none'}")
    print("completed" if any(r.get("type") == "done" for r in records) else "DID NOT COMPLETE")
