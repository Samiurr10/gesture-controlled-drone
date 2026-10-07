#!/usr/bin/env python3
"""Every parameter of the emulated F405's ArduCopter, after fly.py's setup (frame,
arming, FLTMODE_CH, PALMPILOT_FLIGHT_PARAMS) and a reboot, to tmp/palmpilot/params/f405.json.

    PALMPILOT_FLIGHT_PARAMS=... python3 firmware/tools/palmpilot.py system --replay --no-build firmware/probes/drone-flight/params_dump.py
"""
import json
import os
import sys
from pathlib import Path

from controller import ControllerSim, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fly import SKIP_ALL, flight_params, mav, standby          # noqa: E402

with ControllerSim(drone=True, plant=True) as sim:
    sim.set_calibrate(False)
    standby(sim)
    for name, value in [(b"FRAME_CLASS", 1), (b"FRAME_TYPE", 1), (b"ARMING_SKIPCHK", SKIP_ALL), (b"FLTMODE_CH", 0)] + flight_params():
        mav(lambda m, n=name, v=value: m.param_set_encode(1, 1, n, v, mavlink.MAV_PARAM_TYPE_REAL32))
    sim.run_for(1.0)
    mav(lambda m: m.command_long_encode(1, 1, mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 0, 0))
    sim.run_for(1.0)
    standby(sim)
    rc_link.params.clear()
    mav(lambda m: m.param_request_list_encode(1, 1))
    total = None
    for _ in range(120):
        sim.run_for(1.0)
        got = {m.param_id: m.param_value for m in rc_link.params}
        total = rc_link.params[-1].param_count if rc_link.params else None
        if total and len(got) >= total:
            break
    out = Path(os.environ.get("PALMPILOT_OUT", ".")).parents[0] / "params" / "f405.json"
    out.write_text(json.dumps(got, indent=1, sort_keys=True))
    print(f"PARAMS {len(got)} of {total} -> {out}")
