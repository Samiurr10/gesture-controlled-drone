#!/usr/bin/env python3
"""S2-A: both hands linked to the hub over BLE (FW-04 transport binding).

    python3 firmware/tools/palmpilot.py system firmware/tests/s2a_link.py

LEFT, RIGHT and HUB run their real images as three ESP32-S3 machines on one
simulated BLE medium. Nothing reaches the hub except over the radio.

Acceptance limits, fixed before the run (PROVISIONAL; FW-04 leaves rates UNSET):
  * both hands linked within 5 s of power-on
  * negotiated ATT MTU carries a whole 59-byte packet (>= 62)
  * each hand delivers >= 45 accepted packets per second (50 Hz nominal)
  * zero packets rejected (CRC, framing, wrong side, replay)
  * the two hands report distinct sessions and distinct Bluetooth addresses

What this does not establish: RF range, interference, coexistence, power, or
anything about the physical radio. The simulated medium is lossless.
"""
import sys

from controller import ControllerSim

LINK_DEADLINE_S = 5.0
MIN_RATE_HZ = 45
RATE_WINDOW_S = 2.0
EXTENDED_UV = 2154000

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


with ControllerSim() as sim:
    for hand in ("left", "right"):
        sim.set_hand_uv(hand, EXTENDED_UV)
    sim.set_enable(False)
    sim.set_calibrate(False)

    print("boot:", flush=True)
    for hand, side in (("left", 0), ("right", 1)):
        ready = sim.wait_for_type(hand, "ready", timeout=3.0)
        check(f"{hand} hand boots as side {side}", ready.get("side") == side, str(ready))
    sim.wait_for_type("hub", "ready", timeout=3.0)

    print("\nlink:", flush=True)
    try:
        status = sim.wait_linked(timeout=LINK_DEADLINE_S)
        linked_at = sim.time()
        check(f"both hands linked within {LINK_DEADLINE_S:.0f} s", True, f"at {linked_at:.2f} s")
    except AssertionError as error:
        check(f"both hands linked within {LINK_DEADLINE_S:.0f} s", False, str(error)[:300])
        status = None

    if status:
        for entry in status["hands"]:
            check(f"{entry['side']} MTU carries a whole packet", entry["mtu"] >= 62,
                  f"mtu={entry['mtu']}")
        before = {h["side"]: h["accepted"] for h in status["hands"]}
        sim.run_for(RATE_WINDOW_S)
        after = sim.query("hub", "status", "status")
        for entry in after["hands"]:
            rate = (entry["accepted"] - before[entry["side"]]) / RATE_WINDOW_S
            check(f"{entry['side']} delivers >= {MIN_RATE_HZ} packets/s", rate >= MIN_RATE_HZ,
                  f"{rate:.1f}/s")
            check(f"{entry['side']} no rejected packets", not any(entry["rejected"].values()),
                  f"rejected={entry['rejected']}")
            check(f"{entry['side']} stays linked (no drops)", entry["drops"] == 0,
                  f"drops={entry['drops']}")
        sessions = [h["session"] for h in after["hands"]]
        check("hands report distinct sessions", sessions[0] != sessions[1], str(sessions))

        addresses = {}
        for hand in ("left", "right"):
            link = sim.query(hand, "link", "link")
            check(f"{hand} sees itself connected and subscribed",
                  link["connected"] == 1 and link["subscribed"] == 1, str(link))
            events = [r for r in sim.console[hand].records() if r.get("type") == "link"]
            addresses[hand] = events[0].get("addr") if events else None
        check("hands advertise distinct addresses",
              addresses["left"] and addresses["left"] != addresses["right"], str(addresses))

    malformed = [(n, r["line"][:80]) for n in ("left", "right", "hub")
                 for r in sim.console[n].records() if r.get("type") == "malformed"]
    check("every console line is well-formed JSON", not malformed, str(malformed[:3]))
    panics = [n for n in ("left", "right", "hub") if "Guru Meditation" in sim.console[n].text]
    check("no firmware panic on any board", not panics, str(panics))

    sim.save("s2a_link.json", {
        "test": "S2-A hand-hub BLE link",
        "scope": "three ESP32-S3 machines on a lossless simulated BLE medium; "
                 "provisional limits; no RF, range or coexistence claim",
        "limits": {"link_deadline_s": LINK_DEADLINE_S, "min_rate_hz": MIN_RATE_HZ},
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
