#!/usr/bin/env python3
"""Every parameter of the emulated flight controller's ArduCopter, after setup_drone (and
PALMPILOT_FLIGHT_PARAMS) and a reboot, to tmp/palmpilot/params/<PALMPILOT_DRONE>.json.

    PALMPILOT_FLIGHT_PARAMS=... python3 firmware/tools/palmpilot.py system --replay --no-build firmware/probes/drone-flight/params_dump.py
"""
import json
import os
import sys
from pathlib import Path

from controller import ControllerSim, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fly import flight_params, mav          # noqa: E402

with ControllerSim(drone=True, plant=True) as sim:
    sim.set_calibrate(False)
    sim.setup_drone(flight_params())
    rc_link.params.clear()
    mav(lambda m: m.param_request_list_encode(1, 1))
    total = None
    for _ in range(120):
        sim.run_for(1.0)
        got = {m.param_id: m.param_value for m in rc_link.params}
        total = rc_link.params[-1].param_count if rc_link.params else None
        if total and len(got) >= total:
            break
    out = Path(os.environ.get("PALMPILOT_OUT", ".")).parents[0] / "params" / f"{os.environ.get('PALMPILOT_DRONE', 'f405')}.json"
    out.write_text(json.dumps(got, indent=1, sort_keys=True))
    print(f"PARAMS {len(got)} of {total} -> {out}")
