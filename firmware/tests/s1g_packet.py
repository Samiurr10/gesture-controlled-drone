#!/usr/bin/env python3
"""S1-G: hand -> hub packet contract (FW-04).

    python3 firmware/tools/palmpilot.py run firmware/apps/hand \
        firmware/tests/s1g_packet.py

The decoder below is written independently of the firmware, from the layout in
packet.h, so a passing round trip means the contract is actually interoperable
rather than two copies of the same code agreeing.

Scope: this freezes the payload only. The BLE stack is unqualified on this
platform, so transport binding, MTU, notification rate, bonding and reconnect
are NOT covered and remain S2 work.
"""
import struct
import sys
import zlib
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
PACKET_SIZE, PACKET_VERSION = 59, 1
(FLAG_VALID, FLAG_ENABLE, FLAG_CALIBRATED, FLAG_HOLD,
 FLAG_PRECISION, FLAG_MOTION_OK, FLAG_USB_POWER) = (1 << i for i in range(7))

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def decode(raw: bytes) -> dict:
    """Independent decoder. Framing is checked before any field is read."""
    if len(raw) != PACKET_SIZE:
        raise ValueError(f"wrong length {len(raw)}")
    if raw[0] != PACKET_VERSION:
        raise ValueError(f"wrong version {raw[0]}")
    if raw[1] != PACKET_SIZE:
        raise ValueError(f"declared length {raw[1]} != {PACKET_SIZE}")
    crc = struct.unpack_from("<I", raw, 55)[0]
    if zlib.crc32(raw[:55]) & 0xFFFFFFFF != crc:
        raise ValueError("CRC mismatch")
    side, state, fault = raw[2], raw[3], raw[4]
    flags, session, sequence, acquisition = struct.unpack_from("<HIII", raw, 5)
    (timestamp,) = struct.unpack_from("<q", raw, 19)
    curl = list(struct.unpack_from("<5h", raw, 27))
    accel = list(struct.unpack_from("<3h", raw, 37))
    gyro = list(struct.unpack_from("<3h", raw, 43))
    roll, pitch, throttle = struct.unpack_from("<3h", raw, 49)
    return dict(side=side, state=state, fault=fault, flags=flags, session=session,
                sequence=sequence, acquisition=acquisition, timestamp=timestamp,
                curl=curl, accel=accel, gyro=gyro, roll=roll, pitch=pitch,
                throttle=throttle)


def command(sim, line, kind, timeout=8.0, step=0.05):
    mark = len(sim.stream)
    sim.send_line(line)
    return sim.wait_for_type(kind, timeout=timeout, step=step, since=mark)


def packet(sim) -> dict:
    row = command(sim, "packet", "packet")
    return decode(bytes.fromhex(row["hex"]))


def set_all(sim, microvolts, settle=0.15):
    for finger in FINGERS:
        sim.set_flex_uv(finger, microvolts)
    sim.run_for(settle)


