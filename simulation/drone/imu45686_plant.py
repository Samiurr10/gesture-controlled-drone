# The Pixhawk 6X's three ICM-45686, moved by quad_plant. Each sample first advances the
# airframe, reading the motor pulses from the flight controller's timers, then reports
# its motion in this slot's chip axes. SLOT (1, 2 or 3 = SPI1/2/3) is set by the board line.
import math
import os
import random
import struct

import _board_peers
import quad_plant

# ArduPilot's Pixhawk6X hwdef, Holybro 6X-45686: SPI1 ROTATION_YAW_90, SPI2 and SPI3
# ROTATION_ROLL_180. ArduPilot turns chip axes into body axes with that rotation, so a slot
# reports the body vector rotated back: YAW_90 body = (-cy, cx, cz), ROLL_180 body = (cx, -cy, -cz).
CHIP_FROM_BODY = {1: lambda b: (b[1], -b[0], b[2]),
                  2: lambda b: (b[0], -b[1], -b[2]),
                  3: lambda b: (b[0], -b[1], -b[2])}
SLOT = 2

# Noise densities: the ICM-42688-P datasheet's, as for the F405's IMU (not checked against
# an ICM-45686 datasheet), over a ~500 Hz bandwidth. PALMPILOT_IMU_NOISE=0 turns it off.
GYRO_NOISE_DPS = 0.0028 * math.sqrt(500)
ACCEL_NOISE_G = 70e-6 * math.sqrt(500)
_noise = random.Random(42) if os.environ.get("PALMPILOT_IMU_NOISE", "1") != "0" else None

BARO_PERIOD_US = 10_000       # how often the built-in BMP388 is given the plant's pressure
_base = _board_peers.load("icm45686")
G_LSB = _base.G_LSB
DPS_LSB = (1 << 19) / 4000.0  # 20-bit hi-res gyro at 4000 dps full scale
_last_baro_us = [None]


def _split(v):
    """20-bit two's complement -> (int16 high bytes, 4-bit low), as the hi-res FIFO packs it."""
    v = max(-(1 << 19), min((1 << 19) - 1, int(round(v)))) & 0xFFFFF
    return struct.pack('<h', struct.unpack('<h', struct.pack('<H', v >> 4))[0]), v & 0xF


class Slave(_base.Slave):
    def sample(self):
        bus_read = getattr(self.ctx, "bus_read", None) or quad_plant.BUS_READ
        now = self.ctx.now_us
        quad_plant.PLANT.advance(now, bus_read)
        if quad_plant.BARO_SET and (_last_baro_us[0] is None or now - _last_baro_us[0] >= BARO_PERIOD_US):
            _last_baro_us[0] = now
            quad_plant.BARO_SET(quad_plant.PLANT.pressure_pa())
        accel = quad_plant.PLANT.accel_g()
        gyro = quad_plant.PLANT.gyro_dps()
        if _noise:
            accel = [a + _noise.gauss(0, ACCEL_NOISE_G) for a in accel]
            gyro = [w + _noise.gauss(0, GYRO_NOISE_DPS) for w in gyro]
        to_chip = CHIP_FROM_BODY[SLOT]
        self.accel_counts = [a * G_LSB for a in to_chip(accel)]
        self.gyro_counts = [w * DPS_LSB for w in to_chip(gyro)]
        before = len(self.fifo)
        super().sample()
        if len(self.fifo) - before < 20 * self.per_tick:
            quad_plant.PLANT.imu_drops += 1           # FIFO full: stop-on-full drops samples

    def packet(self):
        a = [_split(v) for v in getattr(self, "accel_counts", (0, 0, -G_LSB))]
        g = [_split(v) for v in getattr(self, "gyro_counts", (0, 0, 0))]
        self.ts = (self.ts + self.step_us) & 0xFFFF
        return (bytes([0x78]) + a[0][0] + a[1][0] + a[2][0] + g[0][0] + g[1][0] + g[2][0]
                + struct.pack('<h', 0) + struct.pack('<H', self.ts)
                + bytes([(a[0][1] << 4) | g[0][1], (a[1][1] << 4) | g[1][1], (a[2][1] << 4) | g[2][1]]))
