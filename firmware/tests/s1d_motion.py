#!/usr/bin/env python3
"""S1-D: external motion module driver (FW-02, CTRL-021).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1d_motion.py

Drives the LSM6DS3TR-C (0x6A) and LIS3MDL (0x1C) register fixtures through the
real ESP-IDF i2c_master driver: identity, configuration writes, status
data-ready gating, the auto-incrementing burst read and the absent-device path.

Scope limits. These are register fixtures, not sensor models: no ODR timing,
filtering, FIFO, interrupts, self-test or noise, and values change the instant
the test mutates them. The platform does not simulate GPIO-matrix routing, so
SDA/SCL on GPIO8/9 is NOT covered here and must be verified physically at C2.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("firmware/tests/fixtures").resolve()))

import imu_state                                             # noqa: E402
from harness import PalmPilotSim                             # noqa: E402

FIXTURES = {
    0x6A: "firmware/tests/fixtures/lsm6ds3trc.py",
    0x1C: "firmware/tests/fixtures/lis3mdl.py",
}
MOTION_OK, MOTION_ERR_BUS, MOTION_ERR_IDENTITY, MOTION_ERR_NOT_READY = 0, 1, 2, 3

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


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES, timg=True) as sim:
    sim.set_enable(False)
    sim.wait_ready(timeout=5.0)
    info = next(r for r in sim.records() if r.get("type") == "info")

    print("bus and identity:", flush=True)
    check("motion init succeeded", info.get("motion_init") == 1)
    check("I2C pins reported", info.get("i2c_sda") == 8 and info.get("i2c_scl") == 9,
          f"SDA={info.get('i2c_sda')} SCL={info.get('i2c_scl')}")
    sim.run_for(0.2)
    row = command(sim, "motion", "motion")
    check("LSM6DS3TR-C identity 0x6A", row["id_accel_gyro"] == 0x6A,
          hex(row["id_accel_gyro"]))
    check("LIS3MDL identity 0x3D", row["id_mag"] == 0x3D, hex(row["id_mag"]))
    check("accel/gyro read OK", row["accel_gyro"] == MOTION_OK, str(row["accel_gyro"]))
    check("magnetometer read OK", row["mag_status"] == MOTION_OK, str(row["mag_status"]))

    print("\nresting orientation:", flush=True)
    check("gravity on +Z at rest", row["accel"] == [0, 0, imu_state.ACCEL_LSB_PER_G],
          str(row["accel"]))
    check("no rotation at rest", row["gyro"] == [0, 0, 0], str(row["gyro"]))

    print("\nburst decode, distinct signed values per axis:", flush=True)
    imu_state.accel[:] = [-1234, 5678, 16000]
    imu_state.gyro[:] = [321, -4321, 999]
    imu_state.mag[:] = [-100, 200, -300]
    sim.run_for(0.2)
    row = command(sim, "motion", "motion")
    check("accel axes decoded", row["accel"] == [-1234, 5678, 16000], str(row["accel"]))
    check("gyro axes decoded", row["gyro"] == [321, -4321, 999], str(row["gyro"]))
    check("mag axes decoded", row["mag"] == [-100, 200, -300], str(row["mag"]))

    print("\nfull-scale signed extremes:", flush=True)
    imu_state.accel[:] = [-32768, 32767, -1]
    sim.run_for(0.2)
    row = command(sim, "motion", "motion")
    check("int16 extremes survive the burst", row["accel"] == [-32768, 32767, -1],
          str(row["accel"]))

    print("\ndata-ready gating:", flush=True)
    imu_state.reset()
    imu_state.data_ready = False
    sim.run_for(0.2)
    row = command(sim, "motion", "motion")
    check("no new data -> NOT_READY", row["accel_gyro"] == MOTION_ERR_NOT_READY,
          str(row["accel_gyro"]))
    check("magnetometer also gated", row["mag_status"] == MOTION_ERR_NOT_READY,
          str(row["mag_status"]))
    check("stale data not presented as fresh", row["accel"] == [0, 0, 0],
          str(row["accel"]))

    imu_state.data_ready = True
    sim.run_for(0.2)
    row = command(sim, "motion", "motion")
    check("recovers when data returns", row["accel_gyro"] == MOTION_OK)

    # The fixture stops returning data but still occupies the address, so this
    # models a sensor that has gone silent, NOT a bus-level NACK from an
    # unpopulated address. A physically disconnected module must be tested at
    # CTRL-021; this cannot establish that path.
    print("\nsensor stops responding:", flush=True)
    imu_state.accel_gyro_present = False
    sim.run_for(0.3)
    row = command(sim, "motion", "motion")
    check("silent accel/gyro reports a fault, never data",
          row["accel_gyro"] != MOTION_OK, f"status={row['accel_gyro']}")
    check("silent device yields no data", row["accel"] == [0, 0, 0], str(row["accel"]))
    check("magnetometer unaffected on the same bus",
          row["mag_status"] == MOTION_OK, str(row["mag_status"]))

    imu_state.accel_gyro_present = True
    sim.run_for(0.3)
    row = command(sim, "motion", "motion")
    check("recovers when the device returns", row["accel_gyro"] == MOTION_OK,
          str(row["accel_gyro"]))

    sim.save("s1d-motion.json", {
        "test": "S1-D external motion module driver",
        "scope": "register fixtures through the real i2c_master driver; "
                 "no ODR/filter/FIFO/interrupt behavior, no GPIO-matrix routing, "
                 "and no bus-level NACK from an unpopulated address",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

# Identity is checked once at init, so a wrong sensor needs its own boot.
print("\nwrong sensor at the expected address (separate boot):", flush=True)
imu_state.reset()
imu_state.whoami_accel_gyro = 0x69          # some other device answering 0x6A
with PalmPilotSim(i2c=FIXTURES, timg=True,
                  out=Path("tmp/palmpilot/hand/identity")) as sim:
    sim.set_enable(False)
    sim.wait_ready(timeout=5.0)
    sim.run_for(0.2)
    row = command(sim, "motion", "motion")
    check("wrong WHO_AM_I rejected", row["accel_gyro"] == MOTION_ERR_IDENTITY,
          f"status={row['accel_gyro']} id={hex(row['id_accel_gyro'])}")
    check("rejected sensor yields no data", row["accel"] == [0, 0, 0], str(row["accel"]))

imu_state.reset()
print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
