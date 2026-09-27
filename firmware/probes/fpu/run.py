#!/usr/bin/env python3
"""Report how far the FPU probe gets before the engine aborts."""
from harness import PalmPilotSim

with PalmPilotSim() as sim:
    try:
        for _ in range(12):
            sim.run_for(0.25)
            if any(r.get("type") == "done" and r.get("context") == "app_main"
                   for r in sim.records()):
                break
        print("engine survived the run")
    except Exception as exc:                    # noqa: BLE001 - this is the finding
        print(f"ENGINE ABORTED: {type(exc).__name__}: {exc}")
    print("\nstages reached:")
    for record in sim.records():
        print("  ", record)
