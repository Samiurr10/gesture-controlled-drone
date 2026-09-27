#!/usr/bin/env python3
"""S1-B: calibration capture, rejection cases and curl normalisation (FW-03).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1b_calibration.py

Voltages come from the build guide's divider examples at a 3.300 V rail:
Adafruit #1070 is about 25 kOhm extended and 100 kOhm bent, which through the
47 kOhm shunt gives 2.154 V and 1.055 V. Bending raises resistance, so an
extended finger reads HIGH and a curled finger reads LOW.

These are calculated stimuli, not measured sensor ranges. CTRL-022 must measure
comfortable travel on a real hand before any of these limits are frozen.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("firmware/tests/fixtures").resolve()))

import imu_state                                             # noqa: E402
from harness import FLEX, PalmPilotSim                # noqa: E402

FINGERS = list(FLEX)
EXTENDED_UV = 2154000        # 25 kOhm flex
CURLED_UV = 1055000          # 100 kOhm flex
DEADBAND_MILLI = 30
MILLI = 1000

FIXTURES = {
    0x6A: "firmware/tests/fixtures/lsm6ds3trc.py",
    0x1C: "firmware/tests/fixtures/lis3mdl.py",
}

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def all_flex(sim, microvolts):
    for finger in FINGERS:
        sim.set_flex_uv(finger, microvolts)


def command(sim, line, kind, timeout=6.0):
    mark = len(sim.stream)
    sim.send_line(line)
    return sim.wait_for_type(kind, timeout=timeout, since=mark)


def capture(sim, end, timeout=6.0):
    """Start a capture and wait for the acquisition task to complete it."""
    mark = len(sim.stream)
    sim.send_line(f"cal {end}")
    sim.wait_for_type("capturing", timeout=3.0, since=mark)
    return sim.wait_for_type("capture", timeout=timeout, since=mark)


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES, timg=True) as sim:
    sim.set_enable(False)
    all_flex(sim, EXTENDED_UV)
    sim.wait_ready(timeout=5.0)

    print("uncalibrated state:", flush=True)
    row = command(sim, "sample", "sample")
    check("reports not calibrated", row["calibrated"] == 0)
    check("curl is -1 while uncalibrated", all(c == -1 for c in row["curl_milli"]),
          str(row["curl_milli"]))

    # A capture must average exactly what the acquisition path reads at that
    # voltage. Raw counts are die-specific, so the reference is the live sample,
    # not a formula; the calibrated millivolts are asserted in S1-A.
    print("\ncapture both ends:", flush=True)
    live = command(sim, "sample", "sample")["raw"]
    result = capture(sim, "extended")
    check("extended capture accepted", result["result"] == 0, result["reason"])
    check("extended mean matches live acquisition", result["mean"] == live,
          f"mean={result['mean']} live={live}")
    extended_live = live
    check("extended capture is stable", max(result["spread"]) == 0, str(result["spread"]))

    all_flex(sim, CURLED_UV)
    sim.run_for(0.2)
    live = command(sim, "sample", "sample")["raw"]
    result = capture(sim, "curled")
    check("curled capture accepted", result["result"] == 0, result["reason"])
    check("curled mean matches live acquisition", result["mean"] == live,
          f"mean={result['mean']} live={live}")
    check("curled reads below extended", max(live) < min(extended_live),
          f"{live} vs {extended_live}")

    result = command(sim, "cal neutral", "neutral")
    check("neutral orientation captured", result["result"] == 0, result["reason"])

    result = command(sim, "cal finish", "calibration")
    check("calibration validates", result["valid"] == 1, result["reason"])
    profile = command(sim, "profile", "profile")
    travel = profile["extended"][0] - profile["curled"][0]
    check("profile records both ends", travel > 200, f"travel={travel} counts")
    check("profile is versioned and sided",
          profile["version"] == 1 and profile["side"] in (0, 1),
          f"v{profile['version']} side={profile['side']}")

    print("\ncurl normalisation:", flush=True)
    all_flex(sim, CURLED_UV)
    sim.run_for(0.2)
    row = command(sim, "sample", "sample")
    check("full curl -> 1000 milli", all(c == MILLI for c in row["curl_milli"]),
          str(row["curl_milli"][0]))

    all_flex(sim, EXTENDED_UV)
    sim.run_for(0.2)
    row = command(sim, "sample", "sample")
    check("extended -> 0 milli (deadband)", all(c == 0 for c in row["curl_milli"]),
          str(row["curl_milli"][0]))

    midpoint_uv = (EXTENDED_UV + CURLED_UV) // 2
    all_flex(sim, midpoint_uv)
    sim.run_for(0.2)
    row = command(sim, "sample", "sample")
    expected_mid = (499 - DEADBAND_MILLI) * MILLI // (MILLI - DEADBAND_MILLI)
    check("midpoint -> ~483 milli after deadband rescale",
          all(abs(c - expected_mid) <= 3 for c in row["curl_milli"]),
          f"{row['curl_milli'][0]} expected ~{expected_mid}")

    print("\nrejection cases:", flush=True)
    command(sim, "cal reset", "calibration")

    # Sensor faulted during capture.
    all_flex(sim, EXTENDED_UV)
    sim.set_flex_uv("ring", 0)
    sim.run_for(0.2)
    result = capture(sim, "extended")
    check("faulted channel rejects capture", result["reason"] == "sensor_fault",
          result["reason"])

    # Hand still moving during capture.
    all_flex(sim, EXTENDED_UV)
    sim.run_for(0.2)
    mark = len(sim.stream)
    sim.send_line("cal extended")
    # A capture is 32 samples at 100 Hz, so about 320 ms. Step finely enough to
    # change the stimulus while the capture is still in progress.
    sim.wait_for_type("capturing", timeout=1.0, step=0.02, since=mark)
    sim.run_for(0.05)
    all_flex(sim, CURLED_UV)                 # moved mid-capture
    result = sim.wait_for_type("capture", timeout=6.0, since=mark)
    check("unstable capture rejected", result["reason"] == "unstable_capture",
          f"{result['reason']} spread={result['spread'][0]}")

    # Too little travel between the two ends.
    command(sim, "cal reset", "calibration")
    all_flex(sim, EXTENDED_UV)
    sim.run_for(0.2)
    capture(sim, "extended")
    all_flex(sim, EXTENDED_UV - 100000)      # only ~93 counts of travel
    sim.run_for(0.2)
    capture(sim, "curled")
    command(sim, "cal neutral", "neutral")
    result = command(sim, "cal finish", "calibration")
    check("insufficient travel rejected", result["reason"] == "insufficient_travel",
          result["reason"])
    check("invalid profile leaves calibration invalid", result["valid"] == 0)

    # Ends captured the wrong way round.
    command(sim, "cal reset", "calibration")
    all_flex(sim, CURLED_UV)
    sim.run_for(0.2)
    capture(sim, "extended")
    all_flex(sim, EXTENDED_UV)
    sim.run_for(0.2)
    capture(sim, "curled")
    command(sim, "cal neutral", "neutral")
    result = command(sim, "cal finish", "calibration")
    check("inverted ends rejected", result["reason"] == "inverted_ends", result["reason"])

    # One end never captured.
    command(sim, "cal reset", "calibration")
    all_flex(sim, EXTENDED_UV)
    sim.run_for(0.2)
    capture(sim, "extended")
    result = command(sim, "cal finish", "calibration")
    check("incomplete calibration rejected", result["reason"] == "incomplete",
          result["reason"])

    row = command(sim, "sample", "sample")
    check("rejected calibration yields no curl", all(c == -1 for c in row["curl_milli"]))

    sim.save("s1b-calibration.json", {
        "test": "S1-B calibration capture, rejection, normalisation",
        "scope": "calculated divider stimuli through the modeled ADC; not measured hand travel",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
