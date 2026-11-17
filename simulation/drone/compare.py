#!/usr/bin/env python3
"""Two demo drones side by side, flown by one keyboard.

    tmp/ardupilot-venv/bin/python simulation/drone/demo_view.py --port 8765                # ArduCopter SITL
    tmp/ardupilot-venv/bin/python simulation/drone/demo_view.py --port 8766 --drone f405   # emulated F405
    python3 simulation/drone/compare.py
    then open http://localhost:8767

The page shows each demo_view.py page in a pane (as a follower: it draws and sends nothing)
and owns the keyboard. Each key goes to both servers in the same tick, through the same
/control, /hands, /arm and /althold posts the view's own "Fly it yourself" uses, so both
drones get identical input at the same wall time. Under each pane: the real-time factor
and the measured lag from a stick key press to the drone's reported RC channel changing,
and to its attitude moving 5 degrees on that axis (compare.html says how each is timed).
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).resolve().parent / "view" / "compare.html"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8767)
    ap.add_argument("--left", default="http://localhost:8765", help="left pane's demo_view.py")
    ap.add_argument("--right", default="http://localhost:8766", help="right pane's demo_view.py")
    ap.add_argument("--left-label", default="ArduCopter SITL")
    ap.add_argument("--right-label", default="Emulated STM32F405")
    a = ap.parse_args()
    panes = [{"url": a.left.rstrip("/"), "label": a.left_label}, {"url": a.right.rstrip("/"), "label": a.right_label}]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path.split("?")[0] not in ("/", "/index.html"):
                return self.send_error(404)
            body = PAGE.read_text().replace("/*PANES*/null", json.dumps(panes)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    print(f"compare: http://localhost:{a.port}  ({panes[0]['url']} | {panes[1]['url']})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
