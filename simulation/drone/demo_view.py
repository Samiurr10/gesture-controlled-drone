#!/usr/bin/env python3
"""The laptop demo's screen: the ArduCopter SITL drone (sitl_live.Drone) drawn in 3D in a browser.

    tmp/ardupilot-venv/bin/python simulation/drone/demo_view.py            # a virtual pilot moves the hands
    tmp/ardupilot-venv/bin/python simulation/drone/demo_view.py --hub /dev/cu.usbserial-XXXX
    then open http://localhost:8765

Without --hub, a scripted virtual pilot moves two virtual hands through a tour: take-off,
a pirouette, a circuit, a figure eight, strafes, a fast pass, return and landing, then
again. The poses go through a Python stand-in for the hand and hub mapping
(gesture-mapping.md: 3 deg deadband, 30 deg saturation, slew 4.0/s attitude and 1.5/s
throttle), then as hub command lines through rc_link, as a physical hub's would. It is
not the firmware. With --hub the physical hub's lines are used, and the operator types
arm, disarm, althold or quit in the terminal.

Either way the drone moves only from ArduCopter's motor outputs through SITL's physics.
`--record` saves each tour's states for the replay page (tmp/palmpilot/demo-view/).
"""
import argparse
import json
import math
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rc_link                                                        # noqa: E402
from sitl_live import ROOT, Drone, hub, hub_reader, operator, start_sitl  # noqa: E402

VIEW = HERE / "view"
OUT = ROOT / "tmp/palmpilot/demo-view"
WIND = (2.5, 250.0)                # m/s, from degrees: a light breeze, so the drone has to work
TICK = 0.02
OAK = (35.0, 25.0)                 # north, east: the tree the circuit goes round (view.js draws it)
MODES = {0: "STABILIZE", 2: "ALT HOLD", 3: "AUTO", 5: "LOITER", 6: "RTL", 9: "LAND"}

# The hand and hub mapping, gesture-mapping.md (PROPOSED values).
TILT_DB, TILT_SAT = 3.0, 30.0      # degrees
CURL_DB = 0.03
SLEW = {"roll": 4.0, "pitch": 4.0, "yaw": 4.0, "throttle": 1.5}   # full command per second
HAND_LAG_S = 0.18                  # a hand does not jump to a new pose


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def tilt_to_cmd(deg):
    a = abs(deg)
    return 0.0 if a <= TILT_DB else math.copysign(min(1.0, (a - TILT_DB) / (TILT_SAT - TILT_DB)), deg)


def cmd_to_tilt(cmd):
    return 0.0 if abs(cmd) < 1e-3 else math.copysign(TILT_DB + abs(cmd) * (TILT_SAT - TILT_DB), cmd)


def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


class Hands:
    """Two virtual hands and the hub's mapping of them. The pilot says which sticks it
    wants; the hands move there with a lag, and the mapping turns the poses into the
    hub's command."""

    def __init__(self):
        self.left = {"curl": 0.0, "roll": 0.0}      # four-finger curl 0..1, hand roll deg (yaw)
        self.right = {"roll": 0.0, "pitch": 0.0}    # hand roll and pitch deg
        self.target = {"curl": 0.0, "lroll": 0.0, "rroll": 0.0, "rpitch": 0.0}
        self.enable = False
        self.cmd = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0, "throttle": 0.0}

    def want(self, roll=0.0, pitch=0.0, yaw=0.0, throttle=0.5):
        self.target = {"curl": 0.0 if throttle <= 0 else CURL_DB + throttle * (1 - CURL_DB),
                       "lroll": cmd_to_tilt(yaw), "rroll": cmd_to_tilt(roll), "rpitch": cmd_to_tilt(pitch)}

    def step(self, dt):
        k = min(1.0, dt / HAND_LAG_S)
        t = self.target
        self.left["curl"] += (t["curl"] - self.left["curl"]) * k
        self.left["roll"] += (t["lroll"] - self.left["roll"]) * k
        self.right["roll"] += (t["rroll"] - self.right["roll"]) * k
        self.right["pitch"] += (t["rpitch"] - self.right["pitch"]) * k
        curl = self.left["curl"]
        mapped = {"roll": tilt_to_cmd(self.right["roll"]), "pitch": tilt_to_cmd(self.right["pitch"]),
                  "yaw": tilt_to_cmd(self.left["roll"]),
                  "throttle": 0.0 if curl <= CURL_DB else clamp((curl - CURL_DB) / (1 - CURL_DB), 0.0, 1.0)}
        for axis, value in mapped.items():
            step = SLEW[axis] * dt
            self.cmd[axis] += clamp(value - self.cmd[axis], -step, step)

    def line(self):
        c = self.cmd
        return hub(roll=round(c["roll"] * 1000), pitch=round(c["pitch"] * 1000), yaw=round(c["yaw"] * 1000),
                   throttle=round(c["throttle"] * 1000), valid=int(self.enable))


