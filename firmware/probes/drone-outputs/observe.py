#!/usr/bin/env python3
"""What ArduCopter does with the hub's commands: its messages and motor outputs.

    python3 firmware/tools/palmpilot.py system --replay firmware/probes/drone-outputs/observe.py

Scripted hands (apps/replay) drive the real hub and stock ArduCopter 4.7.1. The
script asks ArduCopter for SERVO_OUTPUT_RAW (motor PWM) and ATTITUDE, then
records them disarmed, tries a normal arm, and if ArduCopter refuses, prints
why and force-arms to see the motors follow the sticks. Nothing models the
airframe, so ATTITUDE is what the flight controller's sensors (the board
model's IMU) report, not motion.
"""
import struct
import zlib

from controller import ControllerSim, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

LEFT, RIGHT = 0, 1
WAITING, PERMITTED = 2, 3
VALID, ENABLE, CALIBRATED, MOTION_OK = 1, 2, 4, 32
HEALTHY = CALIBRATED | MOTION_OK
ARMED_FLAG = mavlink.MAV_MODE_FLAG_SAFETY_ARMED
FORCE = 21196                        # ArduPilot's magic number to skip pre-arm checks


def packet(side, state, flags, roll=0, pitch=0, throttle=0):
    raw = bytearray(59)
    raw[0:5] = bytes([1, 59, side, state, 0])
    struct.pack_into("<HIII", raw, 5, flags, 0x0B5E0000 + side, 0, 0)
    struct.pack_into("<3h", raw, 49, roll, pitch, throttle)
    struct.pack_into("<I", raw, 55, zlib.crc32(raw[:55]) & 0xFFFFFFFF)
    return raw.hex()


def hands(sim, throttle=0, roll=0, yaw=0, enable=True):
    left = (PERMITTED, HEALTHY | VALID | ENABLE) if enable else (WAITING, HEALTHY)
    sim.query("right", f"set {packet(RIGHT, WAITING, HEALTHY, roll=roll)}", "set")
    sim.query("left", f"set {packet(LEFT, *left, roll=yaw, throttle=throttle)}", "set")


def command(sim, cmd, *params):
    params = list(params) + [0] * (7 - len(params))
    rc_link.outbox.append(lambda mav: mav.command_long_encode(1, 1, cmd, 0, *params))
    sim.run_for(1.0)


def armed():
    return bool(rc_link.heartbeat and rc_link.heartbeat["base_mode"] & ARMED_FLAG)


def report(label):
    servo = rc_link.latest.get("SERVO_OUTPUT_RAW")
    att = rc_link.latest.get("ATTITUDE")
    motors = [getattr(servo, f"servo{i}_raw") for i in range(1, 5)] if servo else None
    print(f"  {label:<34} armed={int(armed())}  rc_in={rc_link.rc_reported and rc_link.rc_reported[:4]}"
          f"  motors(us)={motors}"
          + (f"  roll={att.roll * 57.3:+.1f} pitch={att.pitch * 57.3:+.1f} deg" if att else ""), flush=True)


def new_text(since):
    for t, severity, text in rc_link.statustext[since:]:
        print(f"    [{t:6.2f} s] ArduCopter: {text}", flush=True)
    return len(rc_link.statustext)


with ControllerSim(drone=True) as sim:
    sim.set_calibrate(False)
    for hand in ("left", "right"):
        sim.wait_for_type(hand, "ready", timeout=3.0)
    hands(sim, enable=False)
    sim.wait_linked(timeout=5.0)
    while not (rc_link.heartbeat and rc_link.heartbeat["system_status"] == 3) and sim.time() < 20:
        sim.run_for(0.5)
    print(f"ArduCopter standby at {sim.time():.1f} s; messages so far:")
    seen = new_text(0)

    for message_id, hz in ((mavlink.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW, 10),
                           (mavlink.MAVLINK_MSG_ID_ATTITUDE, 10),
                           (mavlink.MAVLINK_MSG_ID_SYS_STATUS, 1)):
        command(sim, mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, message_id, 1_000_000 // hz)

    # A freshly flashed ArduCopter has no frame, so it allocates no motors. Set a
    # quad X, as on first setup, and reboot for the frame to take effect.
    for name, value in ((b"FRAME_CLASS", 1), (b"FRAME_TYPE", 1)):
        rc_link.outbox.append(lambda mav, n=name, v=value: mav.param_set_encode(
            1, 1, n, v, mavlink.MAV_PARAM_TYPE_INT8))
    sim.run_for(1.0)
    command(sim, mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 1)
    rc_link.heartbeat = None
    start = sim.time()
    while not (rc_link.heartbeat and rc_link.heartbeat["system_status"] == 3) and sim.time() - start < 20:
        sim.run_for(0.5)
    print(f"\nrebooted with FRAME_CLASS=1 FRAME_TYPE=1, standby again at {sim.time():.1f} s:")
    seen = new_text(seen)
    for message_id, hz in ((mavlink.MAVLINK_MSG_ID_SERVO_OUTPUT_RAW, 10),
                           (mavlink.MAVLINK_MSG_ID_ATTITUDE, 10),
                           (mavlink.MAVLINK_MSG_ID_SYS_STATUS, 1)):
        command(sim, mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, message_id, 1_000_000 // hz)
    params = {k: v for k, v in ((m.param_id, m.param_value) for m in rc_link.params)}
    print(f"    parameters echoed: {params}")

    print("\ndisarmed:")
    hands(sim, enable=False); sim.run_for(0.4)    # release first: the hub latches at boot
    hands(sim, throttle=0); sim.run_for(1.0); report("ENABLE, throttle 0")
    hands(sim, throttle=600); sim.run_for(1.5); report("throttle 60%")
    hands(sim, throttle=0); sim.run_for(1.5); report("throttle back to 0")
    seen = new_text(seen)

    print("\narm (normal checks):")
    command(sim, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    sim.run_for(2.0)
    print(f"    COMMAND_ACK: {rc_link.acks[-1:] }  (0 accepted, 4 failed)")
    seen = new_text(seen)
    report("after arm request")

    if not armed():
        print("\nforce-arm (pre-arm checks skipped, to see the outputs):")
        command(sim, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1, FORCE)
        sim.run_for(2.0)
        print(f"    COMMAND_ACK: {rc_link.acks[-1:]}")
        seen = new_text(seen)
    report("armed, throttle 0")
    hands(sim, throttle=500); sim.run_for(2.0); report("throttle 50%")
    hands(sim, throttle=800); sim.run_for(2.0); report("throttle 80%")
    hands(sim, throttle=500, roll=600); sim.run_for(2.0); report("throttle 50%, roll right")
    hands(sim, throttle=500, yaw=600); sim.run_for(2.0); report("throttle 50%, yaw right")
    hands(sim, throttle=500, enable=False); sim.run_for(3.0); report("ENABLE released (RC failsafe)")
    seen = new_text(seen)

    command(sim, mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, FORCE)
    sim.run_for(1.0)
    report("disarm")
    new_text(seen)
    status = rc_link.latest.get("SYS_STATUS")
    if status:
        print(f"\nSYS_STATUS: battery {status.voltage_battery} mV, load {status.load / 10:.0f}%,"
              f" sensors healthy 0x{status.onboard_control_sensors_health:08x}")
    print(f"message types seen: {sorted(rc_link.latest)}")
