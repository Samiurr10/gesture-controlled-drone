#!/usr/bin/env python3
"""Report which NVS stage the firmware stops at."""
from harness import PalmPilotSim

with PalmPilotSim(adc=False) as sim:
    for _ in range(24):                 # up to 60 simulated seconds
        sim.run_for(2.5)
        if any(r.get("type") == "done" for r in sim.records()):
            break
    records = sim.records()
    print("completed" if any(r.get("type") == "done" for r in records)
          else "DID NOT COMPLETE")
    print("\ntrace:")
    for record in records:
        print("  ", record)
    stages = [r["name"] for r in records if r.get("type") == "stage"]
    results = {r["name"] for r in records if r.get("type") == "result"}
    blocked = [s for s in stages if s not in results]
    print(f"\nentered but never returned: {blocked or 'none'}")
