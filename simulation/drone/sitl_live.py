#!/usr/bin/env python3
"""The demo drone without the emulated F405: ArduCopter 4.7.1 as native SITL, flown in
real time from hub command lines through the simulation's own bridge (rc_link).

    tmp/ardupilot-venv/bin/python simulation/drone/sitl_live.py scripted
    tmp/ardupilot-venv/bin/python simulation/drone/sitl_live.py serial /dev/cu.usbserial-XXXX

`scripted` flies a fixed list of hub commands against limits set before the first run
and prints PASS or FAIL for each step. `serial` reads a physical hub's UART (115200,
one JSON line per 20 ms); type `arm`, `disarm`, `althold` or `quit` and Enter. `althold`
takes control back after a radio failsafe, which ArduCopter starts 1 s (RC_FS_TIMEOUT)
after the overrides stop.

The airframe is SITL's default quad (--model x: 3 kg, 0.35 m), the one ardupilot_frame.py
ports, so the motion comes from ArduCopter's motor outputs through ArduPilot's physics.
Sensors are SITL's full set (GPS, compass, IMUs, barometer). SITL_SENSORS=board keeps only
the Matek board's (IMU and barometer); without GPS the attitude estimate can stay 2-3 deg off
after a manoeuvre, and a radio failsafe lands instead of returning home. SIM_RC_FAIL 1: no
RC receiver, only the bridge's MAVLink overrides.
"""
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from pymavlink import mavutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import rc_link                                                        # noqa: E402
from sitl_reference import ARDUPILOT, BOARD_SENSORS, OVERRIDES, SITL_BIN  # noqa: E402

WORK = ROOT / "tmp/palmpilot/sitl-live"
TICK = 0.02                       # the bridge's override period, as gcs_peer's
HOME = (-35.363261, 149.165230, 584.0)
RATES_HZ = {"SIM_STATE": 50, "ATTITUDE": 50, "SERVO_OUTPUT_RAW": 50, "RC_CHANNELS": 50}
ALT_HOLD, RTL, LAND = 2, 6, 9
deg = math.degrees


def hub(roll=0, pitch=0, yaw=0, throttle=500, valid=1):
    """A hub command line, as apps/hub prints it."""
    return json.dumps({"type": "command", "roll": roll, "pitch": pitch, "yaw": yaw,
                       "throttle": throttle, "valid": valid}, separators=(",", ":"))


def start_sitl(extra=""):
    """`extra`: more parameter lines, e.g. SITL's wind."""
    WORK.mkdir(parents=True, exist_ok=True)
    board = os.environ.get("SITL_SENSORS", "full") == "board"
    (WORK / "overrides.parm").write_text(OVERRIDES + (BOARD_SENSORS if board else "") + "SIM_RC_FAIL 1\n" + extra)
    defaults = f"{ARDUPILOT}/Tools/autotest/default_params/copter.parm,{WORK}/overrides.parm"
    return subprocess.Popen([str(SITL_BIN), "--model", "x", "--speedup", "1", "-w", "-I0",
                             "--defaults", defaults, "--home", ",".join(map(str, (*HOME, 0)))],
                            cwd=WORK, stdout=open(WORK / "sitl.out", "w"), stderr=subprocess.STDOUT)


