"""Rotate the resting board at a known rate: does ArduCopter integrate the same angle? And how fast does the IMU sample?"""
import math
from controller import ControllerSim, quad_plant, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

PLANT = quad_plant.PLANT
RATE = [0.0, 0.0, 0.0]


def kinematic(dt):
    PLANT.rates = list(RATE)
    if any(RATE):
        PLANT._integrate([0.0, 0.0, 0.0], dt)
        PLANT.pos[2] = -10.0                 # stay airborne for the integrator
    PLANT.specific_force = quad_plant._unrotate(PLANT.q, (0.0, 0.0, -quad_plant.GRAVITY))


with ControllerSim(drone=True, plant=True) as sim:
    PLANT._step = kinematic
    sim.set_calibrate(False)
    while not (rc_link.heartbeat and rc_link.heartbeat["system_status"] == 3) and sim.time() < 25:
        sim.run_for(0.5)
    rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, 511, 0, mavlink.MAVLINK_MSG_ID_ATTITUDE, 50_000, 0, 0, 0, 0, 0))
    rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, 511, 0, mavlink.MAVLINK_MSG_ID_RAW_IMU, 50_000, 0, 0, 0, 0, 0))
    sim.run_for(6.0)
    n0, t0 = PLANT.samples, sim.time()
    sim.run_for(2.0)
    print(f"SPIN IMU samples per simulated second: {(PLANT.samples - n0) / (sim.time() - t0):.1f}")
    for axis, name in ((2, "yaw"), (1, "pitch"), (0, "roll")):
        start = PLANT.euler_deg()[axis]
        a = rc_link.latest["ATTITUDE"]
        est0 = math.degrees((a.roll, a.pitch, a.yaw)[axis])
        RATE[axis] = math.radians(20.0)
        sim.run_for(1.0)
        RATE[axis] = 0.0
        sim.run_for(0.2)
        a = rc_link.latest["ATTITUDE"]
        est = math.degrees((a.roll, a.pitch, a.yaw)[axis]) - est0
        true = PLANT.euler_deg()[axis] - start
        print(f"SPIN {name}: true turn {true:+.2f} deg, ArduCopter's {est:+.2f} deg, ratio {est / true:.4f}")
        # back to level for the next axis
        RATE[axis] = -math.radians(20.0)
        sim.run_for(1.0)
        RATE[axis] = 0.0
        sim.run_for(1.5)
    print(f"SPIN IMU samples {PLANT.samples}, dropped on a full FIFO: {PLANT.imu_drops}")
    raw = rc_link.latest.get("RAW_IMU")
    print("SPIN RAW_IMU at rest:", raw and (raw.xacc, raw.yacc, raw.zacc, raw.xgyro, raw.ygyro, raw.zgyro))
