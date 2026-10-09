#!/usr/bin/env python3
"""Fly ArduPilot's own SITL (ArduCopter 4.7.1, ArduPilot's multicopter physics) with
the RC stream our gesture flight produced, and compare the two flights.

    tmp/ardupilot-venv/bin/python simulation/drone/sitl_reference.py [flight_log.json]

The flight log comes from firmware/probes/drone-flight/fly.py: the hub's commands
and quad_plant's trajectory. Each hub command goes through rc_link, as the bridge
did, and reaches SITL as RC_CHANNELS_OVERRIDE at the same time after arming. Same
setup as the Renode flight: quad X, FLTMODE_CH=0, arming checks skipped, AltHold.

What differs, by construction: SITL's airframe is ArduPilot's default 3 kg, 0.35 m
quad (SIM_Frame.h), ours is quad_plant's 1 kg one, and SITL runs ArduCopter natively
rather than the MatekF405-Wing binary on the emulated STM32F405.
"""
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from pymavlink import mavutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import rc_link                                                        # noqa: E402

ARDUPILOT = ROOT / "tmp/ardupilot"
SITL_BIN = ARDUPILOT / "build/sitl/bin/arducopter"
WORK = ROOT / "tmp/palmpilot/sitl"
ARM_AT_S = float(os.environ.get("ARM_AT_S", "23.76"))      # fly.py's arm time, virtual s
SKIP_ALL = 0xFFFFE
OVERRIDES = """FRAME_CLASS 1
FRAME_TYPE 1
FLTMODE_CH 0
ARMING_SKIPCHK %d
""" % SKIP_ALL
# SITL_SENSORS=board: only what the Matek board model has (IMU, baro), as in the Renode flight.
BOARD_SENSORS = """GPS1_TYPE 0
COMPASS_ENABLE 0
SIM_IMU_COUNT 1
INS_ENABLE_MASK 1
"""


def schedule(log):
    """(t since arm, channels or None) for each hub command, through the bridge's mapping."""
    rc_link.reset()
    out = []
    for c in log["hub_commands"]:
        rc_link.apply_command(c)
        out.append((c["t_us"] / 1e6 - ARM_AT_S, None if rc_link.failsafe else list(rc_link.channels)))
    return out


def main():
    log_path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "tmp/palmpilot/system/flight_log.json")
    log = json.loads(log_path.read_text())
    global ARM_AT_S
    ARM_AT_S = log.get("arm_at_s") or ARM_AT_S
    plan = [p for p in schedule(log) if p[0] >= -1.0]
    end_s = max(t for t, _ in plan) + 2.0

    WORK.mkdir(parents=True, exist_ok=True)
    board = os.environ.get("SITL_SENSORS") == "board"
    (WORK / "overrides.parm").write_text(OVERRIDES + (BOARD_SENSORS if board else ""))
    defaults = f"{ARDUPILOT}/Tools/autotest/default_params/copter.parm,{WORK}/overrides.parm"
    sitl = subprocess.Popen([str(SITL_BIN), "--model", "x", "--speedup", "1", "-w", "-I0",
                             "--defaults", defaults, "--home", "-35.363261,149.165230,584,0"],
                            cwd=WORK, stdout=open(WORK / "sitl.out", "w"), stderr=subprocess.STDOUT)
    try:
        fly(plan, end_s, log)
    finally:
        sitl.terminate()


