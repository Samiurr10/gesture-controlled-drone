#!/usr/bin/env python3
"""Runs the rngreset probe on one ESP32-S3. Set PALMPILOT_RNG_OVERLAY= for the stock RNG.

    python3 firmware/tools/palmpilot.py sim firmware/probes/rngreset firmware/probes/rngreset/run.py
"""
import os
import re
import sys

from harness import PalmPilotSim

with PalmPilotSim() as sim:
    sim.wait_for(lambda _r: "RESULT:" in sim.text, timeout=8.0, step=0.5)
print("\n".join(l for l in sim.text.splitlines() if l.startswith(("RNG", "RESULT"))))
result = re.search(r"RESULT: (\w+)", sim.text)
print(f"\nRNG model: {'candidate' if os.environ.get('PALMPILOT_RNG_OVERLAY') else 'stock'}")
sys.exit(0 if result and result.group(1) == "PASS" else 1)