class Drone:
    """The MAVLink side. A reader thread keeps the newest message of each type; a sender
    thread does gcs_peer's job in wall time: heartbeat, queued messages, and the overrides
    with the bridge's own 100 ms expiry."""

    def __init__(self):
        for _ in range(100):
            try:
                self.conn = mavutil.mavlink_connection("tcp:127.0.0.1:5760", source_system=255)
                break
            except OSError:
                time.sleep(0.2)
        self.conn.wait_heartbeat(timeout=30)
        self.t0 = time.monotonic()
        self.latest, self.texts = {}, []
        self.sim_t = None                    # SITL's clock for the newest SIM_STATE
        self._pending = False
        self.last_override = None            # wall time of the newest override sent
        self.ground = None                   # SITL altitude before take-off
        self.running = True
        rc_link.reset()
        for name, hz in RATES_HZ.items():
            self.command(mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                         getattr(mavutil.mavlink, f"MAVLINK_MSG_ID_{name}"), 1_000_000 // hz)
        for target in (self._read, self._send):
            threading.Thread(target=target, daemon=True).start()

    def now(self):
        return time.monotonic() - self.t0

    def command(self, cmd, *params):
        params = list(params) + [0] * (7 - len(params))
        rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, cmd, 0, *params))

    def althold(self):
        self.command(mavutil.mavlink.MAV_CMD_DO_SET_MODE, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, ALT_HOLD)

    def arm(self, on=True):
        if on:
            self.althold()
        self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, int(on))

    def _read(self):
        while self.running:
            m = self.conn.recv_match(blocking=True, timeout=0.5)
            if m is None or m.get_srcSystem() != 1 or m.get_type() == "BAD_DATA":
                continue
            kind = m.get_type()
            if kind == "HEARTBEAT" and m.get_srcComponent() != 1:
                continue
            self.latest[kind] = m
            if kind == "SIM_STATE":
                self.ground = m.alt if self.ground is None else self.ground
                self._pending = True
            elif kind == "ATTITUDE" and self._pending:
                # SITL sends SIM_STATE then ATTITUDE in the same loop: the attitude's
                # boot time is when that position was computed.
                self.sim_t, self._pending = m.time_boot_ms / 1000, False
            if kind == "STATUSTEXT":
                self.texts.append((round(self.now(), 2), m.text))
                print(f"      ArduCopter: {m.text}", flush=True)

    def _send(self):
        ticks, due = 0, time.monotonic()
        while self.running:
            ticks += 1
            if ticks % 50 == 1:
                self.conn.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            while rc_link.outbox:
                self.conn.mav.send(rc_link.outbox.pop(0)(self.conn.mav))
            rc_link.ticks_since_command += 1
            if not rc_link.failsafe and not rc_link.expired():
                self.conn.mav.rc_channels_override_send(1, 1, *rc_link.channels, *([0] * 10))
                rc_link.overrides_sent += 1
                self.last_override = self.now()
            due += TICK
            time.sleep(max(0.0, due - time.monotonic()))

    def state(self):
        """Everything the screen can draw, now."""
        row = {"t": round(self.now(), 3)}
        s = self.latest.get("SIM_STATE")
        if s and self.ground is not None:
            north = (s.lat_int / 1e7 - HOME[0]) * 111_320.0
            east = (s.lon_int / 1e7 - HOME[1]) * 111_320.0 * math.cos(math.radians(HOME[0]))
            row["sim_t"] = self.sim_t
            row.update(N=round(north, 3), E=round(east, 3), alt=round(s.alt - self.ground, 3),
                       vN=round(s.vn, 3), vE=round(s.ve, 3), vD=round(s.vd, 3),
                       roll=round(deg(s.roll), 2), pitch=round(deg(s.pitch), 2), yaw=round(deg(s.yaw), 2))
        if a := self.latest.get("ATTITUDE"):
            row["est"] = [round(deg(a.roll), 2), round(deg(a.pitch), 2), round(deg(a.yaw), 2)]
            row["boot_s"] = a.time_boot_ms / 1000
        if o := self.latest.get("SERVO_OUTPUT_RAW"):
            row["motors"] = [o.servo1_raw, o.servo2_raw, o.servo3_raw, o.servo4_raw]
        if rc := self.latest.get("RC_CHANNELS"):
            row["rc"] = [rc.chan1_raw, rc.chan2_raw, rc.chan3_raw, rc.chan4_raw]
        if hb := self.latest.get("HEARTBEAT"):
            row["armed"] = bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            row["mode"] = hb.custom_mode
        row["last_override"] = self.last_override
        row["sending"] = self.last_override is not None and self.now() - self.last_override < 2 * TICK
        row["cmd"] = list(rc_link.channels[:4])
        return row

    def wait_ready(self, limit=60.0):
        need = ["tilt alignment complete"] + ([] if os.environ.get("SITL_SENSORS") == "board" else ["is using GPS"])
        start = self.now()
        while self.now() - start < limit:
            if all(any(n in t for _, t in self.texts) for n in need):
                time.sleep(2.0)
                return
            time.sleep(0.2)
        raise RuntimeError(f"EKF not ready after {limit} s")

    def close(self):
        self.running = False


