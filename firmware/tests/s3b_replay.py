#!/usr/bin/env python3
"""S3-B: scripted BLE input from both controllers, through the hub, to ArduCopter.

    python3 firmware/tools/palmpilot.py system --replay firmware/tests/s3b_replay.py

The hands are replaced by apps/replay: the hand's own BLE peripheral sending
packets this script writes, byte for byte, in the frozen 59-byte layout
(packet.h). The hub firmware, the computer bridge and stock ArduCopter 4.7.1 are
the real ones. Every step sets what each controller sends, then checks three
points against the expected value computed here, independently of hub_core.c
and rc_link.py:

  hub      the hub's command line (roll, pitch, yaw, throttle, valid, reason)
  bridge   the RC channels the computer sends (rc_link.channels)
  drone    the RC channels ArduCopter reports back (RC_CHANNELS)

Limits fixed before the run (PROVISIONAL):
  * a step's hub command settles to the expected value within 1.0 s
  * between consecutive hub commands, attitude moves <= 80 and throttle <= 30
  * ArduCopter reports the expected channels exactly (+-0 us) within 0.5 s
  * while the command is invalid, no override is sent

Scope: the hand firmware's sensing and gesture logic are bypassed, so this
covers BLE transport, the hub, the bridge and ArduCopter's RC input only.
Disarmed, no vehicle physics. Mapping and rates are provisional.
"""
import struct
import sys
import zlib

from controller import ControllerSim, rc_link

LEFT, RIGHT = 0, 1
WAITING, PERMITTED, FAULT = 2, 3, 4
VALID, ENABLE, CALIBRATED, HOLD, PRECISION, MOTION_OK = (1 << i for i in range(6))
HEALTHY = CALIBRATED | MOTION_OK
SESSION = {LEFT: 0x1EF70001, RIGHT: 0x816E0002}
MAX_STEP = {"roll": 80, "pitch": 80, "yaw": 80, "throttle": 30}

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def packet(side, state=WAITING, flags=HEALTHY, fault=0, roll=0, pitch=0, throttle=0) -> bytes:
    """One hand packet, encoded from the packet.h layout. The replay hand
    advances sequence, acquisition and timestamp itself."""
    raw = bytearray(59)
    raw[0:5] = bytes([1, 59, side, state, fault])
    struct.pack_into("<HIII", raw, 5, flags, SESSION[side], 0, 0)
    struct.pack_into("<3h", raw, 49, roll, pitch, throttle)
    struct.pack_into("<I", raw, 55, zlib.crc32(raw[:55]) & 0xFFFFFFFF)
    return bytes(raw)


def ready(p):
    return p["fault"] == 0 and p["state"] in (WAITING, PERMITTED) and p["flags"] & HEALTHY == HEALTHY


class Expected:
    """What the hub should command, from the gesture mapping (gesture-mapping.md)."""

    def __init__(self):
        self.await_release, self.active = True, False
        self.hold_throttle, self.was_holding = 0, False
        self.throttle = 0

    def step(self, l, r, live):
        """l, r: packet fields; live: (left, right) still fresh and progressing."""
        reason = None
        for side, p, ok in (("left", l, live[0]), ("right", r, live[1])):
            if reason is None and not ok:
                reason = f"{side}_{ok is None and 'stale' or 'frozen'}"
            if reason is None and not ready(p):
                reason = f"{side}_not_ready"
        if reason is None and self.await_release and not l["flags"] & ENABLE:
            self.await_release = False
        if reason is None and not l["flags"] & VALID:
            reason = "not_enabled"
        if reason is None and self.await_release:
            reason = "await_release"
        if reason:
            self.await_release |= self.active
            self.active = self.was_holding = False
            self.throttle = 0
            return dict(valid=0, reason=reason, roll=0, pitch=0, yaw=0, throttle=0)
        self.active = True
        hold = bool(r["flags"] & HOLD)
        roll, pitch, yaw = r["roll"], r["pitch"], l["roll"]
        throttle = min(max(l["throttle"], 0), 1000)
        if hold:
            if not self.was_holding:
                self.hold_throttle = self.throttle
            roll = pitch = yaw = 0
            throttle = self.hold_throttle
        self.was_holding = hold
        if l["flags"] & PRECISION:
            roll, pitch, yaw = (int(v / 2) for v in (roll, pitch, yaw))
        clamp = lambda v: min(max(v, -1000), 1000)          # noqa: E731
        self.throttle = throttle
        return dict(valid=1, reason="ok", roll=clamp(roll), pitch=clamp(pitch),
                    yaw=clamp(yaw), throttle=throttle)