def fly(plan, end_s, log):
    for _ in range(50):
        try:
            mav = mavutil.mavlink_connection("tcp:127.0.0.1:5760", source_system=255)
            break
        except OSError:
            time.sleep(0.2)
    mav.wait_heartbeat(timeout=30)
    for msg, hz in ((mavlink_id("SIMSTATE"), 20), (mavlink_id("GLOBAL_POSITION_INT"), 20),
                    (mavlink_id("SERVO_OUTPUT_RAW"), 10)):
        mav.mav.command_long_send(1, 1, 511, 0, msg, 1_000_000 // hz, 0, 0, 0, 0, 0)
    texts = []
    print("waiting for the EKF ...", flush=True)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 60:              # EKF origin from SITL's GPS
        m = mav.recv_match(type=["GLOBAL_POSITION_INT", "STATUSTEXT"], blocking=True, timeout=1)
        if m and m.get_type() == "STATUSTEXT":
            texts.append(m.text)
            if "is using GPS" in m.text or ("tilt alignment complete" in m.text and time.monotonic() - t0 > 8):
                break
    mav.set_mode("ALT_HOLD")
    low = [1500, 1500, 1000, 1500, 1500, 0, 0, 0]
    for _ in range(25):
        mav.mav.rc_channels_override_send(1, 1, *low)
        time.sleep(0.02)
    mav.mav.command_long_send(1, 1, 400, 0, 1, 0, 0, 0, 0, 0, 0)
    arm_t = time.monotonic()
    print("armed; replaying", len(plan), "hub commands", flush=True)

    track, i, home = [], 0, None
    while (now := time.monotonic() - arm_t) < end_s:
        while i + 1 < len(plan) and plan[i + 1][0] <= now:
            i += 1
        channels = plan[i][1]
        if channels:
            mav.mav.rc_channels_override_send(1, 1, *channels)
        deadline = time.monotonic() + 0.02
        while (m := mav.recv_match(blocking=True, timeout=max(0.0, deadline - time.monotonic()))):
            kind = m.get_type()
            if kind == "SIMSTATE":
                lat, lng = m.lat / 1e7, m.lng / 1e7
                home = home or (lat, lng)
                north = (lat - home[0]) * 111_320.0
                east = (lng - home[1]) * 111_320.0 * math.cos(math.radians(home[0]))
                track.append({"t": now, "roll": math.degrees(m.roll), "pitch": math.degrees(m.pitch),
                              "yaw": math.degrees(m.yaw), "N": north, "E": east})
            elif kind == "GLOBAL_POSITION_INT" and track:
                track[-1]["alt"] = m.relative_alt / 1000.0
            elif kind == "STATUSTEXT":
                texts.append(f"{now:6.2f}s {m.text}")
            if time.monotonic() >= deadline:
                break
    compare(log, track, texts)


def mavlink_id(name):
    return getattr(mavutil.mavlink, f"MAVLINK_MSG_ID_{name}")


def compare(log, track, texts):
    ours = [{"t": r[0] - ARM_AT_S, "alt": -r[1][2], "N": r[1][0], "E": r[1][1],
             "roll": r[3], "pitch": r[4], "yaw": r[5]} for r in log["log"]]
    sitl = [r for r in track if "alt" in r]
    phases = phase_windows(log)
    rows = []
    for name, start, stop in phases:
        rows.append((name, metrics(ours, start, stop), metrics(sitl, start, stop)))
    print("\nArduCopter: statustext from SITL")
    for t in texts[-12:]:
        print("   ", t)
    print(f"\n{'phase':<16} {'metric':<22} {'ours (Renode F405 + quad_plant)':>32} {'ArduPilot SITL physics':>24}")
    for name, a, b in rows:
        for key in a:
            print(f"{name:<16} {key:<22} {a[key]:>32.2f} {b.get(key, float('nan')):>24.2f}")
    out = ROOT / f"tmp/palmpilot/sitl/compare-{os.environ.get('SITL_SENSORS', 'full')}.json"
    out.write_text(json.dumps({"ours": ours, "sitl": sitl, "phases": phases, "texts": texts}, indent=1))
    print(f"\ntracks saved to {out}")


def phase_windows(log):
    """Contiguous runs of the same hub command after arming: (label, start, stop) in s since arm."""
    windows, current = [], None
    for c in log["hub_commands"]:
        t = c["t_us"] / 1e6 - ARM_AT_S
        if t < 0:
            continue
        key = (c["valid"], c["roll"], c["pitch"], c["yaw"], c["throttle"])
        if current is None or key != current[0]:
            if current:
                windows.append((label(current[0]), current[1], t))
            current = (key, t)
    windows.append((label(current[0]), current[1], current[1] + 2.0))
    return [w for w in windows if w[2] - w[1] >= 1.5]


def label(key):
    valid, roll, pitch, yaw, throttle = key
    if not valid:
        return "invalid"
    parts = [f"thr {throttle}"] + [f"{n} {v:+}" for n, v in (("r", roll), ("p", pitch), ("y", yaw)) if v]
    return " ".join(parts)


def metrics(track, start, stop):
    """Steady-state numbers over the second half of a window."""
    mid = start + (stop - start) / 2
    rows = [r for r in track if mid <= r["t"] <= stop]
    if len(rows) < 2:
        return {}
    dt = rows[-1]["t"] - rows[0]["t"]
    yaw_turn = math.remainder(rows[-1]["yaw"] - rows[0]["yaw"], 360.0)
    return {"climb m/s": (rows[-1]["alt"] - rows[0]["alt"]) / dt,
            "roll deg": sum(r["roll"] for r in rows) / len(rows),
            "pitch deg": sum(r["pitch"] for r in rows) / len(rows),
            "speed N m/s": (rows[-1]["N"] - rows[0]["N"]) / dt,
            "speed E m/s": (rows[-1]["E"] - rows[0]["E"]) / dt,
            "yaw rate deg/s": yaw_turn / dt,
            "alt m": rows[-1]["alt"]}


if __name__ == "__main__":
    main()
