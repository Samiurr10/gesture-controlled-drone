#!/usr/bin/env python3
"""S3-A: both hands and the hub drive stock ArduCopter (D1).

    python3 firmware/tools/palmpilot.py system firmware/tests/s3a_drone.py

Four machines: LEFT, RIGHT and HUB (ESP32-S3, BLE) and the drone, stock
ArduCopter 4.7.1 on an STM32F405 (Matek F405-Wing board model). The computer
bridge turns each hub command into RC channels and sends them to ArduCopter's
telemetry port as MAVLink RC_CHANNELS_OVERRIDE. What ArduCopter reports back
(RC_CHANNELS, HEARTBEAT) is the evidence.

Limits fixed before the run (PROVISIONAL):
  * hands linked within 5 s; ArduCopter heartbeats as a quadrotor, standby within 20 s
  * no override is sent while the hub command is invalid
  * ArduCopter's RC_CHANNELS within +-5 us of the bridge's mapping of the hub command
  * ENABLE released: overrides stop within 0.2 s; ArduCopter in failsafe within 4 s
  * hub lines stop arriving: the bridge's own expiry stops overrides within 0.2 s

Not established: flight. The drone is disarmed throughout, nothing models its
physics, and the mapping and rates are provisional.
"""
import sys

from controller import ControllerSim, rc_link

EXTENDED_UV, CURLED_UV = 2154000, 1055000
MID_UV = (EXTENDED_UV + CURLED_UV) // 2
SATURATION = 16384 // 2
MAV_TYPE_QUADROTOR, STANDBY, CRITICAL = 2, 3, 5
RC_TOLERANCE_US = 5

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def run_until(sim, predicate, limit, step=0.1):
    """Advances until predicate() holds; returns the virtual time it took, or None."""
    start = sim.time()
    while sim.time() - start <= limit:
        if predicate():
            return sim.time() - start
        sim.run_for(step)
    return None


def rc_matches():
    reported = rc_link.rc_reported
    return reported is not None and all(
        abs(reported[i] - rc_link.channels[i]) <= RC_TOLERANCE_US for i in range(4))


with ControllerSim(drone=True) as sim:
    for hand in ("left", "right"):
        sim.set_hand_uv(hand, EXTENDED_UV)
    sim.set_enable(False)
    sim.set_calibrate(False)

    print("boot:", flush=True)
    sim.wait_linked(timeout=5.0)
    check("both hands linked to the hub", True, f"at {sim.time():.2f} s")
    for hand in ("left", "right"):
        result = sim.calibrate(hand, EXTENDED_UV, CURLED_UV)
        check(f"{hand} profile valid", result["valid"] == 1, result["reason"])
    run_until(sim, lambda: rc_link.heartbeat and rc_link.heartbeat["system_status"] == STANDBY,
              20.0 - sim.time(), step=0.5)
    beat = rc_link.heartbeat or {}
    check("ArduCopter heartbeats as a quadrotor", beat.get("type") == MAV_TYPE_QUADROTOR, str(beat))
    check("ArduCopter reaches standby within 20 s", beat.get("system_status") == STANDBY,
          f"at {sim.time():.1f} s")

    print("\nno command, no RC:", flush=True)
    sim.run_for(0.5)
    command = sim.latest_command()
    check("hub command invalid before ENABLE", command["valid"] == 0, command["reason"])
    check("bridge sends no override while invalid", rc_link.overrides_sent == 0,
          f"{rc_link.overrides_sent} sent")

    print("\ngestures reach ArduCopter:", flush=True)
    sim.set_enable(True)                              # open hand: throttle low
    sim.wait_command(lambda c: c["valid"], timeout=0.5)
    sim.set_hand_uv("left", MID_UV, fingers=["index", "middle", "ring", "little"])
    sim.motion("right").set_tilt(roll_component=SATURATION)
    sim.motion("left").set_tilt(roll_component=-SATURATION // 2)
    sim.run_for(1.5)
    command = sim.latest_command()
    check("hub command valid", command["valid"] == 1, command["reason"])
    took = run_until(sim, rc_matches, 1.0)
    check(f"ArduCopter's RC channels match the hub command (+-{RC_TOLERANCE_US} us)",
          took is not None,
          f"hub {[command[k] for k in ('roll', 'pitch', 'throttle', 'yaw')]} -> sent "
          f"{rc_link.channels[:4]} reported {rc_link.rc_reported and rc_link.rc_reported[:4]}")
    check("throttle from the left fingers (ch3)", 1350 < rc_link.channels[2] < 1650,
          str(rc_link.channels[2]))
    check("roll from the right hand (ch1 at full right)", rc_link.channels[0] == 2000,
          str(rc_link.channels[0]))
    check("yaw from the left hand (ch4 left of centre)", rc_link.channels[3] < 1500,
          str(rc_link.channels[3]))
    sim.motion("right").set_tilt(pitch_component=SATURATION)
    sim.run_for(1.0)
    took = run_until(sim, rc_matches, 1.0)
    check("pitch forward reaches ArduCopter as low ch2",
          took is not None and rc_link.rc_reported[1] < 1500,
          f"reported {rc_link.rc_reported and rc_link.rc_reported[:4]}")

    print("\nENABLE released:", flush=True)
    sent = rc_link.overrides_sent
    sim.set_enable(False)
    stopped = run_until(sim, lambda: rc_link.failsafe, 0.2, step=0.02)
    sim.run_for(0.1)
    after = rc_link.overrides_sent
    sim.run_for(0.5)
    check("overrides stop within 0.2 s", stopped is not None and rc_link.overrides_sent == after,
          f"{after - sent} sent after release")
    took = run_until(sim, lambda: rc_link.heartbeat["system_status"] == CRITICAL, 4.0, step=0.25)
    check("ArduCopter enters failsafe within 4 s", took is not None,
          f"{took:.2f} s" if took is not None else str(rc_link.heartbeat))

    print("\nhub falls silent (receiver-local expiry):", flush=True)
    sim.set_enable(True)
    sim.run_for(0.2)
    sim.set_enable(False)
    sim.set_hand_uv("left", EXTENDED_UV, fingers=["index", "middle", "ring", "little"])
    sim.run_for(0.3)
    sim.set_enable(True)
    resumed = run_until(sim, lambda: not rc_link.failsafe, 1.0, step=0.05)
    check("a deliberate new press resumes overrides", resumed is not None)
    sim.console["hub"].on_line = None                 # the computer stops hearing the hub
    sim.run_for(0.2)
    before = rc_link.overrides_sent
    sim.run_for(0.5)
    check("overrides stop within 0.2 s of the last hub line",
          rc_link.overrides_sent == before, f"{rc_link.overrides_sent - before} sent")

    panics = [n for n in ("left", "right", "hub") if "Guru Meditation" in sim.console[n].text]
    check("no firmware panic on any ESP32-S3", not panics, str(panics))
    sim.save("s3a_drone.json", {
        "test": "S3-A hands + hub drive stock ArduCopter",
        "scope": "ArduCopter 4.7.1 MatekF405-Wing, disarmed, no vehicle physics; provisional mapping",
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
