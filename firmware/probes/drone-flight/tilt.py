"""Static tilt on the bench (python3 firmware/tools/palmpilot.py system --replay --no-build firmware/probes/drone-flight/tilt.py): does ArduCopter read the board's roll and pitch with the right sign?"""
import math
from controller import ControllerSim, quad_plant, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

PLANT = quad_plant.PLANT
ROLL, PITCH = 10.0, 5.0


def hold(dt):
    # Resting tilted on a wedge: no motion, the accelerometer feels gravity's reaction only.
    PLANT.rates = [0.0, 0.0, 0.0]
    PLANT.specific_force = quad_plant._unrotate(PLANT.q, (0.0, 0.0, -quad_plant.GRAVITY))


r, p = math.radians(ROLL) / 2, math.radians(PITCH) / 2
PLANT._step = hold
with ControllerSim(drone=True, plant=True) as sim:
    PLANT._step = hold
    PLANT.q = quad_plant._mul((math.cos(r), math.sin(r), 0, 0), (math.cos(p), 0, math.sin(p), 0))
    PLANT.q = quad_plant._mul((math.cos(0), 0, 0, 0), PLANT.q)
    w, x, y, z = PLANT.q
    PLANT.q = (w, x, y, z)
    sim.set_calibrate(False)
    while not (rc_link.heartbeat and rc_link.heartbeat["system_status"] == 3) and sim.time() < 25:
        sim.run_for(0.5)
    rc_link.outbox.append(lambda m: m.command_long_encode(1, 1, 511, 0, mavlink.MAVLINK_MSG_ID_ATTITUDE, 100_000, 0, 0, 0, 0, 0))
    sim.run_for(8.0)
    a = rc_link.latest.get("ATTITUDE")
    print(f"TILT true roll={PLANT.euler_deg()[0]:+.2f} pitch={PLANT.euler_deg()[1]:+.2f}  "
          f"ArduCopter roll={math.degrees(a.roll):+.2f} pitch={math.degrees(a.pitch):+.2f}" if a else "no ATTITUDE")