class Pilot:
    """Flies the tour by choosing sticks from the drone's state, as a person would by eye.
    Each manoeuvre is a generator yielding once per tick."""

    def __init__(self, drone, hands):
        self.drone, self.hands = drone, hands
        self.s, self.caption, self.hold_at = {}, "", (0.0, 0.0)

    # -- sticks from the state ---------------------------------------------------------
    def throttle_for(self, alt):
        vz = clamp(0.9 * (alt - self.s.get("alt", 0.0)), -1.5, 2.0)
        if abs(vz) < 0.08:
            return 0.5
        return 0.5 + math.copysign(0.1 + 0.4 * min(1.0, abs(vz) / 2.5), vz)   # THR_DZ, PILOT_SPEED_UP

    def steer(self, vN, vE, alt, heading=None, lean=0.6):
        s = self.s
        aN, aE = 0.7 * (vN - s.get("vN", 0.0)), 0.7 * (vE - s.get("vE", 0.0))
        mag = math.hypot(aN, aE)
        if mag > 4.0:
            aN, aE = aN * 4.0 / mag, aE * 4.0 / mag
        psi = math.radians(s.get("yaw", 0.0))
        fwd = aN * math.cos(psi) + aE * math.sin(psi)
        right = -aN * math.sin(psi) + aE * math.cos(psi)
        to_stick = lambda a: clamp(math.degrees(math.atan2(a, 9.81)) / 30.0, -lean, lean)   # ANGLE_MAX 30
        yaw = 0.0 if heading is None else clamp(wrap(heading - s.get("yaw", 0.0)) / 90.0, -0.6, 0.6)
        self.hands.want(roll=to_stick(right), pitch=to_stick(fwd), yaw=yaw, throttle=self.throttle_for(alt))

    def hold_position(self, alt, heading=None):
        n, e = self.hold_at
        self.steer(0.4 * (n - self.s["N"]), 0.4 * (e - self.s["E"]), alt, heading)

    # -- manoeuvres --------------------------------------------------------------------
    def say(self, caption):
        self.caption = caption
        print(f"  {self.drone.now():6.1f}s  {caption}", flush=True)

    def wait(self, seconds, **sticks):
        end = self.drone.now() + seconds
        while self.drone.now() < end:
            if sticks:
                self.hands.want(**sticks)
            yield

    def hover(self, seconds, alt, heading=None):
        self.hold_at = (self.s["N"], self.s["E"])
        end = self.drone.now() + seconds
        while self.drone.now() < end:
            self.hold_position(alt, heading)
            yield

    def climb(self, alt, limit=30.0):
        self.hold_at = (self.s["N"], self.s["E"])
        end = self.drone.now() + limit
        while abs(alt - self.s["alt"]) > 0.3 and self.drone.now() < end:
            self.hold_position(alt)
            yield

    def turn(self, degrees, alt, stick=0.45):
        self.hold_at = (self.s["N"], self.s["E"])
        turned, last = 0.0, self.s["yaw"]
        while abs(turned) < abs(degrees) - 8:
            n, e = self.hold_at
            self.steer(0.4 * (n - self.s["N"]), 0.4 * (e - self.s["E"]), alt)
            self.hands.target["lroll"] = cmd_to_tilt(math.copysign(stick, degrees))
            yield
            turned += wrap(self.s["yaw"] - last)
            last = self.s["yaw"]

    def fly(self, points, speed, stop=True, face=True, limit=90.0):
        """Through `points` (north, east, alt); stops at the last one if `stop`."""
        end = self.drone.now() + limit
        for i, (n, e, alt) in enumerate(points):
            last = i == len(points) - 1
            while self.drone.now() < end:
                dn, de = n - self.s["N"], e - self.s["E"]
                d = math.hypot(dn, de)
                v = math.hypot(self.s["vN"], self.s["vE"])
                if last and stop and d < 1.0 and v < 0.6:
                    break
                if not (last and stop) and d < 3.0 + 0.4 * speed:
                    break
                cruise = min(speed, math.sqrt(2 * 1.2 * d)) if last and stop else speed
                heading = math.degrees(math.atan2(de, dn)) if face and d > 4.0 else None
                self.steer(cruise * dn / max(d, 1e-6), cruise * de / max(d, 1e-6), alt, heading)
                yield
        self.hold_at = (self.s["N"], self.s["E"])

    def strafe(self, roll, seconds, alt):
        end = self.drone.now() + seconds
        while self.drone.now() < end:
            self.hands.want(roll=roll, pitch=0.0, yaw=0.0, throttle=self.throttle_for(alt))
            yield

    def land(self):
        calm = 0
        while calm < 50:
            self.hands.want(throttle=0.25)
            calm = calm + 1 if self.s["alt"] < 0.12 and abs(self.s["vD"]) < 0.1 else 0
            yield

    def tour(self):
        """One flight, the same every time; the breeze makes each one differ a little."""
        self.say("Pre-flight: left hand open, ENABLE held")
        self.hands.enable = True
        yield from self.wait(2.5, throttle=0)
        self.say("Arming in ALT HOLD (operator)")
        self.drone.arm(True)
        yield from self.wait(3.0, throttle=0)
        self.say("Take-off: left hand curls past half, the drone climbs")
        yield from self.climb(6.0)
        self.say("Hover: left hand held near half curl")
        yield from self.hover(3.0, 6.0)
        self.say("Pirouette: left hand rolled right, a full turn")
        yield from self.turn(360, 6.0)
        self.say("Forward flight: right hand pitched forward")
        yield from self.fly([(35.0, 0.0, 8.0)], 6.0, stop=False)
        self.say("Banked circuit round the oak: right hand tilts, left hand steers")
        cx, ce, r = OAK[0], OAK[1], 18.0                 # clockwise from its west side: right turns
        ring = [(cx + r * math.cos(b), ce + r * math.sin(b), 9.0)
                for b in [math.radians(270 + 30 * k) for k in range(1, 14)]]
        yield from self.fly(ring, 6.5, stop=False)
        self.say("Climb out over the field")
        yield from self.fly([(10.0, 45.0, 16.0)], 5.0, stop=False)
        self.say("Figure eight: both hands working together")
        eight = [(12.0 * math.sin(2 * t), 26.0 * math.sin(t), 11.0)
                 for t in [k * math.pi / 8 for k in range(1, 17)]]
        yield from self.fly(eight, 7.0, stop=False)
        self.say("Stop and hold: hands back to level")
        yield from self.fly([(0.0, 0.0, 9.0)], 5.0, face=False)
        yield from self.hover(2.0, 9.0)
        self.say("Strafe right: right hand rolled 12 deg")
        yield from self.strafe(0.35, 3.5, 9.0)
        self.say("Strafe left")
        yield from self.strafe(-0.35, 3.5, 9.0)
        yield from self.hover(2.0, 9.0)
        self.say("Fast pass: right hand pitched 18 deg, low over the field")
        yield from self.fly([(-45.0, -25.0, 5.0), (-10.0, 30.0, 5.0)], 11.0, stop=False)
        self.say("Return to the pad")
        yield from self.fly([(0.0, 0.0, 5.0)], 5.0)
        yield from self.hover(3.0, 5.0, heading=0.0)
        self.say("Landing: left hand opens to a quarter curl")
        yield from self.land()
        self.say("Touchdown: left hand open, disarm (operator)")
        yield from self.wait(1.5, throttle=0)
        self.drone.arm(False)
        yield from self.wait(2.0, throttle=0)
        self.hands.enable = False
        self.say("ENABLE released")
        yield from self.wait(4.0, throttle=0)


