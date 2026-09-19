#!/usr/bin/env python3
"""S1-C: control state machine and safety interlocks (FW-05).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1c_control.py

Exercises the interlocks in docs/controller/gesture-mapping.md: throttle-low to
enable, ENABLE held through boot being inert, whole-sample invalidation on
sensor fault, latched faults requiring a deliberate release and new press, and
stalled acquisition being detected as stale rather than frozen at the last
command.
"""
import sys

from harness import FLEX, PalmPilotSim

FINGERS = list(FLEX)
EXTENDED_UV = 2154000
CURLED_UV = 1055000

# enum hand_inhibit
INHIBIT_NONE, INHIBIT_NO_PRESS, INHIBIT_THROTTLE_HIGH = 0, 1, 2
INHIBIT_CALIBRATING, INHIBIT_FAULT = 3, 4

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


def control(sim):
    return command(sim, "control", "control")


def set_all(sim, microvolts, settle=0.15):
    for finger in FINGERS:
        sim.set_flex_uv(finger, microvolts)
    sim.run_for(settle)


def set_fingers(sim, mapping, settle=0.15):
    for finger, microvolts in mapping.items():
        sim.set_flex_uv(finger, microvolts)
    sim.run_for(settle)


def calibrate(sim):
    set_all(sim, EXTENDED_UV)
    mark = len(sim.stream)
    sim.send_line("cal extended")
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    set_all(sim, CURLED_UV)
    mark = len(sim.stream)
    sim.send_line("cal curled")
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    return command(sim, "cal finish", "calibration")


