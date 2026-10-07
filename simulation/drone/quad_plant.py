"""Rigid-body quad X driven by ArduCopter's motor outputs (D2, PROVISIONAL airframe).

One PLANT lives for the whole simulation. imu_plant.py advances it on every
IMU sample (1 kHz) and reports its motion; baro_plant.py reports its altitude
as pressure. Motor pulses are read from the flight controller's own timer
registers, so the loop closes through ArduCopter's PWM outputs and nothing else.

Frames: world NED (z down), body FRD (x forward, y right, z down).
Motors, ArduCopter quad X: 1 front-right CCW, 2 back-left CCW, 3 front-left CW,
4 back-right CW. Thrust follows ArduPilot's own model (MOT_THST_EXPO, MOT_SPIN_MIN,
MOT_SPIN_MAX at defaults), so ArduCopter's hover estimate (MOT_THST_HOVER 0.35)
matches this airframe. The airframe numbers are a typical 1 kg 5-inch-class quad,
not a measured vehicle.
"""
import math
import os

GRAVITY = 9.80665
MASS_KG = 1.0
ARM_M = 0.17                          # motor distance from the centre
INERTIA = (0.008, 0.008, 0.015)       # kg m^2, body x y z
HOVER_THRUST_LIN = 0.35               # ArduCopter's MOT_THST_HOVER default
MAX_THRUST_N = MASS_KG * GRAVITY / (4 * HOVER_THRUST_LIN)
EXPO, SPIN_MIN, SPIN_MAX = 0.65, 0.15, 0.95
YAW_TORQUE_PER_N = 0.016              # rotor drag torque / thrust, m
MOTOR_TIME_CONSTANT_S = 0.02
LINEAR_DRAG = 0.25                    # N per m/s
ANGULAR_DRAG = 0.002                  # N m per rad/s
SEA_LEVEL_PA = 101325.0

R = ARM_M / math.sqrt(2)
# (x, y, yaw sign) per motor; CCW props push the body clockwise seen from above (+yaw).
MOTORS = ((R, R, 1), (-R, -R, 1), (R, -R, -1), (-R, R, -1))

# Matek F405-Wing hwdef: PWM1 PB7 TIM4_CH2, PWM2 PB6 TIM4_CH1, PWM3 PB0 TIM3_CH3, PWM4 PB1 TIM3_CH4.
TIM3, TIM4 = 0x40000400, 0x40000800
PSC, CCR1 = 0x28, 0x34
MOTOR_CHANNELS = ((TIM4, 2), (TIM4, 1), (TIM3, 3), (TIM3, 4))
TIMER_CLOCK_HZ = 84_000_000           # APB1 timers: 168 MHz SYSCLK, APB1 /4, x2
BUS_READ = None                       # set by the harness when a peer ctx has no bus_read


def _mul(q, r):
    w1, x1, y1, z1 = q
    w2, x2, y2, z2 = r
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def _rotate(q, v):
    """Body vector -> world."""
    w, x, y, z = _mul(_mul(q, (0.0, *v)), (q[0], -q[1], -q[2], -q[3]))
    return (x, y, z)


def _unrotate(q, v):
    """World vector -> body."""
    return _rotate((q[0], -q[1], -q[2], -q[3]), v)


def thrust_n(pulse_us):
    """ArduPilot's thrust curve, inverted: PWM -> actuator -> thrust."""
    actuator = ((pulse_us - 1000.0) / 1000.0 - SPIN_MIN) / (SPIN_MAX - SPIN_MIN)
    actuator = min(max(actuator, 0.0), 1.0)
    return MAX_THRUST_N * ((1 - EXPO) * actuator + EXPO * actuator * actuator)


