# The board's ICM-42688-P, moved by quad_plant: each sample first advances the
# airframe, reading the motor pulses from the flight controller's timers.
import math
import os
import random

import _board_peers
import quad_plant

# ICM-42688-P datasheet noise densities, over the 1 kHz output's ~500 Hz bandwidth.
# PALMPILOT_IMU_NOISE=0 turns it off (the model is otherwise noise-free).
GYRO_NOISE_DPS = 0.0028 * math.sqrt(500)
ACCEL_NOISE_G = 70e-6 * math.sqrt(500)
_noise = random.Random(42) if os.environ.get("PALMPILOT_IMU_NOISE", "1") != "0" else None

_base = _board_peers.load("icm42688")


class Slave(_base.Slave):
    def tick(self):
        bus_read = getattr(self.ctx, "bus_read", None) or quad_plant.BUS_READ
        quad_plant.PLANT.advance(self.ctx.now_us, bus_read)
        self.accel_g = quad_plant.PLANT.accel_g()
        self.gyro_dps = quad_plant.PLANT.gyro_dps()
        if _noise:
            self.accel_g = [a + _noise.gauss(0, ACCEL_NOISE_G) for a in self.accel_g]
            self.gyro_dps = [w + _noise.gauss(0, GYRO_NOISE_DPS) for w in self.gyro_dps]
        before = self.samples, self.records
        super().tick()
        if self.samples > before[0] and self.records == before[1]:
            quad_plant.PLANT.imu_drops += 1           # FIFO full: this sample, or the oldest, is lost
