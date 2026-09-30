#!/usr/bin/env python3
"""S2-B: the whole controller -- both hands through the hub to one command.

    python3 firmware/tools/palmpilot.py system firmware/tests/s2b_controller.py

Stimulus enters only through modeled hardware: flex voltages through each
hand's ADC model, tilt through each hand's own I2C motion fixtures, ENABLE and
CALIBRATE through GPIO7. What is observed is the hub's command stream on UART0,
the same bytes the host bridge will read.

Mapping under test (docs/controller/gesture-mapping.md, hub_core.h):
  roll = right roll tilt, pitch = right pitch tilt, yaw = left roll tilt,
  throttle = left four-finger curl; HOLD = right fist; PRECISION = left thumb.

Limits fixed before the run. All PROVISIONAL (FW-04/FW-05 leave them UNSET):
  * a valid command appears within 0.2 s of a deliberate ENABLE press
  * steady-state axes within +-20 milli of the value the hand reports
  * slew: no update moves attitude more than 80 or throttle more than 30 milli
  * fault-to-invalid at the hub <= 150 ms (100 ms freshness + two updates + margin),
    counted in hub updates (20 ms each), not wall clock
  * after any loss of validity the command stays invalid until ENABLE is
    released and pressed again, however healthy the data becomes

What this does not establish: human-hand behaviour, real flex or IMU noise,
RF behaviour, or any physical timing. The simulated medium is lossless.
"""
import sys

from controller import ControllerSim

EXTENDED_UV, CURLED_UV = 2154000, 1055000
MID_UV = (EXTENDED_UV + CURLED_UV) // 2
G = 16384
SATURATION = G // 2                     # sin(30 deg): full command
UPDATE_S = 0.02
ENABLE_LATENCY_S = 0.2
AXIS_TOLERANCE = 20
SLEW_ATTITUDE, SLEW_THROTTLE = 80, 30
FAULT_TO_INVALID_MS = 150

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def settle(sim, seconds=1.0):
    """Long enough for the slowest slew (throttle, 30 milli per update)."""
    sim.run_for(seconds)
    return sim.latest_command()


def hand_control(sim, hand):
    return sim.query(hand, "control", "control")


def tilt(sim, hand, roll=0, pitch=0):
    sim.motion(hand).set_tilt(roll_component=roll, pitch_component=pitch)


def enable_cycle(sim):
    """Release, then a deliberate new press."""
    sim.set_enable(False)
    sim.run_for(0.15)
    sim.set_enable(True)


def invalid_after(sim, mark, act, reason_prefix):
    """Applies `act`, then counts hub updates until the command goes invalid."""
    act()
    command = sim.wait_command(lambda c: not c["valid"], timeout=1.0, since=mark)
    rows = sim.commands(mark)
    first = rows[0]["seq"] if rows else command["seq"]
    return command, (command["seq"] - first + 1) * UPDATE_S * 1000


