#!/usr/bin/env python3
"""Shakedown of quad_plant with scripted hands: motor decode vs SERVO_OUTPUT_RAW, lift-off, roll.

    python3 firmware/tools/palmpilot.py system --replay --no-build firmware/probes/drone-flight/shake.py
"""
import struct
import zlib

from controller import ControllerSim, quad_plant, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

LEFT, RIGHT, WAITING, PERMITTED = 0, 1, 2, 3
VALID, ENABLE, HEALTHY = 1, 2, 4 | 32
PLANT = quad_plant.PLANT


def packet(side, state, flags, roll=0, pitch=0, throttle=0):
    raw = bytearray(59)
    raw[0:5] = bytes([1, 59, side, state, 0])
    struct.pack_into("<HIII", raw, 5, flags, 0x0B5E0000 + side, 0, 0)
    struct.pack_into("<3h", raw, 49, roll, pitch, throttle)
    struct.pack_into("<I", raw, 55, zlib.crc32(raw[:55]) & 0xFFFFFFFF)
    return raw.hex()


def hands(sim, throttle=0, roll=0, pitch=0, yaw=0, enable=True):
    left = (PERMITTED, HEALTHY | VALID | ENABLE) if enable else (WAITING, HEALTHY)
    sim.query("right", f"set {packet(RIGHT, WAITING, HEALTHY, roll=roll, pitch=pitch)}", "set")
    sim.query("left", f"set {packet(LEFT, *left, roll=yaw, throttle=throttle)}", "set")


def mav(fn):
    rc_link.outbox.append(fn)


def texts(since):
    for t, _, x in rc_link.statustext[since:]:
        print(f"    [{t:6.2f}] ArduCopter: {x}", flush=True)
    return len(rc_link.statustext)


def state(label):
    r, p, y = PLANT.euler_deg()
    servo = rc_link.latest.get("SERVO_OUTPUT_RAW")
    reported = [getattr(servo, f"servo{i}_raw") for i in range(1, 5)] if servo else None
    print(f"  {label:<28} alt={-PLANT.pos[2]:6.2f} m  vel=({PLANT.vel[0]:+5.2f},{PLANT.vel[1]:+5.2f},{-PLANT.vel[2]:+5.2f}) m/s"
          f"  roll={r:+6.1f} pitch={p:+6.1f} yaw={y:+6.1f}  pwm={[round(x) for x in PLANT.pulses]} servo_raw={reported}", flush=True)


with ControllerSim(drone=True, plant=True) as sim:
    sim.set_calibrate(False)
    for hand in ("left", "right"):
        sim.wait_for_type(hand, "ready", timeout=3.0)
    hands(sim, enable=False)
    sim.wait_linked(timeout=5.0)
    sim.setup_drone()
    sim.run_for(6.0)                  # EKF alignment
    for msg, hz in ((mavlink.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW, 20), (mavlink.MAVLINK_MSG_ID_RC_CHANNELS, 10)):
        mav(lambda m, i=msg, h=hz: m.command_long_encode(1, 1, mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, i, 1_000_000 // h, 0, 0, 0, 0, 0))
    seen = texts(0)
    hands(sim, enable=False); sim.run_for(0.3)
    hands(sim, throttle=0); sim.run_for(1.0)
    state("ENABLE, throttle 0")
    mav(lambda m: m.command_long_encode(1, 1, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0))
    sim.run_for(2.0)
    print(f"    arm ack {rc_link.acks[-1:]}"); seen = texts(seen)
    state("armed, throttle 0")
    for label, kw, seconds in (("throttle 65%", dict(throttle=650), 3.0), ("throttle 55%", dict(throttle=550), 3.0),
                               ("roll right", dict(throttle=550, roll=300), 2.0), ("level", dict(throttle=550), 2.0),
                               ("throttle 20%", dict(throttle=200), 4.0)):
        hands(sim, **kw)
        for _ in range(int(seconds / 0.5)):
            sim.run_for(0.5)
            state(label)
        seen = texts(seen)
    sim.save("shake_log.json", {"log": PLANT.log})
