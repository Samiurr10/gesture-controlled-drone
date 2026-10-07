# The board's ICM-42688-P, moved by quad_plant: each sample first advances the
# airframe, reading the motor pulses from the flight controller's timers.
import _matek_peers
import quad_plant

_base = _matek_peers.load("icm42688")


class Slave(_base.Slave):
    def tick(self):
        bus_read = getattr(self.ctx, "bus_read", None) or quad_plant.BUS_READ
        quad_plant.PLANT.advance(self.ctx.now_us, bus_read)
        self.accel_g = quad_plant.PLANT.accel_g()
        self.gyro_dps = quad_plant.PLANT.gyro_dps()
        super().tick()
