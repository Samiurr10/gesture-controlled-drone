#!/usr/bin/env python3
"""S1-E: gravity-referenced tilt mapping and gesture flags on one hand (FW-05).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1e_attitude.py

The tilt measure is sin(angle), not the angle: the gravity component along an
axis divided by the measured magnitude. Saturation is sin(30 deg) and the
deadband sin(3 deg), both provisional (CTRL-051).

Yaw never appears here. The hand publishes normalised roll and pitch tilt; the
hub decides which drone axis each drives, and the left hand's roll becomes yaw.
Magnetic data is read but is excluded from the command path by design.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("firmware/tests/fixtures").resolve()))

import imu_state                                             # noqa: E402
from harness import FLEX, PalmPilotSim                       # noqa: E402

FIXTURES = {
    0x6A: "firmware/tests/fixtures/lsm6ds3trc.py",
    0x1C: "firmware/tests/fixtures/lis3mdl.py",
}
FINGERS = list(FLEX)
EXTENDED_UV, CURLED_UV = 2154000, 1055000
G = imu_state.ACCEL_LSB_PER_G
SATURATION = G // 2          # sin(30 deg)
DEADBAND_LSB = 852           # sin(3 deg) * G

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def command(sim, line, kind, timeout=6.0, step=0.05):
    mark = len(sim.stream)
    sim.send_line(line)
    return sim.wait_for_type(kind, timeout=timeout, step=step, since=mark)


def set_all(sim, microvolts, settle=0.15):
    for finger in FINGERS:
        sim.set_flex_uv(finger, microvolts)
    sim.run_for(settle)


def tilt(sim, roll=0, pitch=0, settle=0.6):
    """Place gravity for a tilt and let a few control updates run."""
    imu_state.set_tilt(roll_component=roll, pitch_component=pitch)
    sim.run_for(settle)
    return command(sim, "control", "control")


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES, timg=True) as sim:
    sim.set_enable(False)
    set_all(sim, EXTENDED_UV, settle=0.0)
    sim.wait_ready(timeout=5.0)

    print("calibrate flex and resting orientation:", flush=True)
    set_all(sim, EXTENDED_UV)
    mark = len(sim.stream)
    sim.send_line("cal extended")
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    set_all(sim, CURLED_UV)
    mark = len(sim.stream)
    sim.send_line("cal curled")
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    result = command(sim, "cal neutral", "neutral")
    check("neutral captured level", result["result"] == 0, str(result["ratio"]))
    check("level neutral is gravity on Z", result["ratio"] == [0, 0, 1000],
          str(result["ratio"]))
    result = command(sim, "cal finish", "calibration")
    check("profile valid", result["valid"] == 1, result["reason"])
    set_all(sim, EXTENDED_UV)

    print("\nlevel and deadband:", flush=True)
    state = tilt(sim)
    check("level hand commands nothing",
          state["roll_milli"] == 0 and state["pitch_milli"] == 0,
          f"roll={state['roll_milli']} pitch={state['pitch_milli']}")
    state = tilt(sim, roll=DEADBAND_LSB - 60)
    check("tilt inside the deadband is ignored", state["roll_milli"] == 0,
          str(state["roll_milli"]))

    print("\nsaturation and sign:", flush=True)
    state = tilt(sim, roll=SATURATION)
    check("tilt right saturates roll at +1000", state["roll_milli"] == 1000,
          str(state["roll_milli"]))
    state = tilt(sim, roll=-SATURATION)
    check("tilt left saturates roll at -1000", state["roll_milli"] == -1000,
          str(state["roll_milli"]))
    state = tilt(sim, pitch=SATURATION)
    check("tilt forward saturates pitch at +1000", state["pitch_milli"] == 1000,
          str(state["pitch_milli"]))
    state = tilt(sim, pitch=-SATURATION)
    check("tilt back saturates pitch at -1000", state["pitch_milli"] == -1000,
          str(state["pitch_milli"]))

    print("\naxis independence:", flush=True)
    state = tilt(sim, roll=SATURATION)
    check("rolling does not command pitch", state["pitch_milli"] == 0,
          str(state["pitch_milli"]))
    state = tilt(sim, pitch=SATURATION)
    check("pitching does not command roll", state["roll_milli"] == 0,
          str(state["roll_milli"]))

    print("\nproportional response between deadband and saturation:", flush=True)
    state = tilt(sim, roll=SATURATION // 2)
    half = state["roll_milli"]
    check("half tilt is between deadband and saturation", 300 < half < 700, str(half))
    state = tilt(sim, roll=int(SATURATION * 0.75))
    check("three-quarter tilt exceeds half tilt", state["roll_milli"] > half,
          f"{state['roll_milli']} > {half}")
    state = tilt(sim, roll=SATURATION * 2)
    check("beyond saturation stays clamped at 1000", state["roll_milli"] == 1000,
          str(state["roll_milli"]))

    # The hand reports what it measures. Slew limits, PRECISION and HOLD act on
    # the combined command, so the hub applies them (hub_core.h) and S2-B tests
    # them there; the hand only has to flag the gestures it sees.
    print("\nthe hand reports, the hub shapes:", flush=True)
    tilt(sim, roll=0)
    imu_state.set_tilt(roll_component=SATURATION)    # instantaneous full tilt
    sim.run_for(0.06)                                # a few control updates
    state = command(sim, "control", "control")
    check("a step in tilt is reported at once (slew is the hub's)",
          state["roll_milli"] == 1000, str(state["roll_milli"]))

    print("\nPRECISION is flagged, not applied:", flush=True)
    for finger in FINGERS:
        sim.set_flex_uv(finger, CURLED_UV if finger == "thumb" else EXTENDED_UV)
    state = tilt(sim, roll=SATURATION)
    check("thumb curl flags PRECISION", state["precision"] == 1)
    check("hand still reports full roll under PRECISION", state["roll_milli"] == 1000,
          str(state["roll_milli"]))
    set_all(sim, EXTENDED_UV)
    state = tilt(sim, roll=SATURATION)
    check("PRECISION clears on release", state["precision"] == 0)

    print("\nHOLD is flagged, not applied:", flush=True)
    midpoint_uv = (EXTENDED_UV + CURLED_UV) // 2
    set_all(sim, midpoint_uv)
    sim.run_for(0.2)
    state = tilt(sim, roll=SATURATION)
    check("mid curl gives partial throttle", 300 < state["out_throttle_milli"] < 700,
          str(state["out_throttle_milli"]))
    check("HOLD not active at mid curl", state["hold"] == 0)
    set_all(sim, CURLED_UV)                          # clench into a fist
    sim.run_for(0.2)
    state = command(sim, "control", "control")
    check("full fist flags HOLD", state["hold"] == 1)
    check("hand still reports its tilt under HOLD", state["roll_milli"] == 1000,
          str(state["roll_milli"]))
    check("hand reports the full curl as throttle", state["out_throttle_milli"] >= 950,
          str(state["out_throttle_milli"]))

    print("\nmotion loss invalidates the command:", flush=True)
    set_all(sim, EXTENDED_UV)
    imu_state.accel_gyro_present = False
    sim.run_for(0.4)
    state = command(sim, "control", "control")
    check("motion fault reported", state["fault"] == 4, str(state["fault"]))
    check("command invalid without attitude", state["valid"] == 0, state["state"])
    imu_state.accel_gyro_present = True
    sim.run_for(0.4)

    print("\nneutral capture refuses a moving hand:", flush=True)
    imu_state.accel[:] = [0, 0, int(G * 1.6)]        # sustained acceleration
    sim.run_for(0.2)
    result = command(sim, "cal neutral", "neutral")
    check("accelerating hand rejected", result["reason"] == "unstable_capture",
          result["reason"])

    print("\nneutral is actually applied:", flush=True)
    imu_state.set_tilt(roll_component=SATURATION // 2)
    sim.run_for(0.2)
    result = command(sim, "cal neutral", "neutral")
    check("tilted rest captured as neutral", result["result"] == 0, str(result["ratio"]))
    command(sim, "cal finish", "calibration")
    state = tilt(sim, roll=SATURATION // 2)
    check("that same tilt now reads level", state["roll_milli"] == 0,
          str(state["roll_milli"]))
    state = tilt(sim, roll=0)
    check("level now reads as opposite tilt", state["roll_milli"] < -200,
          str(state["roll_milli"]))

    sim.save("s1e-attitude.json", {
        "test": "S1-E tilt mapping and gesture flags",
        "scope": "sin(angle) control law through modeled drivers; provisional "
                 "thresholds; not an attitude estimate and not linear in degrees",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

imu_state.reset()
print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