class Plant:
    def __init__(self, airframe=None):
        self.airframe = airframe      # None: the 1 kg quad above; else e.g. ArduPilotQuadX
        self.reset()

    def reset(self):
        self.pos = [0.0, 0.0, 0.0]
        self.vel = [0.0, 0.0, 0.0]
        self.q = (1.0, 0.0, 0.0, 0.0)
        self.rates = [0.0, 0.0, 0.0]
        self.thrust = [0.0] * 4
        self.pulses = [0.0] * 4
        self.specific_force = (0.0, 0.0, -GRAVITY)
        self.on_ground = True
        self.last_us = None
        self.samples = 0
        self.imu_drops = 0            # samples the IMU FIFO had no room for
        self.log = []                 # (t_s, pos, vel, roll, pitch, yaw, pulses)

    def read_motors(self, bus_read):
        for i, (base, ch) in enumerate(MOTOR_CHANNELS):
            psc = bus_read(base + PSC, 4)
            ccr = bus_read(base + CCR1 + 4 * (ch - 1), 4)
            self.pulses[i] = ccr * (psc + 1) / TIMER_CLOCK_HZ * 1e6

    def advance(self, now_us, bus_read):
        if self.last_us is None:
            self.last_us = now_us
            return
        dt = (now_us - self.last_us) / 1e6
        self.last_us = now_us
        if dt <= 0:
            return
        self.read_motors(bus_read)
        steps = max(1, math.ceil(dt / 0.001))
        for _ in range(steps):
            self._step(dt / steps)
        self.samples += 1
        if self.samples % 50 == 0:    # 20 Hz at the IMU's 1 kHz
            self.log.append((now_us / 1e6, tuple(self.pos), tuple(self.vel), *self.euler_deg(),
                             tuple(round(p) for p in self.pulses)))

    def _step(self, dt):
        if self.airframe:
            return self._step_airframe(dt)
        alpha = dt / (MOTOR_TIME_CONSTANT_S + dt)
        for i in range(4):
            self.thrust[i] += alpha * (thrust_n(self.pulses[i]) - self.thrust[i])
        total = sum(self.thrust)
        torque = [0.0, 0.0, 0.0]
        for (x, y, spin), t in zip(MOTORS, self.thrust):
            torque[0] += -y * t
            torque[1] += x * t
            torque[2] += spin * YAW_TORQUE_PER_N * t
        force_world = _rotate(self.q, (0.0, 0.0, -total))
        drag = [-LINEAR_DRAG * v for v in self.vel]
        accel = [(f + d) / MASS_KG for f, d in zip(force_world, drag)]
        accel[2] += GRAVITY

        if self.on_ground and accel[2] >= 0:      # resting: the ground carries the rest
            accel = [0.0, 0.0, 0.0]
            self.vel = [0.0, 0.0, 0.0]
            self.rates = [0.0, 0.0, 0.0]
            yaw = self.euler_deg()[2]
            self.q = (math.cos(math.radians(yaw) / 2), 0.0, 0.0, math.sin(math.radians(yaw) / 2))
        else:
            self.on_ground = False
            for i in range(3):
                j, k = (i + 1) % 3, (i + 2) % 3
                gyro_torque = (INERTIA[j] - INERTIA[k]) * self.rates[j] * self.rates[k]
                self.rates[i] += dt * (torque[i] - ANGULAR_DRAG * self.rates[i] + gyro_torque) / INERTIA[i]
            p, q_, r = self.rates
            dq = _mul(self.q, (0.0, p, q_, r))
            q = tuple(a + 0.5 * dt * b for a, b in zip(self.q, dq))
            n = math.sqrt(sum(c * c for c in q))
            self.q = tuple(c / n for c in q)
            for i in range(3):
                self.vel[i] += accel[i] * dt
                self.pos[i] += self.vel[i] * dt
            if self.pos[2] >= 0.0:               # touched down
                self.pos[2] = 0.0
                self.on_ground = True
        self.specific_force = _unrotate(self.q, (accel[0], accel[1], accel[2] - GRAVITY))

    def _step_airframe(self, dt):
        frame = self.airframe
        vel_body = _unrotate(self.q, self.vel)
        force_body, torque = frame.forces(self.pulses, vel_body, tuple(self.rates), -self.pos[2], dt)
        force_world = _rotate(self.q, force_body)
        accel = [f / frame.mass for f in force_world]
        accel[2] += GRAVITY
        if self.on_ground and accel[2] >= 0:
            self._rest()
            accel = [0.0, 0.0, 0.0]
        else:
            self.on_ground = False
            damping = frame.angular_damping(self.rates)
            for i in range(3):
                self.rates[i] += dt * (torque[i] / frame.inertia[i] - damping[i])
            self._integrate(accel, dt)
        self.specific_force = _unrotate(self.q, (accel[0], accel[1], accel[2] - GRAVITY))

    def _rest(self):
        self.vel = [0.0, 0.0, 0.0]
        self.rates = [0.0, 0.0, 0.0]
        yaw = self.euler_deg()[2]
        self.q = (math.cos(math.radians(yaw) / 2), 0.0, 0.0, math.sin(math.radians(yaw) / 2))

    def _integrate(self, accel, dt):
        p, q_, r = self.rates
        dq = _mul(self.q, (0.0, p, q_, r))
        q = tuple(a + 0.5 * dt * b for a, b in zip(self.q, dq))
        n = math.sqrt(sum(c * c for c in q))
        self.q = tuple(c / n for c in q)
        for i in range(3):
            self.vel[i] += accel[i] * dt
            self.pos[i] += self.vel[i] * dt
        if self.pos[2] >= 0.0:                   # touched down
            self.pos[2] = 0.0
            self.on_ground = True

    # ---- sensor views ---------------------------------------------------------
    def accel_g(self):
        return [a / GRAVITY for a in self.specific_force]

    def gyro_dps(self):
        return [math.degrees(w) for w in self.rates]

    def pressure_pa(self):
        altitude = -self.pos[2]
        return SEA_LEVEL_PA * (1 - 2.25577e-5 * altitude) ** 5.25588

    def euler_deg(self):
        w, x, y, z = self.q
        roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
        pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
        yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
        return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def _airframe():
    if os.environ.get("PALMPILOT_AIRFRAME") == "ardupilot":
        import ardupilot_frame
        return ardupilot_frame.ArduPilotQuadX()
    return None


PLANT = Plant(_airframe())
