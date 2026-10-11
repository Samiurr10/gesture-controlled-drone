#!/usr/bin/env python3
"""Runs the ble2link probe: one ESP32-S3 central, two ESP32-S3 peripherals.

    python3 firmware/tools/palmpilot.py sim firmware/probes/ble2link:central \
        firmware/probes/ble2link/run.py

Models come from env.sh; set PALMPILOT_BLE_RADIO_OVERLAY= to run the stock radio.
Prints each board's UART and exits 0 only on the central's RESULT: PASS.
"""
import os
import re
import sys
from pathlib import Path

from harness import accept_repl_files, build_platform

ROOT = Path(__file__).resolve().parents[3]
BUILD = ROOT / "tmp/palmpilot"
MACHINES = {
    "central": ("ble2link-central", "02:b2:00:00:00:30"),
    "p1": ("ble2link-p1", "02:b2:00:00:00:10"),
    "p2": ("ble2link-p2", "02:b2:00:00:00:20"),
}
VIRTUAL_SECONDS = float(os.environ.get("B2L_SECONDS", "24"))

os.environ.setdefault("SIMANTIC_TELEMETRY", "0")
from simantic.engine import load  # noqa: E402
load()
from simantic import Sim  # noqa: E402

out = BUILD / "ble2link-run"
platform = Path(os.environ["PALMPILOT_PLATFORM"])
machines = {
    name: {"mcu": str(build_platform(platform, out, mac=mac, name=f"{name}.repl")),
           "elf": str(BUILD / build / "sim.elf")}
    for name, (build, mac) in MACHINES.items()
}
scenario = {"machines": machines,
            "media": [{"type": "ble", "connect": [f"{n}.radio" for n in machines]}]}

accept_repl_files()
with Sim(scenario=scenario, machine="central", uart="uart0") as sim:
    from Antmicro.Renode.Core import EmulationManager
    from System import Action, Byte
    emulation = EmulationManager.Instance.CurrentEmulation
    consoles = {}
    for machine in emulation.Machines:
        _, name = emulation.TryGetMachineName(machine, None)
        consoles[name] = bytearray()
        uart = machine["sysbus.uart0"]
        uart.GetType().GetEvent("CharReceived").AddEventHandler(
            uart, Action[Byte](lambda b, s=consoles[name]: s.append(int(b))))
    while sim.time < VIRTUAL_SECONDS and b"RESULT:" not in consoles["central"]:
        sim.run_for(1.0)
    elapsed = sim.time

for name in machines:
    lines = consoles[name].decode(errors="replace").splitlines()
    print(f"===== {name}")
    print("\n".join(l for l in lines if "B2L" in l or "RESULT" in l))

result = re.search(r"RESULT: (\w+)", consoles["central"].decode(errors="replace"))
print(f"\nradio model: {'candidate' if os.environ.get('PALMPILOT_BLE_RADIO_OVERLAY') else 'stock'}; "
      f"virtual {elapsed:.1f} s; RESULT: {result.group(1) if result else 'NONE'}")
sys.exit(0 if result and result.group(1) == "PASS" else 1)
