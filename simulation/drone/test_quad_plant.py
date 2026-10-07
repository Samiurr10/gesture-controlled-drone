#!/usr/bin/env python3
"""Physics checks for quad_plant, against closed-form results. No simulator needed.

    python3 simulation/drone/test_quad_plant.py

Limits fixed before the first run:
  free fall with drag      velocity within 0.5% of v(t) = (mg/c)(1 - exp(-ct/m)) after 1 s;
                           accelerometer reads the drag, c v / (m g), within 1e-3 g
  hover                    |net acceleration| < 0.01 m/s^2; accelerometer reads -1 g on body z
  thrust curve             PWM -> thrust inverts ArduPilot's thrust_to_actuator within 1e-9
  motor signs              right motors up -> roll left; front up -> nose up; CCW up -> yaw right
  coordinated tilt         at 30 deg roll and level flight thrust, accelerometer x/y < 1e-6 g
  rate integration         0.5 rad/s for 1 s turns the body 0.5 rad within 1e-4
  ground                   below-weight thrust stays on the ground and reads -1 g; above it lifts
  terminal climb           settles within 1% of (T - mg) / c
  barometer                ISA: 100 m -> 100129 Pa within 2 Pa; pressure falls with height
"""
import math
import sys

import quad_plant as qp

checks, failures = [], []


def check(name, ok, detail=""):
    checks.append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def pulse_for_thrust(thrust_lin):
    """ArduPilot AP_MotorsMulticopter::thrust_to_actuator, then the PWM range."""
    e = qp.EXPO
    actuator = ((e - 1) + math.sqrt((1 - e) ** 2 + 4 * e * thrust_lin)) / (2 * e)
    return 1000 + 1000 * (qp.SPIN_MIN + (qp.SPIN_MAX - qp.SPIN_MIN) * actuator)


def airborne(pulses, altitude=50.0, q=(1.0, 0.0, 0.0, 0.0)):
    p = qp.Plant()
    p.pos = [0.0, 0.0, -altitude]
    p.on_ground = False
    p.q = q
    p.pulses = list(pulses)
    p.thrust = [qp.thrust_n(x) for x in pulses]
    return p


def run(p, seconds, dt=0.001):
    for _ in range(round(seconds / dt)):
        p._step(dt)


print("thrust curve")
worst = max(abs(qp.thrust_n(pulse_for_thrust(t)) / qp.MAX_THRUST_N - t) for t in (0.05, 0.2, 0.35, 0.6, 0.9))
check("PWM -> thrust inverts ArduPilot's thrust_to_actuator", worst < 1e-9, f"worst {worst:.1e}")
check("below MOT_SPIN_MIN there is no thrust", qp.thrust_n(1100) == 0.0)

print("free fall")
p = airborne([1000] * 4)
run(p, 1.0)
c, m = qp.LINEAR_DRAG, qp.MASS_KG
expected = m * qp.GRAVITY / c * (1 - math.exp(-c / m))
check("velocity after 1 s matches the drag solution", abs(p.vel[2] - expected) / expected < 0.005,
      f"{p.vel[2]:.4f} vs {expected:.4f} m/s")
# Falling, an accelerometer measures only the drag (up the body z axis).
drag_g = -c * p.vel[2] / (m * qp.GRAVITY)
check("accelerometer reads the drag, c v / (m g)", abs(p.accel_g()[2] - drag_g) < 1e-3 and abs(p.accel_g()[0]) < 1e-9,
      f"{p.accel_g()[2]:+.4f} vs {drag_g:+.4f} g")

print("hover")
p = airborne([pulse_for_thrust(qp.HOVER_THRUST_LIN)] * 4)
run(p, 2.0)
check("net acceleration ~0 at MOT_THST_HOVER", abs(p.vel[2]) < 0.02, f"vz {p.vel[2]:+.4f} m/s after 2 s")
check("accelerometer reads -1 g on body z", abs(p.accel_g()[2] + 1) < 1e-3, f"{p.accel_g()[2]:+.4f} g")