def show(row, label):
    m = row.get("motors", [0] * 4)
    e = row.get("est", [0, 0, 0])
    print(f"  {row['t']:6.1f}s {label:<24} armed={int(row.get('armed', 0))} mode={row.get('mode', '-'):<2} "
          f"alt={row.get('alt', 0):5.2f} m vz={-row.get('vD', 0):+5.2f} N={row.get('N', 0):+6.2f} E={row.get('E', 0):+6.2f} "
          f"roll={row.get('roll', 0):+5.1f} pitch={row.get('pitch', 0):+5.1f} yaw={row.get('yaw', 0):+6.1f} "
          f"est=({e[0]:+5.1f},{e[1]:+5.1f}) motors={m}", flush=True)


# --- scripted flight ------------------------------------------------------------------
# Limits set before the first run. Angles in degrees over the second half of a step;
# ANGLE_MAX is 30 deg, so a third of full stick asks for about 10 deg.
TILT_THIRD = (6.0, 12.0)
TILT_FULL = (25.0, 31.0)
LEVEL_DEG = 1.5
CLIMB_MPS = (0.5, 1.5)
HOVER_MPS = 0.2
YAW_DPS = (30.0, 150.0)
YAW_STOP_DPS = 5.0
OVERRIDE_STOP_S = 0.15            # bridge expiry is 100 ms, plus one tick
FAILSAFE_S = 4.5                  # RC_OVERRIDE_TIME 3 s, plus margin
LAND_S = 30.0
REALTIME = 0.98                   # SITL seconds per wall second, at least