imu_state.reset()
with PalmPilotSim(i2c=FIXTURES, timg=True) as sim:
    sim.set_enable(False)
    set_all(sim, EXTENDED_UV, settle=0.0)
    sim.wait_ready(timeout=6.0)

    print("framing:", flush=True)
    row = command(sim, "packet", "packet")
    raw = bytes.fromhex(row["hex"])
    check("fixed packet size", len(raw) == PACKET_SIZE and row["bytes"] == PACKET_SIZE,
          f"{len(raw)} bytes")
    check("independent decode succeeds", decode(raw)["side"] == 0)

    corrupted = bytearray(raw)
    corrupted[30] ^= 0xFF
    try:
        decode(bytes(corrupted))
        check("corrupt payload rejected", False, "decoder accepted it")
    except ValueError as exc:
        check("corrupt payload rejected", "CRC" in str(exc), str(exc))

    truncated = raw[:-1]
    try:
        decode(truncated)
        check("truncated packet rejected", False, "decoder accepted it")
    except ValueError as exc:
        check("truncated packet rejected", True, str(exc))

    print("\nidentity and counters:", flush=True)
    # One packet per 20 ms control update, whether or not a hub is linked, so
    # over 0.2 s of virtual time the sequence advances by about ten. The window
    # also contains the `packet` round trip (up to ~0.1 s), hence the band.
    first = decode(raw)
    sim.run_for(0.2)
    second = packet(sim)
    check("session stable within a boot", first["session"] == second["session"],
          hex(first["session"]))
    advanced = second["sequence"] - first["sequence"]
    check("sequence advances once per control update", 9 <= advanced <= 16,
          f"{first['sequence']} -> {second['sequence']} (+{advanced} in ~0.2 s)")
    check("hand side carried", second["side"] == 0)
    check("USB bench power declared explicitly", bool(second["flags"] & FLAG_USB_POWER))
    check("uncalibrated hand says so", not second["flags"] & FLAG_CALIBRATED)
    check("uncalibrated hand is not valid", not second["flags"] & FLAG_VALID)

    print("\ncalibrate and carry real values:", flush=True)
    set_all(sim, EXTENDED_UV)
    mark = len(sim.stream)
    sim.send_line("cal extended")
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    set_all(sim, CURLED_UV)
    mark = len(sim.stream)
    sim.send_line("cal curled")
    sim.wait_for_type("capture", timeout=6.0, since=mark)
    command(sim, "cal neutral", "neutral")
    command(sim, "cal finish", "calibration")
    set_all(sim, EXTENDED_UV)

    imu_state.accel[:] = [111, -222, 16000]
    imu_state.gyro[:] = [-33, 44, -55]
    sim.run_for(0.4)
    row = packet(sim)
    check("calibrated flag set", bool(row["flags"] & FLAG_CALIBRATED))
    check("motion health flagged", bool(row["flags"] & FLAG_MOTION_OK))
    check("accelerometer carried verbatim", row["accel"] == [111, -222, 16000],
          str(row["accel"]))
    check("gyroscope carried verbatim", row["gyro"] == [-33, 44, -55], str(row["gyro"]))
    check("extended fingers read zero curl", row["curl"] == [0, 0, 0, 0, 0],
          str(row["curl"]))

    print("\ncommand fields and bounds:", flush=True)
    imu_state.set_tilt(roll_component=imu_state.ACCEL_LSB_PER_G // 2)
    sim.run_for(0.8)
    row = packet(sim)
    check("roll reaches the bound, never exceeds it", row["roll"] == 1000, str(row["roll"]))
    check("every axis within [-1000, 1000]",
          all(-1000 <= v <= 1000 for v in (row["roll"], row["pitch"], row["throttle"])),
          f"{row['roll']}/{row['pitch']}/{row['throttle']}")
    check("throttle within [0, 1000]", 0 <= row["throttle"] <= 1000, str(row["throttle"]))

    print("\npermission is carried, not inferred:", flush=True)
    imu_state.set_tilt()
    set_all(sim, EXTENDED_UV)
    sim.run_for(0.4)
    row = packet(sim)
    check("not valid before a deliberate press", not row["flags"] & FLAG_VALID)
    sim.set_enable(True)
    sim.run_for(0.3)
    row = packet(sim)
    check("valid after release-then-press", bool(row["flags"] & FLAG_VALID))
    check("ENABLE state carried", bool(row["flags"] & FLAG_ENABLE))
    sim.set_enable(False)
    sim.run_for(0.3)
    row = packet(sim)
    check("release clears validity in the packet", not row["flags"] & FLAG_VALID)

    print("\nfrozen sampling behind a live link (the FW-04 case):", flush=True)
    # Take the reference only after the stall is acknowledged: the round trip
    # to send it advances time, during which sampling is still running.
    command(sim, "stall 60", "stalling")
    before = packet(sim)
    sim.run_for(0.1)
    during = packet(sim)
    check("packets keep flowing while sampling is stopped",
          during["sequence"] > before["sequence"],
          f"{before['sequence']} -> {during['sequence']}")
    check("acquisition counter does NOT advance",
          during["acquisition"] == before["acquisition"],
          f"{before['acquisition']} -> {during['acquisition']}")
    check("sample timestamp does NOT advance",
          during["timestamp"] == before["timestamp"])
    check("hand reports itself faulted", during["fault"] == 3 and
          not during["flags"] & FLAG_VALID, f"fault={during['fault']}")
    sim.run_for(1.2)
    after = packet(sim)
    check("acquisition resumes", after["acquisition"] > during["acquisition"],
          f"{during['acquisition']} -> {after['acquisition']}")

    sim.save("s1g-packet.json", {
        "test": "S1-G hand to hub packet contract",
        "scope": "payload only, decoded independently; BLE transport, MTU, "
                 "rate, bonding and reconnect are NOT covered",
        "checks": [{"name": n, "passed": o, "detail": d} for n, o, d in checks],
        "passed": not failures,
    })

imu_state.reset()
print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