with ControllerSim() as sim:
    for hand in ("left", "right"):
        sim.set_hand_uv(hand, EXTENDED_UV)
    sim.set_enable(False)
    sim.set_calibrate(False)
    sim.wait_linked(timeout=5.0)

    print("calibrate both hands (bench procedure over each hand's UART):", flush=True)
    for hand in ("left", "right"):
        result = sim.calibrate(hand, EXTENDED_UV, CURLED_UV)
        check(f"{hand} profile valid", result["valid"] == 1, result["reason"])
    sim.run_for(0.3)

    print("\npermission:", flush=True)
    command = sim.latest_command()
    check("no ENABLE: command invalid", not command["valid"], command["reason"])
    check("no ENABLE: reason is not_enabled", command["reason"] == "not_enabled",
          command["reason"])
    check("no ENABLE: every axis zero",
          all(command[k] == 0 for k in ("roll", "pitch", "yaw", "throttle")), str(command))
    mark = sim.mark("hub")
    sim.set_enable(True)
    command = sim.wait_command(lambda c: c["valid"], timeout=ENABLE_LATENCY_S, since=mark)
    check(f"ENABLE press gives a valid command within {ENABLE_LATENCY_S} s", command["valid"] == 1,
          f"seq +{command['seq'] - sim.commands(mark)[0]['seq']}")
    command = settle(sim, 0.3)
    check("open level hands command zero",
          all(command[k] == 0 for k in ("roll", "pitch", "yaw", "throttle")), str(command))

    print("\nthrottle from the left hand's four fingers:", flush=True)
    sim.set_hand_uv("left", MID_UV, fingers=["index", "middle", "ring", "little"])
    mark = sim.mark("hub")
    command = settle(sim, 1.0)
    reported = hand_control(sim, "left")["out_throttle_milli"]
    check("half curl gives about half throttle", 350 < command["throttle"] < 650,
          str(command["throttle"]))
    check("hub throttle equals what the left hand reports",
          abs(command["throttle"] - reported) <= AXIS_TOLERANCE,
          f"hub {command['throttle']} hand {reported}")
    steps = [b["throttle"] - a["throttle"] for a, b in zip(sim.commands(mark), sim.commands(mark)[1:])]
    check(f"throttle slews at most {SLEW_THROTTLE} per update", max(steps, default=0) <= SLEW_THROTTLE,
          f"max step {max(steps, default=0)}")
    check("throttle actually ramps (more than one update)",
          sum(1 for s in steps if s > 0) > 3, f"{sum(1 for s in steps if s > 0)} rising updates")

    print("\nright hand drives roll and pitch, left hand drives yaw:", flush=True)
    mark = sim.mark("hub")
    tilt(sim, "right", roll=SATURATION)
    command = settle(sim, 0.6)
    check("right roll tilt -> roll +1000", command["roll"] == 1000, str(command["roll"]))
    check("right roll tilt moves nothing else", command["pitch"] == 0 and command["yaw"] == 0,
          f"pitch={command['pitch']} yaw={command['yaw']}")
    steps = [abs(b["roll"] - a["roll"]) for a, b in zip(sim.commands(mark), sim.commands(mark)[1:])]
    check(f"roll slews at most {SLEW_ATTITUDE} per update", max(steps, default=0) <= SLEW_ATTITUDE,
          f"max step {max(steps, default=0)}")
    tilt(sim, "right", pitch=-SATURATION)
    command = settle(sim, 0.6)
    check("right pitch tilt back -> pitch -1000", command["pitch"] == -1000, str(command["pitch"]))
    check("roll returns to zero when the right hand levels in roll", command["roll"] == 0,
          str(command["roll"]))
    tilt(sim, "right")
    tilt(sim, "left", roll=-SATURATION)
    command = settle(sim, 0.6)
    check("left roll tilt -> yaw -1000", command["yaw"] == -1000, str(command["yaw"]))
    check("left tilt does not command roll or pitch", command["roll"] == 0 and command["pitch"] == 0,
          f"roll={command['roll']} pitch={command['pitch']}")
    check("throttle unaffected by tilt", abs(command["throttle"] - reported) <= AXIS_TOLERANCE,
          str(command["throttle"]))

    print("\nPRECISION (left thumb) halves attitude, not throttle:", flush=True)
    tilt(sim, "right", roll=SATURATION)
    settle(sim, 0.6)
    sim.set_flex_uv("left", "thumb", CURLED_UV)
    command = settle(sim, 0.6)
    check("PRECISION flagged", command["precision"] == 1)
    check("roll halved to 500", command["roll"] == 500, str(command["roll"]))
    check("yaw halved to -500", command["yaw"] == -500, str(command["yaw"]))
    check("throttle unchanged by PRECISION", abs(command["throttle"] - reported) <= AXIS_TOLERANCE,
          f"{command['throttle']} vs {reported}")
    sim.set_flex_uv("left", "thumb", EXTENDED_UV)
    command = settle(sim, 0.6)
    check("full authority returns on release", command["roll"] == 1000 and command["precision"] == 0,
          str(command["roll"]))

    print("\nHOLD (right fist) neutralises attitude and freezes throttle:", flush=True)
    before = sim.latest_command()["throttle"]
    sim.set_hand_uv("right", CURLED_UV)
    command = settle(sim, 0.8)
    check("HOLD flagged", command["hold"] == 1)
    check("HOLD zeroes roll, pitch and yaw",
          command["roll"] == 0 and command["pitch"] == 0 and command["yaw"] == 0, str(command))
    check("HOLD keeps throttle where it was", abs(command["throttle"] - before) <= AXIS_TOLERANCE,
          f"{command['throttle']} vs {before}")
    sim.set_hand_uv("left", CURLED_UV, fingers=["index", "middle", "ring", "little"])
    command = settle(sim, 0.8)
    check("left fist cannot move a held throttle", abs(command["throttle"] - before) <= AXIS_TOLERANCE,
          f"{command['throttle']} vs {before}")
    sim.set_hand_uv("left", MID_UV, fingers=["index", "middle", "ring", "little"])
    sim.set_hand_uv("right", EXTENDED_UV)
    command = settle(sim, 1.0)
    check("releasing HOLD restores control", command["hold"] == 0 and command["roll"] == 1000,
          str(command))

    print("\nENABLE is a deadman:", flush=True)
    mark = sim.mark("hub")
    sim.set_enable(False)
    command = sim.wait_command(lambda c: not c["valid"], timeout=0.3, since=mark)
    check("release invalidates the command", command["valid"] == 0, command["reason"])
    check("invalid command carries no motion",
          all(command[k] == 0 for k in ("roll", "pitch", "yaw", "throttle")), str(command))
    sim.set_enable(True)
    command = sim.wait_command(lambda c: True, timeout=0.3)
    sim.run_for(0.2)
    command = sim.latest_command()
    check("a new press with the left hand half-curled is refused (throttle-low interlock)",
          command["valid"] == 0, command["reason"])
    sim.set_enable(False)
    sim.set_hand_uv("left", EXTENDED_UV, fingers=["index", "middle", "ring", "little"])
    sim.run_for(0.3)
    sim.set_enable(True)
    command = sim.wait_command(lambda c: c["valid"], timeout=0.4)
    check("press with throttle low is granted", command["valid"] == 1, command["reason"])
    settle(sim, 0.4)

    print("\nright hand sampling freezes behind a live link:", flush=True)
    mark = sim.mark("hub")
    command, latency = invalid_after(sim, mark, lambda: sim.send_line("right", "stall 40"),
                                     "right")
    check("hub invalidates on the right hand's frozen sampler",
          command["reason"] in ("right_frozen", "right_not_ready"), command["reason"])
    check(f"fault-to-invalid <= {FAULT_TO_INVALID_MS} ms", latency <= FAULT_TO_INVALID_MS,
          f"{latency:.0f} ms ({command['reason']})")
    sim.run_for(1.0)                                 # the stall ends; data healthy again
    command = sim.latest_command()
    check("healthy data alone does not resume (latched)", command["valid"] == 0,
          command["reason"])
    check("latch names its way out", command["reason"] == "await_release", command["reason"])
    enable_cycle(sim)
    command = sim.wait_command(lambda c: c["valid"], timeout=0.5)
    check("release and a new press resume", command["valid"] == 1)

    print("\nleft flex sensor unplugged:", flush=True)
    mark = sim.mark("hub")
    command, latency = invalid_after(sim, mark, lambda: sim.set_flex_uv("left", "ring", 0),
                                     "left")
    check("hub invalidates on a left sensor fault", command["reason"] == "left_not_ready",
          command["reason"])
    check(f"sensor-fault-to-invalid <= {FAULT_TO_INVALID_MS} ms", latency <= FAULT_TO_INVALID_MS,
          f"{latency:.0f} ms")
    sim.set_flex_uv("left", "ring", EXTENDED_UV)
    sim.run_for(0.5)
    check("repaired sensor alone does not resume", sim.latest_command()["valid"] == 0,
          sim.latest_command()["reason"])
    enable_cycle(sim)
    command = sim.wait_command(lambda c: c["valid"], timeout=0.5)
    check("release and a new press resume after repair", command["valid"] == 1)

    print("\nright hand reboots (link lost, new session):", flush=True)
    sim.send_line("right", "cal save")
    sim.run_for(0.3)
    old_session = sim.query("hub", "status", "status")["hands"][1]["session"]
    mark = sim.mark("hub")
    command, latency = invalid_after(sim, mark, lambda: sim.send_line("right", "reboot"), "right")
    check("hub invalidates when the right hand resets",
          command["reason"] in ("right_missing", "right_stale", "right_frozen"), command["reason"])
    check(f"reset-to-invalid <= {FAULT_TO_INVALID_MS} ms", latency <= FAULT_TO_INVALID_MS,
          f"{latency:.0f} ms")
    right = {}
    for _ in range(40):                              # up to ~6 s
        right = sim.query("hub", "status", "status")["hands"][1]
        if right["connects"] >= 2 and right["ready"] and right["age_us"] < 100000:
            break
        sim.run_for(0.1)
    check("right hand relinks by itself", right["connects"] >= 2 and right["ready"] == 1,
          f"connects={right['connects']} age_us={right['age_us']}")
    check("rebooted hand reports a new session", right["session"] != old_session,
          f"{old_session} -> {right['session']}")
    sim.run_for(0.5)
    command = sim.latest_command()
    check("a relinked hand does not resurrect permission", command["valid"] == 0,
          command["reason"])
    enable_cycle(sim)
    command = sim.wait_command(lambda c: c["valid"], timeout=0.6)
    check("deliberate re-enable resumes with the rebooted hand", command["valid"] == 1,
          command["reason"])

    print("\nhub CALIBRATE captures neutral on both hands:", flush=True)
    sim.set_enable(False)
    sim.run_for(0.2)
    tilt(sim, "left", roll=3000)                     # both hands resting slightly tilted
    tilt(sim, "right", pitch=3000)
    sim.run_for(0.2)
    marks = {h: sim.mark(h) for h in ("left", "right")}
    mark = sim.mark("hub")
    sim.set_calibrate(True)
    command = sim.wait_command(lambda c: c["reason"] == "calibrating", timeout=0.3, since=mark)
    check("output inhibited while CALIBRATE is held", command["valid"] == 0, command["reason"])
    for hand in ("left", "right"):
        neutral = sim.wait_for(hand, lambda rows: next(
            (r for r in rows if r.get("type") == "neutral" and r.get("source") == "hub"), None),
            timeout=0.5, since=marks[hand])
        check(f"{hand} captured neutral on the hub's request",
              neutral["result"] == 0 and neutral["valid"] == 1, str(neutral))
    sim.set_calibrate(False)
    sim.run_for(0.2)
    enable_cycle(sim)
    command = sim.wait_command(lambda c: c["valid"], timeout=0.5)
    command = settle(sim, 0.6)
    check("the new resting posture now commands zero",
          command["valid"] == 1 and command["pitch"] == 0 and command["yaw"] == 0, str(command))

    malformed = [(n, r["line"][:80]) for n in ("left", "right", "hub")
                 for r in sim.console[n].records() if r.get("type") == "malformed"]
    check("every console line is well-formed JSON", not malformed, str(malformed[:3]))
    panics = [n for n in ("left", "right", "hub") if "Guru Meditation" in sim.console[n].text]
    check("no firmware panic on any board", not panics, str(panics))

    sim.save("s2b_controller.json", {
        "test": "S2-B whole controller: two hands, hub, one command",
        "scope": "three ESP32-S3 machines, modeled ADC/GPIO/I2C/BLE; provisional limits; "
                 "not human-hand, noise, RF or physical timing evidence",
        "limits": {"enable_latency_s": ENABLE_LATENCY_S, "axis_tolerance": AXIS_TOLERANCE,
                   "slew_attitude": SLEW_ATTITUDE, "slew_throttle": SLEW_THROTTLE,
                   "fault_to_invalid_ms": FAULT_TO_INVALID_MS},
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