print("motor signs")
hover = pulse_for_thrust(qp.HOVER_THRUST_LIN)
cases = [("right motors (1, 4) up -> roll left (negative)", [hover + 20, hover, hover, hover + 20], 0, -1),
         ("left motors (2, 3) up -> roll right (positive)", [hover, hover + 20, hover + 20, hover], 0, 1),
         ("front motors (1, 3) up -> nose up (positive pitch)", [hover + 20, hover, hover + 20, hover], 1, 1),
         ("CCW motors (1, 2) up -> yaw right (positive)", [hover + 20, hover + 20, hover, hover], 2, 1)]
for name, pulses, axis, sign in cases:
    p = airborne(pulses)
    run(p, 0.2)
    others = [abs(p.rates[i]) for i in range(3) if i != axis]
    check(name, sign * p.rates[axis] > 0.05 and max(others) < 1e-6,
          f"rates {[round(r, 3) for r in p.rates]} rad/s")

print("coordinated tilt")
tilt = math.radians(30)
q = (math.cos(tilt / 2), math.sin(tilt / 2), 0.0, 0.0)
thrust_lin = qp.HOVER_THRUST_LIN / math.cos(tilt)
p = airborne([pulse_for_thrust(thrust_lin)] * 4, q=q)
p.vel = [0.0, 0.0, 0.0]
run(p, 0.001)
a = p.accel_g()
check("30 deg roll, level-flight thrust: accelerometer only on body z", abs(a[0]) < 1e-6 and abs(a[1]) < 1e-6,
      f"{[round(x, 7) for x in a]} g")
check("and it reads 1/cos(30 deg) g", abs(-a[2] - 1 / math.cos(tilt)) < 2e-3, f"{-a[2]:.4f} g")
check("the drone accelerates right (+E) when rolled right", p.vel[1] > 0, f"vE {p.vel[1]:+.2e} m/s")

print("rate integration")
qp.ANGULAR_DRAG, angular_drag = 0.0, qp.ANGULAR_DRAG    # attitude kinematics alone
p = airborne([1000] * 4)
p.rates = [0.5, 0.0, 0.0]
for _ in range(1000):
    p._step(0.001)
    p.rates = [0.5, 0.0, 0.0]             # hold the rate: kinematics only
check("0.5 rad/s for 1 s turns the body 0.5 rad", abs(math.radians(p.euler_deg()[0]) - 0.5) < 1e-4,
      f"{math.radians(p.euler_deg()[0]):.6f} rad")
qp.ANGULAR_DRAG = angular_drag

print("ground")
p = qp.Plant()
p.pulses = [pulse_for_thrust(0.3)] * 4
run(p, 1.0)
check("thrust below weight stays on the ground", p.on_ground and p.pos[2] == 0.0)
check("and reads -1 g at rest", abs(p.accel_g()[2] + 1) < 1e-9 and abs(p.accel_g()[0]) < 1e-9)
p.pulses = [pulse_for_thrust(0.45)] * 4
run(p, 1.0)
check("thrust above weight lifts off", not p.on_ground and p.pos[2] < -0.1, f"alt {-p.pos[2]:.2f} m")

print("terminal climb")
p = airborne([pulse_for_thrust(0.45)] * 4)
run(p, 30.0)
expected = (4 * 0.45 * qp.MAX_THRUST_N - qp.MASS_KG * qp.GRAVITY) / qp.LINEAR_DRAG
check("climb rate settles at (T - mg) / c", abs(-p.vel[2] - expected) / expected < 0.01,
      f"{-p.vel[2]:.3f} vs {expected:.3f} m/s")

print("barometer")
p = qp.Plant()
p.pos = [0.0, 0.0, -100.0]
check("ISA pressure at 100 m", abs(p.pressure_pa() - 100129.4) < 2, f"{p.pressure_pa():.1f} Pa")
p.pos = [0.0, 0.0, -101.0]
check("pressure falls with height", p.pressure_pa() < 100129.4)

print(f"\n{len(checks) - len(failures)}/{len(checks)} checks passed")
sys.exit(1 if failures else 0)
