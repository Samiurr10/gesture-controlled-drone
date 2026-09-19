#!/usr/bin/env python3
"""S1-F: calibration persistence across reboot, and integrity rejection (FW-03).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1f_persistence.py

Exercises real NVS writes to the modeled SPI flash: save, reload and the
missing-profile path. The stored profile is never trusted on its own - validity
is re-derived after load.

BLOCKED here, and deliberately not attempted:

  * **Restore across a reboot.** esp_restart() aborts this engine
    (firmware/probes/reset/README.md). The behavior a user actually depends on
    - switching the hand on and finding it already calibrated - cannot be
    verified in simulation.
  * **Erase, and CRC rejection of a corrupt profile.** nvs_erase_key never
    returns in this application, and corrupting a stored blob needs the same
    write path (firmware/probes/nvs/README.md).

Both must be tested physically at C2/CTRL-022. Persistence is therefore
implemented but NOT QUALIFIED.

Scope: NVS against simulated flash only. No wear, no power loss during a write,
no silicon flash timing, no erase and no reboot.
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

(PERSIST_OK, PERSIST_ERR_UNAVAILABLE, PERSIST_ERR_MISSING, PERSIST_ERR_SIZE,
 PERSIST_ERR_VERSION, PERSIST_ERR_SIDE, PERSIST_ERR_CRC, PERSIST_ERR_WRITE) = range(8)

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


def set_all(sim, microvolts, settle=0.15):
    for finger in FINGERS:
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
    command(sim, "cal neutral", "neutral")
    result = command(sim, "cal finish", "calibration")
    set_all(sim, EXTENDED_UV)
    return result


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES) as sim:
    sim.set_enable(False)
    set_all(sim, EXTENDED_UV, settle=0.0)
    sim.wait_ready(timeout=6.0)

    print("first boot:", flush=True)
    restore = next(r for r in sim.records() if r.get("type") == "storage")
    check("NVS initialised", restore["available"] == 1)
    check("no stored profile yet", restore["status"] == PERSIST_ERR_MISSING,
          str(restore["status"]))
    check("hand starts uncalibrated", restore["calibrated"] == 0)

    print("\nsave a validated profile:", flush=True)
    result = calibrate(sim)
    check("calibration valid before save", result["valid"] == 1, result["reason"])
    profile = command(sim, "profile", "profile")
    saved_extended = profile["extended"]
    saved_neutral = profile["neutral"]
    result = command(sim, "cal save", "storage")
    check("save accepted", result["status"] == PERSIST_OK, str(result["status"]))

    print("\nreload from storage (reboot is BLOCKED, see probes/reset):", flush=True)
    command(sim, "cal reset", "calibration")
    state = command(sim, "control", "control")
    check("reset clears the in-memory profile", state["valid"] == 0, state["state"])
    result = command(sim, "cal load", "storage")
    check("stored profile loads back", result["status"] == PERSIST_OK,
          str(result["status"]))
    check("hand is calibrated without recapturing", result["calibrated"] == 1)
    profile = command(sim, "profile", "profile")
    check("flex ends preserved exactly", profile["extended"] == saved_extended,
          f"{profile['extended']} vs {saved_extended}")
    check("neutral orientation preserved", profile["neutral"] == saved_neutral,
          f"{profile['neutral']} vs {saved_neutral}")
    check("validity re-derived, not taken from storage", profile["valid"] == 1)

    print("\nloaded profile drives commands:", flush=True)
    set_all(sim, CURLED_UV)
    sim.run_for(0.6)
    state = command(sim, "control", "control")
    check("throttle works from the restored profile",
          state["throttle_milli"] == 1000, str(state["throttle_milli"]))
    set_all(sim, EXTENDED_UV)

    print("\nmissing profile:", flush=True)
    command(sim, "cal reset", "calibration")
    state = command(sim, "control", "control")
    check("reset hand commands nothing", state["valid"] == 0, state["state"])

    sim.save("s1f-persistence.json", {
        "test": "S1-F calibration persistence and integrity",
        "scope": "NVS on simulated SPI flash; save and reload only",
        "blocked": [
            "restore across reboot - esp_restart aborts the engine",
            "erase - nvs_erase_key never returns in this application",
            "CRC rejection on device - needs the same blocked write path",
            "all three are physical-only at C2/CTRL-022",
        ],
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

imu_state.reset()
print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