class Screen:
    """Runs the hands or the physical hub at 50 Hz and keeps the newest snapshot for the page."""

    def __init__(self, drone, virtual, record):
        self.drone, self.virtual, self.record = drone, virtual, record
        self.hands = Hands()
        self.pilot = Pilot(drone, self.hands)
        self.snapshot, self.frames, self.tours = "{}", [], 0
        self.boot = []                      # (wall, SITL boot s) for the real-time factor

    def run(self):
        tour, due = None, time.monotonic()
        while self.drone.running:
            s = self.drone.state()
            if self.virtual and "N" in s:
                self.pilot.s = s
                if tour is None:
                    tour = self.pilot.tour()
                try:
                    next(tour)
                except StopIteration:
                    self.save()
                    tour = None
                self.hands.step(TICK)
                rc_link.apply_line(self.hands.line())
            self.publish(s)
            due += TICK
            time.sleep(max(0.0, due - time.monotonic()))

    def publish(self, s):
        if "boot_s" in s:
            self.boot.append((s["t"], s["boot_s"]))
            self.boot = self.boot[-250:]
        rtf = None
        if len(self.boot) > 50 and self.boot[-1][0] > self.boot[0][0]:
            rtf = (self.boot[-1][1] - self.boot[0][1]) / (self.boot[-1][0] - self.boot[0][0])
        ch = rc_link.channels
        frame = {
            "t": s["t"], "source": "virtual" if self.virtual else "hub",
            "pos": [s.get("N", 0), s.get("E", 0), s.get("alt", 0)],
            "vel": [s.get("vN", 0), s.get("vE", 0), s.get("vD", 0)],
            "att": [s.get("roll", 0), s.get("pitch", 0), s.get("yaw", 0)],
            "est": s.get("est"), "motors": s.get("motors"), "rc": s.get("rc"),
            "armed": s.get("armed", False), "mode": MODES.get(s.get("mode"), str(s.get("mode", "-"))),
            "sending": s.get("sending", False),
            "cmd": {"valid": not rc_link.failsafe and not rc_link.expired(),
                    "roll": (ch[0] - 1500) / 500, "pitch": -(ch[1] - 1500) / 500,
                    "throttle": (ch[2] - 1000) / 1000, "yaw": (ch[3] - 1500) / 500},
            "caption": self.pilot.caption if self.virtual else "Physical hub",
            "texts": self.drone.texts[-4:], "rtf": rtf, "wind": WIND,
        }
        if self.virtual:
            frame["hands"] = {"left": dict(self.hands.left), "right": dict(self.hands.right),
                              "enable": self.hands.enable}
        self.snapshot = json.dumps(frame, separators=(",", ":"))
        if self.record and self.virtual and (not self.frames or s["t"] - self.frames[-1]["t"] >= 0.05):
            self.frames.append(json.loads(self.snapshot, parse_float=lambda x: round(float(x), 3)))

    def save(self):
        self.tours += 1
        if self.record and self.frames:
            OUT.mkdir(parents=True, exist_ok=True)
            path = OUT / f"tour-{self.tours}.json"
            path.write_text(json.dumps(self.frames, separators=(",", ":")))
            print(f"  tour {self.tours} saved: {path} ({len(self.frames)} frames)", flush=True)
        self.frames = []


