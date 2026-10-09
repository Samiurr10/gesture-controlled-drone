#!/usr/bin/env python3
"""Bench console for a physical board: type commands, see replies, keep a log.

Every line received is printed and appended, with the host time, to a log file,
so a bench run leaves the capture CLAUDE.md section 7 asks for. Runs under the
ESP-IDF python, which has pyserial:

    . firmware/tools/env.sh
    "$IDF_PYTHON_ENV_PATH/bin/python" firmware/tools/bench.py /dev/cu.usbserial-110

    # scripted: send each command in order, keep reading, exit after N seconds
    "$IDF_PYTHON_ENV_PATH/bin/python" firmware/tools/bench.py PORT --send info --send sample --for 3

Lines you type are logged as `> command`. Ctrl-C or Ctrl-D ends the session.
"""
import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--log", type=Path, help="default: tmp/bench/<time>-<port>.log")
    ap.add_argument("--send", action="append", default=[], help="command to send (repeatable)")
    ap.add_argument("--for", dest="seconds", type=float, help="exit after this many seconds")
    args = ap.parse_args()

    log_path = args.log or ROOT / "tmp" / "bench" / f"{datetime.now():%Y%m%d-%H%M%S}-{Path(args.port).name}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", buffering=1)
    port = serial.Serial(args.port, args.baud, timeout=0.1)
    print(f"# {args.port} @ {args.baud}, logging to {log_path}", file=sys.stderr)

    def note(text: str) -> None:
        log.write(f"{datetime.now().isoformat(timespec='milliseconds')} {text}\n")

    def reader() -> None:
        pending = b""
        while True:
            pending += port.read(256)
            *lines, pending = pending.split(b"\n")
            for raw in lines:
                line = raw.decode(errors="replace").rstrip("\r")
                print(line, flush=True)
                note(line)

    def send(command: str) -> None:
        port.write(command.encode() + b"\n")
        note(f"> {command}")

    threading.Thread(target=reader, daemon=True).start()
    for command in args.send:
        send(command)
        time.sleep(0.2)
    try:
        if args.seconds is not None:
            time.sleep(args.seconds)
            return
        for line in sys.stdin:
            send(line.strip())
    except KeyboardInterrupt:
        pass
    finally:
        print(f"# log: {log_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
