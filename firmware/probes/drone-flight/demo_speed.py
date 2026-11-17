#!/usr/bin/env python3
"""How far behind real time the laptop demo's drone would be: the flight controller and
quad_plant alone, as in the demo, where the hands and hub are physical.

    PALMPILOT_DRONE=f405 python3 firmware/tools/palmpilot.py drone firmware/probes/drone-flight/demo_speed.py

Hub command lines go through controller.bridge_hub_line every 20 ms of virtual time, as a
physical hub's serial lines would, and the simulation runs in 20 ms slices, as the demo
runner would between screen updates. Prints wall time per simulated second for each phase
and the virtual time the airframe takes to answer each stick step.
"""
import json
import time

from controller import ControllerSim, bridge_hub_line, quad_plant, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

SLICE = 0.02
ALT_HOLD = 2
PLANT = quad_plant.PLANT
rows = []                           # (phase, wall_s, sim_t, roll, pitch, yaw, alt, vz)


def hub(roll=0, pitch=0, yaw=0, throttle=0):
    return json.dumps({"type": "command", "roll": roll, "pitch": pitch, "yaw": yaw,
                       "throttle": throttle, "valid": 1}, separators=(",", ":"))


def command(cmd, *params):
    params = list(params) + [0] * (7 - len(params))
    rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, cmd, 0, *params))


def phase(sim, name, seconds, line):
    for _ in range(round(seconds / SLICE)):
        bridge_hub_line(line)
        start = time.perf_counter()
        sim.run_for(SLICE)
        r, p, y = PLANT.euler_deg()
        rows.append((name, time.perf_counter() - start, sim.time(), r, p, y, -PLANT.pos[2], -PLANT.vel[2]))


def response(name, column, fraction=0.9):
    """Virtual seconds from the phase's first slice until `column` first covers `fraction`
    of its change over the phase."""
    part = [r for r in rows if r[0] == name]
    start, end = part[0][column], part[-1][column]
    for r in part:
        if abs(r[column] - start) >= fraction * abs(end - start):
            return r[2] - part[0][2] + SLICE, end - start
    return None, end - start


def main():
    with ControllerSim(drone=True, plant=True, hands=False) as sim:
        t0 = time.perf_counter()
        sim.setup_drone()
        sim.run_for(6.0)                                   # EKF alignment
        boot_wall, boot_sim = time.perf_counter() - t0, sim.time()
        print(f"boot, parameters, reboot, alignment: {boot_sim:.1f} s simulated in {boot_wall:.1f} s", flush=True)

        phase(sim, "standby", 3, hub())
        command(mavlink.MAV_CMD_DO_SET_MODE, mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, ALT_HOLD)
        phase(sim, "mode", 1, hub())
        command(mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        phase(sim, "armed, first second", 1, hub())
        phase(sim, "armed, on the ground", 2, hub())
        phase(sim, "climb", 6, hub(throttle=750))
        phase(sim, "hover", 4, hub(throttle=500))
        phase(sim, "roll right", 3, hub(roll=333, throttle=500))
        phase(sim, "level after roll", 2, hub(throttle=500))
        phase(sim, "pitch forward", 3, hub(pitch=333, throttle=500))
        phase(sim, "level after pitch", 2, hub(throttle=500))
        phase(sim, "yaw right", 3, hub(yaw=500, throttle=500))
        phase(sim, "descend", 6, hub(throttle=250))
        armed = bool(rc_link.heartbeat and rc_link.heartbeat["base_mode"] & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        print(f"armed={armed} mode={rc_link.heartbeat and rc_link.heartbeat['custom_mode']} "
              f"max alt={max(r[6] for r in rows):.1f} m", flush=True)

        print("\nphase                  sim s  wall s  wall/sim  worst slice (ms wall per 20 ms)")
        names = list(dict.fromkeys(r[0] for r in rows))
        for name in names:
            part = [r for r in rows if r[0] == name]
            wall = sum(r[1] for r in part)
            print(f"{name:<22} {len(part) * SLICE:5.1f} {wall:7.1f}  {wall / (len(part) * SLICE):7.2f}  "
                  f"{max(r[1] for r in part) * 1000:7.0f}")
        flight = [r for r in rows if r[0] not in ("standby", "mode", "armed, first second", "armed, on the ground")]
        ratio = sum(r[1] for r in flight) / (len(flight) * SLICE)
        print(f"in flight overall: {ratio:.2f} s wall per simulated s")

        print("\nstick step -> airframe            90% at (sim s)  change     on screen at that ratio (s)")
        for name, column, unit in (("climb", 7, "m/s climb"), ("roll right", 3, "deg roll"),
                                   ("pitch forward", 4, "deg pitch"), ("level after roll", 3, "deg roll")):
            t, change = response(name, column)
            shown = f"{t * ratio:.2f}" if t is not None else "-"
            print(f"{name:<22} {unit:<10} {t if t is not None else float('nan'):10.2f}   {change:+7.2f}   {shown}")


if __name__ == "__main__":
    main()
