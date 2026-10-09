#!/usr/bin/env python3
"""S1-A: five-channel acquisition, fault classification and ENABLE debounce.

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1a_acquisition.py

Stimulus is injected as voltages at the modeled ADC and as levels at the
modeled GPIO, so it traverses the real esp_adc / gpio drivers. Nothing writes
application state. The ADC model is noise-free and uses the modeled die's
eFuse calibration: these results validate the model's calibrated contract and
the firmware's logic, never analog accuracy.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("firmware/tests/fixtures").resolve()))

import imu_state                                             # noqa: E402
from harness import ADC_MV_TOLERANCE, FLEX, PalmPilotSim  # noqa: E402

ATTEN = 3
FINGERS = list(FLEX)
# Distinct per-finger levels so a channel-identity error cannot pass.
PROBE_UV = dict(zip(FINGERS, (200000, 400000, 600000, 800000, 1000000)))

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


def sample(sim):
    mark = len(sim.stream)
    sim.send_line("sample")
    return sim.wait_for_type("sample", timeout=3.0, since=mark)


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES, timg=True) as sim:
    print("boot and identity:", flush=True)
    sim.set_enable(False)                      # released before anything else
    ready = sim.wait_ready(timeout=5.0)
    check("reaches ready", ready.get("type") == "ready")
    boot = next(r for r in sim.records() if r.get("type") == "boot")
    check("boot marker precedes init", boot.get("fixture") == "palmpilot-hand-v1")
    info = next(r for r in sim.records() if r.get("type") == "info")
    check("fixture identity", info.get("fixture") == "palmpilot-hand-v1",
          f"idf={info.get('idf')} period={info.get('sample_period_us')}us")
    check("flex pin map", info.get("flex_gpio") == [1, 2, 4, 5, 6],
          str(info.get("flex_gpio")))
    check("enable pin", info.get("enable_gpio") == 7)
    check("ADC calibration created", info.get("adc_calibrated") == 1)

    print("\nfree-running acquisition (esp_timer):", flush=True)
    for finger, uv in PROBE_UV.items():
        sim.set_flex_uv(finger, uv)
    sim.run_for(0.5)
    mark = len(sim.stream)
    sim.send_line("stats")
    first = sim.wait_for_type("stats", since=mark)
    sim.run_for(0.5)
    mark = len(sim.stream)
    sim.send_line("stats")
    second = sim.wait_for_type("stats", since=mark)
    check("timer ticks advance", second["ticks"] > first["ticks"] > 0,
          f"{first['ticks']} -> {second['ticks']}")
    check("acquisition advances with ticks", second["acq"] > first["acq"] > 0,
          f"{first['acq']} -> {second['acq']}")
    check("no acquisition overruns", second["overruns"] == 0,
          f"overruns={second['overruns']}")

    print("\nchannel identity and calibrated millivolts:", flush=True)
    # Raw counts are die-specific (eFuse calibration), so the contract is the
    # calibrated millivolts; raw must only be off the rails and rise with the
    # injected voltage, which PROBE_UV orders thumb -> little.
    row = sample(sim)
    for index, finger in enumerate(FINGERS):
        expected_mv = PROBE_UV[finger] // 1000
        raw = row["raw"][index]
        ok = (abs(row["mv"][index] - expected_mv) <= ADC_MV_TOLERANCE
              and 0 < raw < 4095 and row["status"][index] == 0
              and (index == 0 or raw > row["raw"][index - 1]))
        check(f"{finger:<6} GPIO{FLEX[finger]['gpio']}", ok,
              f"{expected_mv} mV -> mv={row['mv'][index]} (±{ADC_MV_TOLERANCE}) "
              f"raw={raw}")
    check("healthy with all channels in range", row["healthy"] == 1 and row["fault_mask"] == 0)

    print("\nfault classification (near-rail is a fault, never a command):", flush=True)
    sim.set_flex_uv("middle", 0)               # unplugged: pulled to GND via 47k
    sim.run_for(0.2)
    row = sample(sim)
    check("open circuit -> FLEX_FAULT_OPEN", row["status"][2] == 1,
          f"raw={row['raw'][2]} status={row['status'][2]}")
    check("fault_mask marks only the middle channel", row["fault_mask"] == 0b00100,
          bin(row["fault_mask"]))
    check("sample reported unhealthy", row["healthy"] == 0)

    # 4.4 V saturates the model in both its ideal and calibrated modes, while
    # silicon saturates at the
    # 3V3 rail. Reaching the short guard therefore needs a voltage that is not
    # physically applicable. This exercises the classifier only; the physical
    # short case must be measured at C1/CTRL-011.
    sim.set_flex_uv("middle", 4400000)
    sim.run_for(0.2)
    row = sample(sim)
    check("rail saturation -> FLEX_FAULT_SHORT [MODEL-ONLY]", row["status"][2] == 2,
          f"raw={row['raw'][2]} status={row['status'][2]}")

    sim.set_flex_uv("middle", PROBE_UV["middle"])
    sim.run_for(0.2)
    row = sample(sim)
    check("recovers to healthy when restored", row["healthy"] == 1 and row["fault_mask"] == 0)

    print("\nENABLE on GPIO7 (active low, debounced):", flush=True)
    row = sample(sim)
    check("released reads inactive", row["enable"] == 0)
    sim.set_enable(True)
    sim.run_for(0.2)
    row = sample(sim)
    check("pressed reads active", row["enable"] == 1)
    sim.set_enable(False)
    sim.run_for(0.2)
    row = sample(sim)
    check("release returns inactive", row["enable"] == 0)

    sim.save("s1a-acquisition.json", {
        "test": "S1-A acquisition, faults, ENABLE",
        "scope": "modeled ADC/GPIO drivers; calibrated-state ADC model, not analog accuracy",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
