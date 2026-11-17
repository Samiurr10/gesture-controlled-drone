#!/usr/bin/env python3
"""The demo drone on the emulated flight controller: stock ArduCopter 4.7.1 on the Matek
F405-Wing (STM32F405) in Simantic, with quad_plant flying the airframe from its motor
outputs. A stand-in for sitl_live.Drone in demo_view.py (`--drone f405`), to see what the
emulated F405 adds in delay next to SITL.

Runs in the Simantic environment (env.sh), not the ArduPilot venv; demo_view.py's docstring
has the command line. One thread owns the simulation and runs it in 20 ms slices as fast as
it goes, never ahead of the wall clock. It is slower than real time in flight (about 1.47 s
wall per simulated second, demo_speed.py) and pauses further when ArduCopter changes mode
or arms; nothing here hides that. `boot_s` is simulated time, so the page's real-time
factor shows it.

Hub lines reach rc_link from the screen's thread at 50 Hz of wall time, as a physical hub's
would reach the computer bridge; gcs_peer sends the newest channels every 20 ms of
simulated time and counts its 100 ms expiry in simulated ticks. With the F405 slower than
real time it therefore sees more than one line per tick, never fewer.

The airframe is quad_plant's 1 kg quad (PALMPILOT_AIRFRAME=ardupilot: the port of SITL's
3 kg quad). No wind. Sensors are the Matek board's (IMU, barometer); no GPS or compass, so
N/E come from quad_plant, not from ArduCopter's estimate.
"""
import os
import sys
import threading
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for path in (HERE, ROOT / "firmware/tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("PALMPILOT_OUT", str(ROOT / "tmp/palmpilot/f405-live"))

from controller import ControllerSim, quad_plant, rc_link             # noqa: E402
from pymavlink.dialects.v20 import ardupilotmega as mavlink           # noqa: E402

SLICE = 0.02
ALT_HOLD = 2
ALIGN_LIMIT_S = 30.0               # simulated seconds to wait for the EKF's tilt alignment
RATES_HZ = {"ATTITUDE": 50, "RC_CHANNELS": 20}
PLANT = quad_plant.PLANT


class Drone:
    """sitl_live.Drone's interface over the Simantic drone machine. `t` and now() are wall
    seconds since start; `sim_t` and `boot_s` are simulated seconds."""

    def __init__(self):
        self.t0 = time.monotonic()
        self.texts = []
        self.running = True
        self.last_override = None          # wall time of the end of the newest slice that sent one
        self.boot_wall = None              # wall seconds to ready
        self.error = None
        self._ready = threading.Event()
        self._row = {}
        self._seen = 0
        rc_link.reset()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def now(self):
        return time.monotonic() - self.t0

    def command(self, cmd, *params):
        params = list(params) + [0] * (7 - len(params))
        rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, cmd, 0, *params))

    def althold(self):
        self.command(mavlink.MAV_CMD_DO_SET_MODE, mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, ALT_HOLD)

    def arm(self, on=True):
        if on:
            self.althold()
        self.command(mavlink.MAV_CMD_COMPONENT_ARM_DISARM, int(on))

    # -- the simulation thread ---------------------------------------------------------
    def _run(self):
        try:
            with ControllerSim(drone=True, plant=True, hands=False) as sim:
                self.sim = sim
                sim.setup_drone()
                for name, hz in RATES_HZ.items():
                    self.command(mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                                 getattr(mavlink, f"MAVLINK_MSG_ID_{name}"), 1_000_000 // hz)
                start = sim.time()
                while self.running and sim.time() - start < ALIGN_LIMIT_S:
                    self._slice(sim)
                    if any("alignment complete" in t for _, t in self.texts):
                        break
                else:
                    if self.running:
                        raise RuntimeError(f"no EKF tilt alignment within {ALIGN_LIMIT_S} s simulated")
                end = sim.time() + 2.0
                while self.running and sim.time() < end:
                    self._slice(sim)
                self.boot_wall = self.now()
                self._ready.set()
                while self.running:
                    began = time.monotonic()
                    self._slice(sim)
                    spare = SLICE - (time.monotonic() - began)
                    if spare > 0:               # never ahead of the wall clock
                        time.sleep(spare)
        except Exception as error:              # noqa: BLE001 - reported through wait_ready
            self.error = error
            traceback.print_exc()
        finally:
            self.running = False
            self._ready.set()

    def _slice(self, sim):
        sent = rc_link.overrides_sent
        sim.run_for(SLICE)
        now = self.now()
        sending = rc_link.overrides_sent > sent
        if sending:
            self.last_override = now
        for _, _, text in rc_link.statustext[self._seen:]:
            self.texts.append((round(now, 2), text))
            print(f"      ArduCopter: {text}", flush=True)
        self._seen = len(rc_link.statustext)
        roll, pitch, yaw = PLANT.euler_deg()
        row = {"sim_t": round(sim.time(), 3), "boot_s": round(sim.time(), 3),
               "N": round(PLANT.pos[0], 3), "E": round(PLANT.pos[1], 3), "alt": round(-PLANT.pos[2], 3),
               "vN": round(PLANT.vel[0], 3), "vE": round(PLANT.vel[1], 3), "vD": round(PLANT.vel[2], 3),
               "roll": round(roll, 2), "pitch": round(pitch, 2), "yaw": round(yaw, 2),
               "motors": [round(p) for p in PLANT.pulses], "sending": sending}
        if a := rc_link.latest.get("ATTITUDE"):
            row["est"] = [round(v * 57.29577951308232, 2) for v in (a.roll, a.pitch, a.yaw)]
        if rc_link.rc_reported:
            row["rc"] = list(rc_link.rc_reported[:4])
        if hb := rc_link.heartbeat:
            row["armed"] = bool(hb["base_mode"] & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            row["mode"] = hb["custom_mode"]
        self._row = row

    # -- what the screen reads ---------------------------------------------------------
    def state(self):
        """The newest completed slice, as sitl_live.Drone.state() reports it."""
        row = {"t": round(self.now(), 3), **self._row}
        row["last_override"] = self.last_override
        row.setdefault("sending", False)
        row["cmd"] = list(rc_link.channels[:4])
        return row

    def wait_ready(self, limit=600.0):
        if not self._ready.wait(limit):
            raise RuntimeError(f"F405 drone not ready after {limit} s wall")
        if self.error or not self.running:
            raise RuntimeError(f"F405 drone stopped before it was ready: {self.error}")

    def close(self):
        self.running = False
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=30)
