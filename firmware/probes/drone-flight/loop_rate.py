#!/usr/bin/env python3
"""How often the emulated F405 runs ArduCopter's main loop, IMU update and EKF3 update.

    python3 firmware/tools/palmpilot.py system --replay --no-build firmware/probes/drone-flight/loop_rate.py

Counts entries to the ELF's AP_Scheduler::loop, AP_InertialSensor::update and
NavEKF3::UpdateFilter with CPU hooks over simulated time. ArduCopter's
SCHED_LOOP_RATE is 400 Hz; INS update and EKF3 run once per loop.
"""
import subprocess

from controller import ControllerSim, rc_link

ELF = "tmp/drone/matekf405-wing-arducopter.elf"
NAMES = ("AP_Scheduler::loop()", "AP_InertialSensor::update()", "NavEKF3::UpdateFilter()")


def addresses():
    out = subprocess.run(["arm-none-eabi-nm", "-C", ELF], capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1] == "T" and parts[2] in NAMES:
            found[parts[2]] = int(parts[0], 16)
    return found


with ControllerSim(drone=True, plant=True) as sim:
    sim.set_calibrate(False)
    while not (rc_link.heartbeat and rc_link.heartbeat["system_status"] == 3) and sim.time() < 25:
        sim.run_for(0.5)
    sim.run_for(3.0)
    from Antmicro.Renode.Peripherals.CPU import CpuAddressHook, ICPUWithHooks   # the engine is loaded now
    from System import UInt64
    cpu = ICPUWithHooks(sim.drone_machine["sysbus.cpu"])
    counts, hooks = {}, []
    for name, addr in addresses().items():
        counts[name] = 0

        def hit(_cpu, _pc, n=name):
            counts[n] += 1
        hook = CpuAddressHook(hit)
        hooks.append((addr, hook))
        cpu.AddHook(UInt64(addr), hook)

    def measure(label, seconds=2.0):
        before, t0 = dict(counts), sim.time()
        sim.run_for(seconds)
        dt = sim.time() - t0
        rates = {n.split("::")[0]: round((counts[n] - before[n]) / dt, 1) for n in counts}
        print(f"LOOP {label:<14} per simulated second: {rates}", flush=True)

    measure("disarmed")
    rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, 400, 0, 1, 21196, 0, 0, 0, 0, 0))
    sim.run_for(1.0)
    measure("armed, idle")
