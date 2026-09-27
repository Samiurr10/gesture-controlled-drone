#!/usr/bin/env python3
"""Score the interrupt watchdog with production settings against fixed limits.

    python3 firmware/tools/palmpilot.py run firmware/probes/iwdt firmware/probes/iwdt/run.py
"""
import sys

from harness import PalmPilotSim

IDLE_MS = 20000
PANIC_WINDOW_MS = (285, 305)   # 300 ms timeout, last tick-hook feed <= 10 ms before
ESP_RST_INT_WDT = 5
checks, failures = [], []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)
    if not ok:
        failures.append(name)


with PalmPilotSim(timg=True) as sim:
    now_ms = lambda: sim.machine.ElapsedVirtualTime.TimeElapsed.TotalMilliseconds
    sim.wait_for_type("ready", timeout=6.0)
    mark = len(sim.stream)
    sim.send_line(f"idle {IDLE_MS}")
    try:
        done = sim.wait_for_type("idle_done", timeout=IDLE_MS / 1000 + 5, step=0.25, since=mark)
        text = bytes(sim.stream[mark:]).decode(errors="replace")
        check(f"healthy for {IDLE_MS} ms with no IWDT trip", "Interrupt wdt" not in text and "boot" not in text.split("idle_done")[0],
              f"ticks={done['ticks']}")
    except AssertionError as exc:
        text = bytes(sim.stream[mark:]).decode(errors="replace")
        check(f"healthy for {IDLE_MS} ms with no IWDT trip", False, text[-300:])

    mark = len(sim.stream)
    sim.send_line("spin 1000")
    sim.wait_for_type("spin_start", timeout=3.0, step=0.01, since=mark)
    start = now_ms()
    panic_at = None
    while now_ms() - start < 1500:
        sim.run_for(0.001)
        if b"Interrupt wdt timeout" in bytes(sim.stream[mark:]):
            panic_at = now_ms() - start
            break
    text = bytes(sim.stream[mark:]).decode(errors="replace")
    check("interrupts off: IWDT panics", panic_at is not None, text[-200:] if panic_at is None else "")
    if panic_at is not None:
        check("panic arrives at the IWDT timeout", PANIC_WINDOW_MS[0] <= panic_at <= PANIC_WINDOW_MS[1],
              f"{panic_at:.1f} ms after interrupts were disabled")
        check("stalled code never completed", "spin_survived" not in text)
        try:
            boot = sim.wait_for_type("boot", timeout=6.0, step=0.05, since=mark)
            check("chip reboots after the panic", True)
            check("reset reason is INT_WDT", boot["reset_reason"] == ESP_RST_INT_WDT, str(boot))
        except AssertionError:
            check("chip reboots after the panic", False, bytes(sim.stream[mark:]).decode(errors="replace")[-300:])

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