with PalmPilotSim() as sim:
    # ENABLE is pressed before the firmware ever runs.
    sim.set_enable(True)
    set_all(sim, EXTENDED_UV, settle=0.0)
    sim.wait_ready(timeout=5.0)

    print("uncalibrated:", flush=True)
    state = control(sim)
    check("starts in selftest, command invalid",
          state["state"] == "selftest" and state["valid"] == 0, state["state"])

    print("\ncalibration:", flush=True)
    result = calibrate(sim)
    check("calibration valid", result["valid"] == 1, result["reason"])

    print("\nENABLE held through boot is inert:", flush=True)
    set_all(sim, EXTENDED_UV)                       # throttle 0, arming allowed
    state = control(sim)
    check("still held, but not permitted", state["state"] == "waiting"
          and state["valid"] == 0, f"{state['state']} valid={state['valid']}")
    check("refusal reported as no-press", state["inhibit"] == INHIBIT_NO_PRESS,
          str(state["inhibit"]))

    sim.set_enable(False)
    sim.run_for(0.15)
    sim.set_enable(True)                            # release, then a new press
    sim.run_for(0.15)
    state = control(sim)
    check("release then new press permits", state["state"] == "permitted"
          and state["valid"] == 1, f"{state['state']} valid={state['valid']}")

    print("\nrelease ends permission:", flush=True)
    sim.set_enable(False)
    sim.run_for(0.15)
    state = control(sim)
    check("release returns to waiting, invalid",
          state["state"] == "waiting" and state["valid"] == 0, state["state"])

    print("\nthrottle-low interlock:", flush=True)
    set_all(sim, CURLED_UV)                         # closed fist = full throttle
    state = control(sim)
    check("closed fist reads full throttle", state["throttle_milli"] == 1000,
          str(state["throttle_milli"]))
    sim.set_enable(True)
    sim.run_for(0.15)
    state = control(sim)
    check("press with high throttle refused",
          state["state"] == "waiting" and state["valid"] == 0, state["state"])
    check("refusal reported as throttle-high",
          state["inhibit"] == INHIBIT_THROTTLE_HIGH, str(state["inhibit"]))

    sim.set_enable(False)
    sim.run_for(0.1)
    set_all(sim, EXTENDED_UV)
    sim.set_enable(True)
    sim.run_for(0.15)
    state = control(sim)
    check("press with low throttle permitted",
          state["state"] == "permitted" and state["valid"] == 1, state["state"])

    print("\nsensor fault latches while permitted:", flush=True)
    sim.set_flex_uv("ring", 0)                      # unplugged
    sim.run_for(0.15)
    state = control(sim)
    check("fault invalidates the command",
          state["state"] == "fault" and state["valid"] == 0, state["state"])

    sim.set_flex_uv("ring", EXTENDED_UV)            # sensor restored
    sim.run_for(0.15)
    state = control(sim)
    check("healthy data alone does not restore control",
          state["state"] == "recovery" and state["valid"] == 0, state["state"])
    check("still inhibited while ENABLE stays held",
          state["inhibit"] == INHIBIT_FAULT, str(state["inhibit"]))

    sim.run_for(0.5)                                # hold it there a while
    state = control(sim)
    check("holding ENABLE never self-recovers",
          state["state"] == "recovery" and state["valid"] == 0, state["state"])

    sim.set_enable(False)
    sim.run_for(0.15)
    state = control(sim)
    check("release clears to waiting", state["state"] == "waiting", state["state"])
    sim.set_enable(True)
    sim.run_for(0.15)
    state = control(sim)
    check("deliberate new press restores control",
          state["state"] == "permitted" and state["valid"] == 1, state["state"])

    print("\nstalled acquisition is detected as stale:", flush=True)
    # 30 sweeps at 100 Hz is about 300 ms without data, well past the 50 ms
    # freshness limit, and deterministic regardless of task-delay behavior.
    command(sim, "stall 30", "stalling")
    sim.run_for(0.1)
    state = control(sim)
    check("frozen acquisition invalidates the command",
          state["state"] == "fault" and state["valid"] == 0,
          f"{state['state']} fault={state['fault']}")
    check("fault reason is stale, not sensor", state["fault"] == 3,
          str(state["fault"]))

    sim.run_for(0.5)                                # let acquisition resume
    sim.set_enable(False)
    sim.run_for(0.15)
    sim.set_enable(True)
    sim.run_for(0.15)
    state = control(sim)
    check("recovers after release and new press",
          state["state"] == "permitted" and state["valid"] == 1, state["state"])

    print("\ncalibration inhibits output:", flush=True)
    mark = len(sim.stream)
    sim.send_line("cal extended")
    sim.wait_for_type("capturing", timeout=1.0, step=0.02, since=mark)
    sim.run_for(0.05)
    state = control(sim)
    check("calibrating enters service, command invalid",
          state["state"] == "service" and state["valid"] == 0, state["state"])
    check("refusal reported as calibrating",
          state["inhibit"] == INHIBIT_CALIBRATING, str(state["inhibit"]))
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    # That capture replaced the extended end, so the profile is invalid until a
    # full cycle completes. Recalibrate before testing the gesture thresholds.
    result = calibrate(sim)
    check("recalibration after service capture", result["valid"] == 1, result["reason"])

    print("\ndiscrete gestures:", flush=True)
    sim.set_enable(False)
    set_all(sim, EXTENDED_UV)
    state = control(sim)
    check("open hand: no HOLD, no PRECISION",
          state["hold"] == 0 and state["precision"] == 0)

    set_fingers(sim, {"thumb": CURLED_UV})
    state = control(sim)
    check("thumb curled -> PRECISION only",
          state["precision"] == 1 and state["hold"] == 0)
    check("thumb is excluded from throttle", state["throttle_milli"] == 0,
          str(state["throttle_milli"]))

    set_all(sim, CURLED_UV)
    state = control(sim)
    check("full fist -> HOLD", state["hold"] == 1, str(state["curl_milli"]))

    sim.save("s1c-control.json", {
        "test": "S1-C control state machine and safety interlocks",
        "scope": "modeled ADC/GPIO drivers; provisional thresholds, none qualified",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
