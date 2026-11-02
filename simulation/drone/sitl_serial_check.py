#!/usr/bin/env python3
"""sitl_live.py serial, fed by a fake hub on a pseudo-terminal, as a physical hub on USB
would feed it: a ready line, an arm refused at high throttle, arm, climb, roll, level,
0.3 s of malformed lines, the hub unplugged for about 2 s (radio failsafe, RTL), the hub
back and `althold`, descent, landing, disarm. Prints the drone's state at the end of
each phase.

    tmp/ardupilot-venv/bin/python simulation/drone/sitl_serial_check.py

A pseudo-terminal is not a USB-UART bridge: DTR/RTS and the bridge's own latency are not
exercised.
"""
import json
import os
import pty
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
master, slave = pty.openpty()
port = os.ttyname(slave)
runner = subprocess.Popen([f"{ROOT}/tmp/ardupilot-venv/bin/python", f"{ROOT}/simulation/drone/sitl_live.py", "serial", port],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
lines, ready = [], threading.Event()


def read():
    for line in runner.stdout:
        lines.append((time.monotonic(), line.rstrip()))
        print(line.rstrip(), flush=True)
        if "ready after" in line:
            ready.set()
threading.Thread(target=read, daemon=True).start()


def hub(roll=0, pitch=0, yaw=0, throttle=500, valid=1):
    return json.dumps({"type": "command", "roll": roll, "pitch": pitch, "yaw": yaw, "throttle": throttle,
                       "valid": valid}, separators=(",", ":"))


current = {"line": '{"type":"boot"}'}
def write():
    while runner.poll() is None:
        if current["line"] is not None:             # None: the hub is unplugged
            os.write(master, (current["line"] + "\n").encode())
        time.sleep(0.02)


ready.wait(120)
threading.Thread(target=write, daemon=True).start()
marks = {}


def phase(name, line, seconds, operator=None):
    current["line"] = line
    time.sleep(0.3)                  # the operator acts on what the hub is already sending
    if operator:
        runner.stdin.write(operator + "\n")
        runner.stdin.flush()
    marks[name] = time.monotonic()
    print(f"### {name}", flush=True)
    time.sleep(seconds)


phase("ready line", '{"type":"ready"}', 1)
phase("throttle high, try to arm", hub(throttle=600), 2, "arm")
phase("throttle low, arm", hub(throttle=0), 3, "arm")
phase("climb", hub(throttle=750), 5)
phase("roll right", hub(roll=333), 3)
phase("level", hub(), 3)
phase("malformed lines 0.3 s", '{"type":"command","roll":', 0)
phase("hover after the glitch", hub(), 3)
phase("hub unplugged 2 s", None, 1.7)
phase("hub back, althold", hub(), 4, "althold")
phase("descend", hub(throttle=250), 10)
phase("disarm", hub(throttle=0), 3, "disarm")
runner.stdin.write("quit\n")
runner.stdin.flush()
runner.wait(30)


def rows(name, nxt):
    start, stop = marks[name], marks.get(nxt, 1e18)
    return [l for t, l in lines if start <= t < stop]


num = lambda key, l: float(re.search(rf"{key}=\s*([+-]?[\d.]+)", l).group(1))
names = list(marks)
for i, name in enumerate(names):
    part = [l for l in rows(name, names[i + 1] if i + 1 < len(names) else None) if " alt=" in l]
    if part:
        last = part[-1]
        print(f"{name:<28} last: alt={num('alt', last):.2f} roll={num('roll', last):+.1f} armed={num('armed', last):.0f} "
              f"| {last.split('s ', 1)[1][:16]}")
print("refusal seen:", any("refused" in l for _, l in lines))
