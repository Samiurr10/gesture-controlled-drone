#!/usr/bin/env python3
"""Summarise a bench log written by bench.py.

    python3 firmware/tools/bench_summary.py tmp/bench/<log> [--last N]

Hand logs: per flex channel, the min / max / mean / spread of the calibrated
millivolts and raw counts over the `acq` and `sample` records (use `stream N` to
collect them), plus how many samples were not healthy.

Hub logs: the `command` rate on the hub's own clock, the largest step between
consecutive commands on each axis, and every change of `valid` / `reason` with
its hub time, so fault-to-invalid and recovery can be read off directly.
"""
import argparse
import json
from pathlib import Path

FINGERS = ["thumb", "index", "middle", "ring", "little"]
AXES = ["roll", "pitch", "yaw", "throttle"]


def records(path: Path):
    for line in path.read_text(errors="replace").splitlines():
        brace = line.find("{")
        if brace < 0:
            continue
        try:
            yield json.loads(line[brace:])
        except json.JSONDecodeError:
            continue


def hand(samples) -> None:
    print(f"{len(samples)} samples, {sum(not s.get('healthy') for s in samples)} not healthy")
    for i, finger in enumerate(FINGERS):
        mv = [s["mv"][i] for s in samples]
        raw = [s["raw"][i] for s in samples]
        status = sorted({s["status"][i] for s in samples})
        print(f"  {finger:6}  mV min {min(mv):5} max {max(mv):5} mean {sum(mv) / len(mv):7.1f} spread {max(mv) - min(mv):4}"
              f"   raw min {min(raw):4} max {max(raw):4} spread {max(raw) - min(raw):4}   status {status}")


def hub(commands) -> None:
    span = (commands[-1]["t_us"] - commands[0]["t_us"]) / 1e6
    rate = (len(commands) - 1) / span if span > 0 else 0.0
    print(f"{len(commands)} commands over {span:.2f} s on the hub clock: {rate:.1f} per second")
    gaps = [b["seq"] - a["seq"] for a, b in zip(commands, commands[1:])]
    print(f"  sequence gaps other than 1: {sum(g != 1 for g in gaps)}")
    for axis in AXES:
        steps = [abs(b[axis] - a[axis]) for a, b in zip(commands, commands[1:]) if a["valid"] and b["valid"]]
        print(f"  {axis:8} largest step between valid commands: {max(steps, default=0)}")
    print("  valid / reason changes (hub time, s):")
    last = None
    for c in commands:
        state = (c["valid"], c["reason"])
        if state != last:
            print(f"    {c['t_us'] / 1e6:10.3f}  valid={c['valid']}  reason={c['reason']}")
            last = state


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", type=Path)
    ap.add_argument("--last", type=int, help="only the last N records of each kind")
    args = ap.parse_args()
    recs = list(records(args.log))
    samples = [r for r in recs if r.get("type") in ("acq", "sample")
               and isinstance(r.get("mv"), list) and len(r["mv"]) == len(FINGERS)]
    commands = [r for r in recs if r.get("type") == "command"]
    if args.last:
        samples, commands = samples[-args.last:], commands[-args.last:]
    if samples:
        hand(samples)
    if len(commands) > 1:
        hub(commands)
    if not samples and len(commands) < 2:
        print("no acq/sample or command records in this log")


if __name__ == "__main__":
    main()