def second_half(rows):
    return rows[len(rows) // 2:]


def mean(rows, key):
    return sum(r[key] for r in rows) / len(rows)


def rate(rows, key):
    span = rows[-1]["t"] - rows[0]["t"]
    if key == "yaw":                # unwrapped sample by sample: a fast turn passes +-180 within the window
        return sum(math.remainder(b["yaw"] - a["yaw"], 360.0) for a, b in zip(rows, rows[1:])) / span
    return (rows[-1][key] - rows[0][key]) / span


def within(value, bounds):
    return bounds[0] <= value <= bounds[1]


def tilt(roll=None, pitch=None, level=False):
    def check(rows, _):
        h = second_half(rows)
        r, p = mean(h, "roll"), mean(h, "pitch")
        if level:
            return abs(r) < LEVEL_DEG and abs(p) < LEVEL_DEG, f"roll {r:+.2f}, pitch {p:+.2f} (limit +-{LEVEL_DEG})"
        ok = (roll is None or within(roll[0] * r, roll[1])) and (pitch is None or within(pitch[0] * p, pitch[1]))
        return ok, f"roll {r:+.2f}, pitch {p:+.2f}"
    return check


def climb(bounds=None, hover=False):
    def check(rows, _):
        v = rate(second_half(rows), "alt")
        return (abs(v) < HOVER_MPS if hover else within(v, bounds)), f"climb {v:+.2f} m/s"
    return check


def yaw(sign=0):
    def check(rows, _):
        v = rate(second_half(rows), "yaw")
        return (abs(v) < YAW_STOP_DPS if not sign else within(sign * v, YAW_DPS)), f"yaw rate {v:+.1f} deg/s"
    return check


def armed(want):
    def check(rows, _):
        return rows[-1].get("armed") == want and (not want or rows[-1].get("mode") == ALT_HOLD), \
            f"armed={rows[-1].get('armed')} mode={rows[-1].get('mode')}"
    return check


def overrides_stop(rows, start):
    """The last override went out within the expiry of the last hub line (sent just before `start`)."""
    after = rows[-1]["last_override"] - start
    return after <= OVERRIDE_STOP_S, f"last override {after:.3f} s after the last line"


def overrides_resume(rows, start):
    back = next((r["last_override"] for r in rows if r["last_override"] and r["last_override"] > start), None)
    after = None if back is None else back - start
    return after is not None and after <= 2 * TICK, f"first override {after if after is None else round(after, 3)} s after the first line"


def landed(rows):
    return len(rows) > 50 and all(r.get("alt", 1) < 0.15 and abs(r.get("vD", 1)) < 0.1 for r in rows[-50:])


def lands(rows, start):
    t = rows[-1]["t"] - start
    worst = max(max(abs(r.get("roll", 0)), abs(r.get("pitch", 0))) for r in rows)
    return landed(rows) and worst < 10.0, f"on the ground after {t:.1f} s, worst tilt {worst:.1f} deg"


def failsafe(rows, start):
    """Radio failsafe: RTL with a position estimate, LAND without one (FS_THR_ENABLE 1)."""
    expect = LAND if os.environ.get("SITL_SENSORS") == "board" else RTL
    land = next((r["t"] - start for r in rows if r.get("mode") == expect), None)
    disarmed = rows[-1].get("armed") is False
    worst = max(max(abs(r.get("roll", 0)), abs(r.get("pitch", 0))) for r in rows)
    ok = land is not None and land <= FAILSAFE_S and disarmed and worst < 10.0
    return ok, (f"{'LAND' if expect == LAND else 'RTL'} {land if land is None else round(land, 2)} s after release, "
                f"disarmed={disarmed}, worst tilt {worst:.1f} deg")


# (label, seconds, hub line or None for silence, operator action, check, stop early when)
FLIGHT = [
    ("ENABLE held, throttle 0", 2, hub(throttle=0), None, None, None),
    ("arm, AltHold", 3, hub(throttle=0), "arm", armed(True), None),
    ("climb (throttle 750)", 6, hub(throttle=750), None, climb(CLIMB_MPS), None),
    ("hover (throttle 500)", 4, hub(), None, climb(hover=True), None),
    ("roll right 1/3", 3, hub(roll=333), None, tilt(roll=(1, TILT_THIRD)), None),
    ("level", 3, hub(), None, tilt(level=True), None),
    ("roll left 1/3", 3, hub(roll=-333), None, tilt(roll=(-1, TILT_THIRD)), None),
    ("level", 3, hub(), None, tilt(level=True), None),
    ("pitch forward 1/3", 3, hub(pitch=333), None, tilt(pitch=(-1, TILT_THIRD)), None),
    ("level", 3, hub(), None, tilt(level=True), None),
    ("pitch back 1/3", 3, hub(pitch=-333), None, tilt(pitch=(1, TILT_THIRD)), None),
    ("level", 3, hub(), None, tilt(level=True), None),
    ("yaw right 1/2", 4, hub(yaw=500), None, yaw(1), None),
    ("yaw left 1/2", 4, hub(yaw=-500), None, yaw(-1), None),
    ("yaw stop", 2, hub(), None, yaw(0), None),
    ("roll right + pitch forward", 3, hub(roll=333, pitch=333), None, tilt(roll=(1, TILT_THIRD), pitch=(-1, TILT_THIRD)), None),
    ("level", 3, hub(), None, tilt(level=True), None),
    ("full roll right", 2, hub(roll=1000), None, tilt(roll=(1, TILT_FULL)), None),
    ("level", 4, hub(), None, tilt(level=True), None),
    ("hub silent 0.5 s", 0.5, None, None, overrides_stop, None),
    ("hub back", 2, hub(), None, overrides_resume, None),
    ("descend (throttle 250)", LAND_S, hub(throttle=250), None, lands, landed),
    ("on the ground, throttle 0", 2, hub(throttle=0), None, None, None),
    ("disarm", 3, hub(throttle=0), "disarm", armed(False), None),
    ("re-arm for failsafe", 3, hub(throttle=0), "arm", armed(True), None),
    ("climb", 5, hub(throttle=750), None, climb(CLIMB_MPS), None),
    ("hover", 3, hub(), None, climb(hover=True), None),
    ("ENABLE released in flight", 40, hub(valid=0), None, failsafe, lambda rows: rows[-1].get("armed") is False and len(rows) > 50),
]


def response_time(rows, start, key, fraction=0.9):
    """Seconds from the step's first line until `key` covers `fraction` of its change."""
    a, b = rows[0][key], mean(second_half(rows), key)
    for r in rows:
        if abs(r[key] - a) >= fraction * abs(b - a):
            return r["t"] - start
    return None


def echo_time(rows, start, channel, value):
    """Seconds until ArduCopter reports the new stick value on RC_CHANNELS."""
    return next((r["t"] - start for r in rows if r.get("rc") and abs(r["rc"][channel] - value) <= 2), None)


def scripted(drone):
    results, log, latency = [], [], []
    for label, seconds, line, action, check, until in FLIGHT:
        if action == "arm":
            drone.arm(True)
        elif action == "disarm":
            drone.arm(False)
        start, rows, shown = drone.now(), [], 0.0
        while drone.now() - start < seconds:
            if line is not None:
                rc_link.apply_line(line)
            rows.append(drone.state())
            if rows[-1]["t"] - shown >= 1.0:
                show(rows[-1], label)
                shown = rows[-1]["t"]
            if until and until(rows):
                break
            time.sleep(TICK)
        log.append({"step": label, "start": start, "rows": rows})
        if check:
            ok, detail = check(rows, start)
            results.append((label, ok, detail))
            print(f"  -> {'PASS' if ok else 'FAIL'}  {label}: {detail}", flush=True)
        stick = {"roll right 1/3": (0, "roll", 1666), "pitch forward 1/3": (1, "pitch", 1334),
                 "full roll right": (0, "roll", 2000), "level": None}.get(label)
        if stick:
            ch, key, value = stick
            latency.append((label, echo_time(rows, start, ch, value), response_time(rows, start, key)))
    return results, log, latency


def report(drone, sitl, results, log, latency, wall):
    rows = [r for step in log for r in step["rows"] if "boot_s" in r]
    rtf = (rows[-1]["boot_s"] - rows[0]["boot_s"]) / (rows[-1]["t"] - rows[0]["t"])
    cpu = subprocess.run(["ps", "-o", "time=", "-p", str(sitl.pid)], capture_output=True, text=True).stdout.strip()
    minutes, seconds = cpu.split(":")
    cpu_s = int(minutes) * 60 + float(seconds)
    ok = rtf >= REALTIME
    results.append(("real time", ok, f"{rtf:.3f} SITL s per wall s (limit {REALTIME})"))
    print(f"\n{'PASS' if ok else 'FAIL'}  real time: {rtf:.3f} SITL s per wall s; SITL used {cpu_s:.1f} s of CPU in {wall:.1f} s "
          f"({100 * cpu_s / wall:.0f}% of one core)")
    print("\nstick step               ArduCopter sees it   airframe at 90%")
    for label, echo, resp in latency:
        print(f"  {label:<22} {echo if echo is None else f'{echo * 1000:4.0f} ms':>12}   {resp if resp is None else f'{resp:.2f} s':>10}")
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed}/{len(results)} checks passed")
    out = WORK / f"scripted-{os.environ.get('SITL_SENSORS', 'full')}.json"
    out.write_text(json.dumps({"results": results, "latency": latency, "rtf": rtf, "cpu_s": cpu_s, "wall_s": wall,
                               "texts": drone.texts, "steps": log}, indent=None))
    print(f"log: {out}")
    return passed == len(results)


