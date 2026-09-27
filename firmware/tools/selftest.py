#!/usr/bin/env python3
"""Verify the PalmPilot toolchain end to end against the ADC reference app.

    python3 firmware/tools/palmpilot.py run \
        simulation/simantic/hardware-validation/esp32s3-adc \
        firmware/tools/selftest.py

Checks boot through the mask ROM, the public ESP-IDF ADC driver, injection on
each of the five planned flex channels, and ENABLE on GPIO7. It asserts the
calibrated millivolts ESP-IDF derives from the modeled die's eFuse, within
ADC_MV_TOLERANCE — the model's calibrated contract, not analog accuracy. Raw
counts are die-specific, so they are only checked for being off the rails,
repeatable and increasing with voltage.
"""
import sys

from harness import ADC_MV_TOLERANCE, FLEX, PalmPilotSim

ATTENUATION = 3           # ESP-IDF enum encoding; the widest documented span
PROBE_UV = {"thumb": 200000, "index": 400000, "middle": 600000,
            "ring": 800000, "little": 1000000}

failures, checks = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


with PalmPilotSim() as sim:
    print("boot:", flush=True)
    ready = sim.wait_ready()
    check("firmware reaches ready", ready.get("type") == "ready")
    info = next((r for r in sim.records() if r.get("type") == "info"), {})
    check("fixture identity", info.get("fixture") == "palmpilot-adc-v1",
          f"idf={info.get('idf')} cores={info.get('cores')} rev={info.get('revision')}")

    print("\nflex channels, attenuation 3:", flush=True)
    previous_raw = 0
    for finger, microvolts in PROBE_UV.items():
        channel = FLEX[finger]["channel"]
        expected_mv = microvolts // 1000
        sim.set_flex_uv(finger, microvolts)
        mark = len(sim.stream)
        sim.send_line(f"read {channel} {ATTENUATION} 4")
        sim.wait_for_type("end", timeout=4.0, since=mark)
        rows = sim.records(mark)
        samples = [r for r in rows if r.get("type") == "sample"]
        raws = {r["raw"] for r in samples}
        mvs = {r["mv"] for r in samples}
        raw = min(raws) if raws else 0
        ok = (len(samples) == 4
              and all(r["status"] == 0 and r["cal_status"] == 0 for r in samples)
              and len(raws) == 1 and 0 < raw < 4095 and raw > previous_raw
              and all(abs(mv - expected_mv) <= ADC_MV_TOLERANCE for mv in mvs))
        check(f"{finger:<6} GPIO{FLEX[finger]['gpio']} / ADC1_CH{channel}", ok,
              f"{expected_mv} mV -> {sorted(mvs)} mV (±{ADC_MV_TOLERANCE}) raw {sorted(raws)}")
        previous_raw = raw

    print("\nENABLE on GPIO7 (active low):", flush=True)
    try:
        sim.set_enable(True)
        sim.set_enable(False)
        check("inject_gpio accepted both levels", True)
    except Exception as exc:                       # noqa: BLE001 - reported, not raised
        check("inject_gpio accepted both levels", False, repr(exc))

    sim.save("selftest.json", {
        "scope": "toolchain chain check; calibrated-state ADC model, not analog accuracy",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