def page():
    head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            '<script>window.PALMPILOT_SOURCE = "live";</script></head><body>')
    return (head + (VIEW / "page.html").read_text() + "</body></html>").encode()


def handler(screen):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(page(), "text/html; charset=utf-8")
            if self.path == "/view.js":
                return self.send((VIEW / "view.js").read_bytes(), "text/javascript; charset=utf-8")
            if self.path == "/state":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                try:
                    while screen.drone.running:
                        self.wfile.write(f"data: {screen.snapshot}\n\n".encode())
                        self.wfile.flush()
                        time.sleep(1 / 30)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            self.send_error(404)

        def send(self, body, kind):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", help="a physical hub's serial port; default: the virtual pilot")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--record", action="store_true", help="save each tour's states for the replay page")
    ap.add_argument("--tours", type=int, default=0, help="stop after this many tours (0: run until Ctrl-C)")
    a = ap.parse_args()

    sitl = start_sitl(f"SIM_WIND_SPD {WIND[0]}\nSIM_WIND_DIR {WIND[1]}\nSIM_WIND_TURB 0.4\n")
    drone = None
    try:
        drone = Drone()
        screen = Screen(drone, virtual=a.hub is None, record=a.record)
        server = ThreadingHTTPServer(("127.0.0.1", a.port), handler(screen))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print(f"view: http://localhost:{a.port}  (waiting for SITL's EKF ...)", flush=True)
        drone.wait_ready()
        print(f"ready after {drone.now():.1f} s", flush=True)
        threading.Thread(target=screen.run, daemon=True).start()
        if a.hub:
            hub_reader(drone, a.hub)
            operator(drone)
        else:
            while not a.tours or screen.tours < a.tours:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if drone:
            drone.close()
        sitl.terminate()


if __name__ == "__main__":
    main()