def hub_reader(drone, port):
    """A physical hub's lines into rc_link, on a thread."""
    import serial                                                    # pyserial, only for a physical hub
    link = serial.Serial()
    link.port, link.baudrate, link.timeout = port, 115200, 0.5
    link.dtr = link.rts = False                     # on DevKits these drive EN/IO0: do not reset the hub
    link.open()

    def read():
        while drone.running:
            try:
                raw = link.readline()
            except serial.SerialException as error:
                print(f"hub serial error: {error}", flush=True)
                return
            if raw:
                rc_link.apply_line(raw.decode(errors="replace").strip())
    threading.Thread(target=read, daemon=True).start()


def operator(drone):
    """Operator words on standard input, until `quit`."""
    for text in sys.stdin:
        word = text.strip()
        if word == "arm":
            if rc_link.failsafe or rc_link.expired() or rc_link.channels[2] > 1100:
                print("refused: the hub command must be valid with the throttle low", flush=True)
            else:
                drone.arm(True)
        elif word == "disarm":
            drone.arm(False)
        elif word == "althold":
            drone.althold()
        elif word == "quit":
            break


def serial_hub(drone, port):
    hub_reader(drone, port)

    def show_loop():
        while drone.running:
            c = rc_link
            show(drone.state(), f"hub {'invalid' if c.failsafe else 'stale' if c.expired() else 'valid'}")
            time.sleep(0.5)
    threading.Thread(target=show_loop, daemon=True).start()
    operator(drone)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "scripted"
    sitl = start_sitl()
    drone = None
    try:
        drone = Drone()
        drone.wait_ready()
        print(f"ready after {drone.now():.1f} s", flush=True)
        if mode == "serial":
            serial_hub(drone, sys.argv[2])
            return
        start = time.monotonic()
        results, log, latency = scripted(drone)
        ok = report(drone, sitl, results, log, latency, time.monotonic() - start)
        sys.exit(0 if ok else 1)
    finally:
        if drone:
            drone.close()
        sitl.terminate()


if __name__ == "__main__":
    main()