def rc_expected(c):
    """AETR, 1000..2000 us, pitch forward is a low ch2 (rc_link.py's contract)."""
    return [1500 + c["roll"] // 2, 1500 + -c["pitch"] // 2,
            1000 + c["throttle"], 1500 + c["yaw"] // 2]


def fields(side, **kw):
    p = dict(side=side, state=WAITING, flags=HEALTHY, fault=0, roll=0, pitch=0, throttle=0)
    p.update(kw)
    return p


# Each step: what each controller sends, and whether it is still sending
# (True), muted (None: packets stop) or frozen (False: packets, no new samples).
ARMED = dict(state=PERMITTED, flags=HEALTHY | VALID | ENABLE)
STEPS = [
    ("hands healthy, ENABLE not pressed", fields(LEFT), fields(RIGHT), (True, True)),
    ("ENABLE pressed, sticks centred", fields(LEFT, **ARMED), fields(RIGHT), (True, True)),
    ("right tilt, left tilt and half throttle",
     fields(LEFT, **ARMED, roll=-300, throttle=500), fields(RIGHT, roll=600, pitch=-400), (True, True)),
    ("PRECISION halves roll, pitch and yaw",
     fields(LEFT, state=PERMITTED, flags=HEALTHY | VALID | ENABLE | PRECISION, roll=-300, throttle=500),
     fields(RIGHT, roll=600, pitch=-400), (True, True)),
    ("HOLD zeroes attitude and freezes throttle",
     fields(LEFT, **ARMED, roll=-300, throttle=900),
     fields(RIGHT, flags=HEALTHY | HOLD, roll=600, pitch=-400), (True, True)),
    ("full deflection, out-of-range values clamped",
     fields(LEFT, **ARMED, roll=1000, throttle=1400), fields(RIGHT, roll=1500, pitch=-1000), (True, True)),
    ("right hand faults", fields(LEFT, **ARMED), fields(RIGHT, state=FAULT, fault=1), (True, True)),
    ("right hand healthy again: latched", fields(LEFT, **ARMED), fields(RIGHT), (True, True)),
    ("ENABLE released", fields(LEFT), fields(RIGHT), (True, True)),
    ("ENABLE pressed again", fields(LEFT, **ARMED, throttle=300), fields(RIGHT), (True, True)),
    ("right sampler stalls", fields(LEFT, **ARMED, throttle=300), fields(RIGHT), (True, False)),
    ("right recovers, ENABLE re-pressed",
     fields(LEFT, **ARMED, throttle=300), fields(RIGHT), (True, True), "repress"),
    ("left goes silent", fields(LEFT, **ARMED, throttle=300), fields(RIGHT), (None, True)),
]


def send(sim, side, p):
    name = "left" if side == LEFT else "right"
    hexed = packet(side, p["state"], p["flags"], p["fault"], p["roll"], p["pitch"], p["throttle"]).hex()
    if not sim.query(name, f"set {hexed}", "set")["ok"]:
        raise AssertionError(f"{name} rejected the packet")


def set_live(sim, live, current):
    for name, now, before in zip(("left", "right"), live, current):
        if now != before:
            sim.query(name, f"mute {1 if now is None else 0}", "mute")
            sim.query(name, f"freeze {1 if now is False else 0}", "freeze")


def run_until(sim, predicate, limit, step=0.05):
    start = sim.time()
    while sim.time() - start <= limit:
        if predicate():
            return sim.time() - start
        sim.run_for(step)
    return None


with ControllerSim(drone=True) as sim:
    sim.set_calibrate(False)
    for hand in ("left", "right"):
        sim.wait_for_type(hand, "ready", timeout=3.0)
    send(sim, LEFT, fields(LEFT))
    send(sim, RIGHT, fields(RIGHT))
    sim.wait_linked(timeout=5.0)
    check("both replay hands linked to the hub", True, f"at {sim.time():.2f} s")
    run_until(sim, lambda: rc_link.heartbeat and rc_link.heartbeat["system_status"] == 3, 20.0, step=0.5)
    check("ArduCopter in standby", bool(rc_link.heartbeat) and rc_link.heartbeat["system_status"] == 3,
          f"at {sim.time():.1f} s")

    model, live, steps_since = Expected(), (True, True), []
    for name, left, right, now_live, *extra in STEPS:
        print(f"\n{name}:", flush=True)
        if extra == ["repress"]:
            set_live(sim, now_live, live)
            live = now_live
            send(sim, LEFT, fields(LEFT, throttle=300))
            send(sim, RIGHT, right)
            sim.run_for(0.3)
            model.step(fields(LEFT), right, live)
        mark = sim.mark("hub")
        sent_before = rc_link.overrides_sent
        # Right first, so HOLD is engaged before the throttle moves under it.
        send(sim, RIGHT, right)
        send(sim, LEFT, left)
        set_live(sim, now_live, live)
        live = now_live
        want = model.step(left, right, live)
        keys = ("valid", "reason", "roll", "pitch", "yaw", "throttle")
        took = run_until(sim, lambda: (c := sim.latest_command(mark)) is not None
                         and all(c[k] == want[k] for k in keys), 1.0)
        got = sim.latest_command(mark) or {}
        check("hub command", took is not None,
              f"expected {[want[k] for k in keys]} got {[got.get(k) for k in keys]}")
        steps_since.append(mark)
        if want["valid"]:
            rc = rc_expected(want)
            check("bridge sends the expected channels", rc_link.channels[:4] == rc,
                  f"expected {rc} sent {rc_link.channels[:4]}")
            took = run_until(sim, lambda: rc_link.rc_reported is not None
                             and rc_link.rc_reported[:4] == rc, 0.5)
            check("ArduCopter reports them", took is not None,
                  f"reported {rc_link.rc_reported and rc_link.rc_reported[:4]}")
        else:
            sim.run_for(0.2)
            after = rc_link.overrides_sent
            sim.run_for(0.3)
            check("no override while invalid", rc_link.overrides_sent == after,
                  f"{rc_link.overrides_sent - after} sent")

    rows = sim.commands(steps_since[0])
    jumps = [(a["seq"], k, b[k] - a[k]) for a, b in zip(rows, rows[1:])
             if b["seq"] == a["seq"] + 1 and a["valid"] and b["valid"]
             for k in MAX_STEP if abs(b[k] - a[k]) > MAX_STEP[k]]
    check("slew limits between consecutive commands", not jumps, str(jumps[:3]))
    status = sim.query("hub", "status", "status")
    check("hub rejected no packet", all(sum(h["rejected"].values()) == 0 for h in status["hands"]),
          str([h["rejected"] for h in status["hands"]]))
    panics = [n for n in ("left", "right", "hub") if "Guru Meditation" in sim.console[n].text]
    check("no firmware panic on any ESP32-S3", not panics, str(panics))
    sim.save("s3b_replay.json", {
        "test": "S3-B scripted BLE input -> hub -> ArduCopter",
        "scope": "hand sensing bypassed (apps/replay); ArduCopter 4.7.1 MatekF405-Wing, disarmed",
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    })

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
