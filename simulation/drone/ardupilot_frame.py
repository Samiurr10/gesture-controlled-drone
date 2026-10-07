"""ArduPilot SITL's default multicopter, frame "x", for quad_plant.

A Python port of ArduPilot Copter-4.7.1 libraries/SITL/SIM_Frame.cpp (Frame::init,
Frame::calculate_forces) and SIM_Motor.cpp (Motor::calculate_forces, calc_thrust,
pwm_to_command), with SIM_Frame.h's default Model. ArduPilot is GPLv3, and so is
this file: keep it out of anything distributed under another licence.

Kept as in ArduPilot, quirks included: a motor sits at diagonal_size (not half of
it) from the centre, rotation has no gyroscopic coupling, and rotational air
resistance is gyro * radians(400) / refRotRate.
"""
import math

GRAVITY = 9.80665

# SIM_Frame.h default Model
MASS = 3.0
DIAGONAL = 0.35
REF_SPD, REF_ANGLE = 15.08, 45.0
REF_VOLTAGE, REF_CURRENT, REF_ALT = 12.09, 29.3, 593.0
REF_BAT_RES = 0.01
MAX_VOLTAGE = 4.2 * 3
HOVER_THR_OUT = 0.39
PROP_EXPO = 0.65
REF_ROT_RATE = 120.0
PWM_MIN, PWM_MAX = 1000.0, 2000.0
SPIN_MIN, SPIN_MAX = 0.15, 0.95
SLEW_MAX = 150.0
DISC_AREA = 0.385
MDRAG_COEF = 0.2
# SIM_Frame.cpp quad_x_motors: (angle, yaw factor); CCW = 1, CW = -1 (AP_MotorsMatrix.h)
MOTORS = ((45, 1), (-135, 1), (-45, -1), (135, -1))


def air_density(alt_amsl):
    """ISA troposphere, as AP_Baro::get_air_density_for_alt_amsl below 11 km."""
    temp = 288.15 - 0.0065 * alt_amsl
    return 1.225 * (temp / 288.15) ** 4.2558797


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


class ArduPilotQuadX:
    mass = MASS

    def __init__(self, home_alt=584.0):
        self.home_alt = home_alt
        # Frame::init
        drag_force = MASS * GRAVITY * math.tan(math.radians(REF_ANGLE))
        cos_tilt = math.cos(math.radians(REF_ANGLE))
        airspeed_bf = REF_SPD * cos_tilt
        ref_thrust = MASS * GRAVITY / cos_tilt
        ref_rho = air_density(REF_ALT)
        self.mdrag_coef = MDRAG_COEF
        momentum_drag = cos_tilt * self.mdrag_coef * airspeed_bf * math.sqrt(ref_thrust * ref_rho * DISC_AREA)
        if momentum_drag > drag_force:
            self.mdrag_coef *= drag_force / momentum_drag
            self.area_cd = 0.0
        else:
            self.area_cd = (drag_force - momentum_drag) / (0.5 * ref_rho * REF_SPD ** 2)
        hover_thrust = MASS * GRAVITY
        hover_power = REF_CURRENT * REF_VOLTAGE
        hover_velocity_out = 2 * hover_power / hover_thrust
        effective_disc_area = hover_thrust / (0.5 * ref_rho * hover_velocity_out ** 2)
        self.velocity_max = hover_velocity_out / math.sqrt(HOVER_THR_OUT)
        self.effective_prop_area = effective_disc_area / len(MOTORS)
        self.true_prop_area = DISC_AREA / len(MOTORS)
        self.power_factor = hover_power / hover_thrust
        ixx = MASS * 0.25 * (DIAGONAL * 0.5) ** 2
        self.inertia = (ixx, ixx, MASS * 0.5 * (DIAGONAL * 0.5) ** 2)
        self.positions = [(math.cos(math.radians(a)) * DIAGONAL, math.sin(math.radians(a)) * DIAGONAL, 0.0)
                          for a, _ in MOTORS]
        self.last_command = [0.0] * len(MOTORS)
        self.current = 0.0

    def angular_damping(self, rates):
        return [w * math.radians(400.0) / REF_ROT_RATE for w in rates]

    def forces(self, pulses, vel_air_bf, gyro, altitude, dt):
        """Body force (N) and torque (N m) from the four PWM pulses: Frame::calculate_forces."""
        rho = air_density(self.home_alt + altitude)
        voltage = MAX_VOLTAGE - self.current * REF_BAT_RES
        voltage_scale = voltage / MAX_VOLTAGE
        force, torque, current = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0.0
        thrust_vector = (0.0, 0.0, -1.0)
        mdrag_factor = self.mdrag_coef * math.sqrt(rho * self.true_prop_area)
        for i, ((_, yaw_factor), position, pwm) in enumerate(zip(MOTORS, self.positions, pulses)):
            # pwm_to_command, then the slew limiter
            lo = PWM_MIN + SPIN_MIN * (PWM_MAX - PWM_MIN)
            hi = PWM_MIN + SPIN_MAX * (PWM_MAX - PWM_MIN)
            command = min(max((pwm - lo) / (hi - lo), 0.0), 1.0)
            step = SLEW_MAX * dt
            command = min(max(command, self.last_command[i] - step), self.last_command[i] + step)
            self.last_command[i] = command
            # motor velocity through the air, including rotation about the centre
            spin = _cross(position, gyro)
            motor_vel = [v - s for v, s in zip(vel_air_bf, spin)]
            velocity_in = max(0.0, -motor_vel[2])         # -(motor_vel projected on (0,0,-1)).z
            velocity_out = voltage_scale * self.velocity_max * math.sqrt((1 - PROP_EXPO) * command + PROP_EXPO * command ** 2)
            motor_thrust = 0.5 * rho * self.effective_prop_area * (velocity_out ** 2 - velocity_in ** 2)
            yaw_scale = 0.05 * DIAGONAL * motor_thrust
            rotor_torque = [c * yaw_factor * command * yaw_scale * -1.0 for c in thrust_vector]
            thrust = [c * motor_thrust for c in thrust_vector]
            # momentum drag, every component from the thrust before any is taken off
            root = [math.sqrt(abs(c)) for c in thrust]
            drag = (mdrag_factor * motor_vel[0] * (root[1] + root[2]),
                    mdrag_factor * motor_vel[1] * (root[0] + root[2]),
                    mdrag_factor * motor_vel[2] * (root[0] + root[1] + root[2]))
            thrust = [c - d for c, d in zip(thrust, drag)]
            arm_torque = _cross(position, thrust)
            for k in range(3):
                force[k] += thrust[k]
                torque[k] += arm_torque[k] + rotor_torque[k]
            current += self.power_factor * abs(motor_thrust) / max(voltage, 0.1)
        self.current = current
        # body drag
        for k in range(3):
            force[k] -= math.copysign(self.area_cd * 0.5 * rho * vel_air_bf[k] ** 2, vel_air_bf[k])
        return force, torque
