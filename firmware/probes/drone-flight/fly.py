#!/usr/bin/env python3
"""A gesture flight: both hands -> hub -> ArduCopter (AltHold) -> motors -> quad_plant.

    python3 firmware/tools/palmpilot.py system firmware/probes/drone-flight/fly.py

LEFT and RIGHT run the real hand firmware with simulated flex sensors and IMUs,
the hub links them over BLE, the bridge sends its commands to stock ArduCopter
4.7.1 as RC overrides, and quad_plant flies the airframe from ArduCopter's motor
pulses, feeding the motion back to the flight controller's IMU and barometer.

Bench setup a real first flight would also need, done here over MAVLink by the
host: frame = quad X, arming checks skipped (the board model has no compass and
no accelerometer calibration), AltHold, arm. ENABLE is permission, not arming.
"""
from controller import ControllerSim, quad_plant, rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

EXTENDED_UV, CURLED_UV = 2154000, 1055000
FINGERS = ["index", "middle", "ring", "little"]
SKIP_ALL = 0xFFFFE
ALT_HOLD = 2
TILT = 16384 // 2
PLANT = quad_plant.PLANT


def throttle(sim, milli):
    """Left four-finger curl for a hub throttle of about `milli`."""
    curl = 0.031 + milli / 1000 * 0.938
    sim.set_hand_uv("left", round(EXTENDED_UV - curl * (EXTENDED_UV - CURLED_UV)), fingers=FINGERS)


def mav(fn):
    rc_link.outbox.append(fn)


def command(cmd, *params):
    params = list(params) + [0] * (7 - len(params))
    mav(lambda m: m.command_long_encode(1, 1, cmd, 0, *params))


def standby(sim, limit=25):
    rc_link.heartbeat = None
    start = sim.time()
    while not (rc_link.heartbeat and rc_link.heartbeat["system_status"] in (3, 4)) and sim.time() - start < limit:
        sim.run_for(0.5)


def texts(since):
    for t, _, x in rc_link.statustext[since:]:
        print(f"      ArduCopter: {x}", flush=True)
    return len(rc_link.statustext)


def show(sim, label):
    r, p, y = PLANT.euler_deg()
    c = sim.latest_command() or {}
    armed = bool(rc_link.heartbeat and rc_link.heartbeat["base_mode"] & mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
    print(f"  t={sim.time():5.1f}s {label:<20} hub[r={c.get('roll', 0):+5} p={c.get('pitch', 0):+5} y={c.get('yaw', 0):+5} "
          f"t={c.get('throttle', 0):4}] armed={int(armed)} | alt={-PLANT.pos[2]:5.2f} m "
          f"N={PLANT.pos[0]:+6.2f} E={PLANT.pos[1]:+6.2f} | roll={r:+5.1f} pitch={p:+5.1f} yaw={y:+6.1f} "
          f"| motors={[round(x) for x in PLANT.pulses]}", flush=True)


def phase(sim, label, seconds, setup):
    setup()
    for _ in range(int(seconds)):
        sim.run_for(1.0)
        show(sim, label)


with ControllerSim(drone=True, plant=True) as sim:
    for hand in ("left", "right"):
        sim.set_hand_uv(hand, EXTENDED_UV)
    sim.set_enable(False)
    sim.set_calibrate(False)
    sim.wait_linked(timeout=5.0)
    for hand in ("left", "right"):
        print(f"{hand} calibration:", sim.calibrate(hand, EXTENDED_UV, CURLED_UV)["reason"])
    standby(sim)
    for name, value, kind in ((b"FRAME_CLASS", 1, mavlink.MAV_PARAM_TYPE_INT8), (b"FRAME_TYPE", 1, mavlink.MAV_PARAM_TYPE_INT8),
                              (b"ARMING_SKIPCHK", SKIP_ALL, mavlink.MAV_PARAM_TYPE_INT32),
                              # The bridge holds ch5 at 1500 us; as a mode switch it would force mode slot 3.
                              (b"FLTMODE_CH", 0, mavlink.MAV_PARAM_TYPE_INT8)):
        mav(lambda m, n=name, v=value, k=kind: m.param_set_encode(1, 1, n, v, k))
    sim.run_for(1.0)
    command(mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 1)
    sim.run_for(1.0)
    standby(sim)
    sim.run_for(6.0)                  # EKF alignment
    seen = texts(0)

    print("\nprepare: ENABLE, left hand open (throttle 0), AltHold, arm")
    throttle(sim, 0)
    sim.set_enable(True)
    sim.wait_command(lambda c: c["valid"], timeout=1.0)
    command(mavlink.MAV_CMD_DO_SET_MODE, mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, ALT_HOLD)
    sim.run_for(1.0)
    command(mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    sim.run_for(2.0)
    sim.run_for(1.0)
    print(f"      mode={rc_link.heartbeat and rc_link.heartbeat['custom_mode']} (2 = AltHold) acks={rc_link.acks[-2:]}")
    seen = texts(seen)
    show(sim, f"on the ground, mode {rc_link.heartbeat and rc_link.heartbeat['custom_mode']}")

    print("\nflight:")
    phase(sim, "climb (curl 75%)", 6, lambda: throttle(sim, 750))
    phase(sim, "hover (curl 50%)", 4, lambda: throttle(sim, 500))
    phase(sim, "roll right", 3, lambda: sim.motion("right").set_tilt(roll_component=TILT // 3))
    phase(sim, "level", 2, lambda: sim.motion("right").set_tilt())
    phase(sim, "pitch forward", 3, lambda: sim.motion("right").set_tilt(pitch_component=TILT // 3))
    phase(sim, "level", 2, lambda: sim.motion("right").set_tilt())
    phase(sim, "yaw right", 3, lambda: sim.motion("left").set_tilt(roll_component=TILT // 2))
    phase(sim, "yaw stop", 1, lambda: sim.motion("left").set_tilt())
    seen = texts(seen)
    phase(sim, "descend (curl 25%)", 4, lambda: throttle(sim, 250))
    for _ in range(30):
        if PLANT.on_ground:
            break
        sim.run_for(1.0)
        show(sim, "descend")
    show(sim, "landed" if PLANT.on_ground else "still airborne")
    throttle(sim, 0)
    sim.run_for(2.0)
    command(mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 21196)
    sim.run_for(1.0)
    sim.set_enable(False)
    sim.run_for(1.0)
    show(sim, "disarmed, ENABLE off")
    texts(seen)
    panics = [n for n in ("left", "right", "hub") if "Guru Meditation" in sim.console[n].text]
    print(f"\nfirmware panics: {panics or 'none'}; trajectory samples: {len(PLANT.log)}")
    sim.save("flight_log.json", {
        "scope": "quad_plant PROVISIONAL airframe; ArduCopter 4.7.1 MatekF405-Wing, AltHold; hands simulated",
        "columns": ["t_s", "pos_ned_m", "vel_ned_mps", "roll_deg", "pitch_deg", "yaw_deg", "motor_us"],
        "log": PLANT.log,
        "hub_commands": sim.commands(),
    })
