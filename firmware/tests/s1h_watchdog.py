#!/usr/bin/env python3
"""S1-H: task watchdog fed only by real work (FW-06).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1h_watchdog.py

FW-06 requires the watchdog to be serviced only after acquisition, validation
and the output stage have actually progressed - "a timer-only feed does not
establish application health". That rule is what this test verifies, through
the firmware's feed counter: services advance during healthy operation and stop
the moment sampling stalls, even though every task is still scheduled and the
UART still answers.

The timeout itself is now exercised too: the timer-group model counts and
raises the watchdog interrupt, so starving the loop past the period trips
ESP-IDF's real task watchdog.

BLOCKED: the panic and the reset. Bench firmware sets trigger_panic false so a
trip is observable instead of resetting, because esp_restart aborts this engine
(firmware/probes/reset/README.md). Production must enable trigger_panic, and
what state the firmware returns in after a watchdog reset is physical-only at C2.
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
EXTENDED_UV = 2154000

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def command(sim, line, kind, timeout=8.0, step=0.05):
    mark = len(sim.stream)
    sim.send_line(line)
    return sim.wait_for_type(kind, timeout=timeout, step=step, since=mark)


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES, timg=True) as sim:
    sim.set_enable(False)
    for finger in FINGERS:
        sim.set_flex_uv(finger, EXTENDED_UV)
    sim.wait_ready(timeout=6.0)

    print("configuration:", flush=True)
    sim.run_for(0.4)
    stats = command(sim, "stats", "stats")
    check("watchdog subscribed by the control task", stats["watchdog"] == 1)
    check("no trips at startup", stats["watchdog_trips"] == 0,
          str(stats["watchdog_trips"]))

    print("\nhealthy loop services it:", flush=True)
    before = command(sim, "stats", "stats")
    sim.run_for(2.0)
    stats = command(sim, "stats", "stats")
    check("watchdog serviced while healthy",
          stats["watchdog_feeds"] > before["watchdog_feeds"],
          f"{before['watchdog_feeds']} -> {stats['watchdog_feeds']}")
    check("acquisition genuinely advancing", stats["acq"] > 200, str(stats["acq"]))

    print("\nbrief stall stops the service without tripping:", flush=True)
    # 60 sweeps at 100 Hz is about 600 ms: enough to freeze the service, still
    # inside the 1000 ms period, so the discipline is visible on its own.
    command(sim, "stall 60", "stalling")
    during = command(sim, "stats", "stats")
    sim.run_for(0.4)
    stalled = command(sim, "stats", "stats")
    check("watchdog NOT serviced while sampling is stalled",
          stalled["watchdog_feeds"] == during["watchdog_feeds"],
          f"{during['watchdog_feeds']} -> {stalled['watchdog_feeds']}")
    check("control task still running, so this is a deliberate refusal",
          stalled["watchdog"] == 1 and stalled["ticks"] > during["ticks"],
          f"ticks {during['ticks']} -> {stalled['ticks']}")
    check("no trip inside the period", stalled["watchdog_trips"] == 0,
          str(stalled["watchdog_trips"]))
    state = command(sim, "control", "control")
    check("command invalid while stalled", state["valid"] == 0, state["state"])

    print("\nservice resumes once sampling does:", flush=True)
    sim.run_for(1.5)
    resumed = command(sim, "stats", "stats")
    check("watchdog serviced again after recovery",
          resumed["watchdog_feeds"] > stalled["watchdog_feeds"],
          f"{stalled['watchdog_feeds']} -> {resumed['watchdog_feeds']}")

    print("\nstall past the period actually trips it:", flush=True)
    command(sim, "stall 300", "stalling")   # 3 s, well past the 1000 ms period
    sim.run_for(2.5)
    tripped = command(sim, "stats", "stats")
    check("watchdog timeout fired", tripped["watchdog_trips"] > 0,
          f"trips={tripped['watchdog_trips']}")
    check("ESP-IDF reported the timeout",
          "Task watchdog got triggered" in sim.text)
    check("firmware still alive, because bench build does not panic",
          tripped["watchdog"] == 1 and tripped["ticks"] > resumed["ticks"])

    sim.run_for(1.5)                        # let the stall expire
    recovered = command(sim, "stats", "stats")
    check("service resumes after the trip",
          recovered["watchdog_feeds"] > tripped["watchdog_feeds"],
          f"{tripped['watchdog_feeds']} -> {recovered['watchdog_feeds']}")

    sim.save("s1h-watchdog.json", {
        "test": "S1-H task watchdog",
        "scope": "service discipline and the real timeout, against the "
                 "timer-group model under test",
        "blocked": [
            "panic and reset after a trip - esp_restart aborts the engine",
            "post-reset state - physical-only at C2",
        ],
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

imu_state.reset()
print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
