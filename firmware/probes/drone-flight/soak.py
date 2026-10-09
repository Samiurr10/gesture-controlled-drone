#!/usr/bin/env python3
"""Run the four-machine drone simulation (replay hands, hub, F405 + plant) for a while,
printing simulated time each second, so a stall shows as output that stops.

    python3 firmware/tools/palmpilot.py system --replay --no-build firmware/probes/drone-flight/soak.py [seconds [tag]]
"""
import faulthandler
import os
import signal
import sys
import time

from controller import ControllerSim, quad_plant, rc_link

faulthandler.register(signal.SIGUSR1, all_threads=True)   # kill -USR1 <pid>: every Python thread's stack
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0

t0 = time.monotonic()
# SOAK_QUANTUM: the machines' synchronisation quantum in seconds; smaller means more
# synchronisation points, so more chances to hit a cross-thread race.
quantum = float(os.environ["SOAK_QUANTUM"]) if os.environ.get("SOAK_QUANTUM") else None
with ControllerSim(drone=True, plant=True, quantum=quantum) as sim:
    print(f"SOAK started in {time.monotonic() - t0:.1f}s", flush=True)
    sim.set_calibrate(False)
    start = time.monotonic()
    while sim.time() < SECONDS:
        sim.run_for(1.0)
        print(f"SOAK sim={sim.time():5.1f}s wall={time.monotonic() - start:6.1f}s imu={quad_plant.PLANT.samples} "
              f"heartbeats={rc_link.heartbeats}", flush=True)
    print("SOAK done", flush=True)
    t1 = time.monotonic()
print(f"SOAK shut down in {time.monotonic() - t1:.1f}s", flush=True)
