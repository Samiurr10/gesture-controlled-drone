#!/usr/bin/env python3
"""Engine stress: SETS controller sets in one simulation, each a scripted LEFT and
RIGHT hand (apps/replay) and a hub on their own BLE medium. Three sets are 9 dual-core
ESP32-S3s, 18 core threads. Prints simulated time each second; a run that stops
printing with the process idle is a stall.

    python3 firmware/probes/drone-flight/stress.py <seconds> <tag>   (env from palmpilot.py env)
    STRESS_SETS=1 (default; more than one BLE medium does not link, see the session notes)
    STRESS_EXTRA=N extra standalone ESP32-S3s (alternating hub / LEFT hand firmware)

At the end every hub must report both its hands linked and delivering packets.
"""
import faulthandler
import os
import signal
import struct
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "firmware/tools"))
from controller import Console                                   # noqa: E402
from harness import build_platform                               # noqa: E402

faulthandler.register(signal.SIGUSR1, all_threads=True)
SECONDS = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
SETS = int(os.environ.get("STRESS_SETS", "1"))
ROOT = Path(__file__).resolve().parents[3]
ELF = {"left": ROOT / "tmp/palmpilot/replay-left/sim.elf",
       "right": ROOT / "tmp/palmpilot/replay-right/sim.elf",
       "hub": ROOT / "tmp/palmpilot/hub/sim.elf"}
LEFT, RIGHT, WAITING, HEALTHY = 0, 1, 2, 4 | 32


def packet(side, session):
    raw = bytearray(59)
    raw[0:5] = bytes([1, 59, side, WAITING, 0])
    struct.pack_into("<HIII", raw, 5, HEALTHY, session, 0, 0)
    struct.pack_into("<I", raw, 55, zlib.crc32(raw[:55]) & 0xFFFFFFFF)
    return raw.hex()


os.environ.setdefault("SIMANTIC_TELEMETRY", "0")
from simantic.engine import load                                 # noqa: E402
load()
from Antmicro.Renode.Core import EmulationManager                # noqa: E402
from System import Action, Byte                                  # noqa: E402
from simantic import Sim                                         # noqa: E402

out = ROOT / "tmp/palmpilot/stress" / str(os.getpid())
platform = Path(os.environ["PALMPILOT_PLATFORM"])
machines, media = {}, []
for s in range(1, SETS + 1):
    names = []
    for role, n in (("left", 1), ("right", 2), ("hub", 3)):
        name = f"{role}{s}"
        mac = f"02:50:5{s}:00:00:{n}0"
        machines[name] = {"repl": str(build_platform(platform, out, name=f"{name}.repl", mac=mac)),
                          "elf": str(ELF[role])}
        names.append(name)
    media.append({"type": "ble", "connect": [f"{n}.radio" for n in names]})
# STRESS_EXTRA: more ESP32-S3s on no medium, alternating hub firmware (scanning) and a LEFT
# hand (advertising). Their radios still run events and their firmware still reads and writes
# radio registers, so each adds two more core threads with the same lock pattern.
for k in range(1, int(os.environ.get("STRESS_EXTRA", "0")) + 1):
    role = "hub" if k % 2 else "left"
    name = f"x{role}{k}"
    machines[name] = {"repl": str(build_platform(platform, out, name=f"{name}.repl", mac=f"02:50:6{k % 10}:00:00:{k:02d}")),
                      "elf": str(ELF[role])}

t0 = time.monotonic()
with Sim(scenario={"machines": machines, "media": media}, machine="hub1", uart="uart0") as sim:
    print(f"STRESS started {SETS} sets, {len(machines)} machines in {time.monotonic() - t0:.1f}s", flush=True)
    emulation = EmulationManager.Instance.CurrentEmulation
    consoles = {}
    for machine in emulation.Machines:
        found, name = emulation.TryGetMachineName(machine, None)
        if found and name.startswith("hub"):
            consoles[name] = Console(name)
            uart = machine["sysbus.uart0"]
            uart.GetType().GetEvent("CharReceived").AddEventHandler(
                uart, Action[Byte](lambda v, c=consoles[name]: c.feed(int(v))))
    sim.run_for(1.0)
    for s in range(1, SETS + 1):
        sim.send_bytes(f"set {packet(LEFT, 0x5100 + s)}\n".encode(), machine=f"left{s}")
        sim.send_bytes(f"set {packet(RIGHT, 0x5200 + s)}\n".encode(), machine=f"right{s}")
    start = time.monotonic()
    while sim.time < SECONDS:
        sim.run_for(1.0)
        print(f"STRESS sim={sim.time:5.1f}s wall={time.monotonic() - start:6.1f}s", flush=True)
    linked = 0
    for s in range(1, SETS + 1):
        hub = f"hub{s}"
        mark = len(consoles[hub].stream)
        sim.send_bytes(b"status\n", machine=hub)
        sim.run_for(0.3)
        rows = [r for r in consoles[hub].records(mark) if r.get("type") == "status"]
        ok = bool(rows) and all(h["ready"] and h["accepted"] > 0 for h in rows[-1]["hands"])
        linked += ok
        print(f"STRESS {hub} both hands linked and delivering: {ok}", flush=True)
        if not ok and os.environ.get("STRESS_DEBUG"):
            print(f"STRESS {hub} status: {rows[-1] if rows else consoles[hub].text[-600:]!r}", flush=True)
    print(f"STRESS done linked={linked}/{SETS}", flush=True)
