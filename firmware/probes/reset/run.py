#!/usr/bin/env python3
"""Report whether a software reset completes or aborts the engine."""
from harness import PalmPilotSim

with PalmPilotSim() as sim:
    try:
        for _ in range(16):
            sim.run_for(0.25)
            if any(r.get("type") == "restarted" for r in sim.records()):
                break
        print("engine survived the run")
    except Exception as exc:                    # noqa: BLE001 - this is the finding
        print(f"ENGINE ABORTED: {type(exc).__name__}: {exc}")
    print("\nrecords:")
    for record in sim.records():
        print("  ", record)
