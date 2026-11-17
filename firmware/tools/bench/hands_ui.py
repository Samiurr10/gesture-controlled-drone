"""Live 3D view of both PalmPilot hands and the hub, read over each board's USB UART.

Each hand is polled for `sample` (20 Hz) and `motion` (10 Hz); the hub streams its
command lines by itself and is asked for `status` once a second. A port that is
missing is retried every second. Page at http://localhost:8771.
Usage: python hands_ui.py [--left PORT] [--right PORT] [--hub PORT]
"""
import argparse, json, queue, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import serial

ap = argparse.ArgumentParser()
ap.add_argument("--left", default="/dev/cu.usbserial-310")
ap.add_argument("--right", default="/dev/cu.usbserial-1120")
ap.add_argument("--hub", default="/dev/cu.usbserial-1110")
ap.add_argument("--boards", default="left,hub", help="comma list of left,right,hub to read")
args = ap.parse_args()

state = {k: {"serial": "off", "log": []} for k in ("left", "right", "hub")}
queues = {k: queue.Queue() for k in state}
HAND_CMDS = {"cal reset", "cal extended", "cal curled", "cal neutral", "cal finish", "cal save", "reboot"}


def board_loop(name, port):
    polls = ({"sample": 0.05, "motion": 0.1, "profile": 1.0} if name != "hub" else {"status": 1.0, "hands": 0.1})
    st = state[name]
    st["serial"] = "connecting"
    while True:
        try:
            s = serial.Serial()
            s.port, s.baudrate, s.timeout = port, 115200, 0.02
            s.dtr = s.rts = False  # opening must not reset the board
            s.open()
            st["serial"] = "open"
            due = {k: 0.0 for k in polls}
            buf = b""
            while True:
                now = time.time()
                while not queues[name].empty():
                    s.write((queues[name].get() + "\n").encode())
                for cmd, period in polls.items():
                    if now >= due[cmd]:
                        s.write(cmd.encode() + b"\n"); due[cmd] = now + period
                buf += s.read(8192)
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    line = raw.decode(errors="replace").strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = msg.get("type")
                    msg["at"] = time.time()
                    if kind in ("sample", "motion", "status", "command", "hands", "profile", "neutral", "calibration", "storage"):
                        st[kind] = msg
                    if kind == "capture":
                        st["capture_" + msg.get("end", "")] = msg
                    if kind not in ("sample", "motion", "status", "command", "hands", "profile"):
                        st["log"] = (st["log"] + [line])[-8:]
        except (serial.SerialException, OSError) as e:
            st["serial"] = f"not connected ({e.__class__.__name__})"
            time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path == "/state":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    self.wfile.write(f"data: {json.dumps(state)}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError):
                return
        body = Path(__file__).with_name("hands.html").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        side, _, cmd = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode().partition(":")
        ok = side in ("left", "right") and (cmd in HAND_CMDS or cmd.startswith("cal set "))
        if ok:
            queues[side].put(cmd)
        self.send_response(204 if ok else 400)
        self.end_headers()


if __name__ == "__main__":
    for name in args.boards.split(","):
        threading.Thread(target=board_loop, args=(name, getattr(args, name)), daemon=True).start()
    print("hands view on http://localhost:8771")
    ThreadingHTTPServer(("127.0.0.1", 8771), Handler).serve_forever()
