"""LSM6DS3TR-C accelerometer/gyroscope register fixture (I2C 0x6A).

Implements only what the PalmPilot driver uses: identity, the control
registers it writes, the data-ready status bits and the auto-incrementing
burst read of gyro and accelerometer output. It is a register fixture, not a
sensor model: no ODR timing, filtering, FIFO, interrupts, self-test or
temperature behavior, and output changes the instant the test mutates state.
"""
import imu_state

WHO_AM_I = 0x0F
CTRL1_XL, CTRL2_G, CTRL3_C = 0x10, 0x11, 0x12
STATUS_REG = 0x1E
OUTX_L_G, OUTX_L_XL = 0x22, 0x28


class Slave:
    def __init__(self, ctx):
        self.pointer = 0
        self.control = {CTRL1_XL: 0x00, CTRL2_G: 0x00, CTRL3_C: 0x04}  # IF_INC set

    # The driver writes the register pointer, then either continues with data
    # or issues a repeated start and reads.
    def on_write(self, data):
        if not imu_state.accel_gyro_present or not data:
            return
        self.pointer = data[0]
        for value in data[1:]:
            if self.pointer in self.control:
                self.control[self.pointer] = value
            self.pointer = (self.pointer + 1) & 0xFF

    def on_read(self, count):
        if not imu_state.accel_gyro_present:
            return bytes()          # absent device: no data, driver should fail
        out = bytearray()
        for _ in range(count):
            out.append(self._register(self.pointer))
            self.pointer = (self.pointer + 1) & 0xFF
        return bytes(out)

    def on_finish(self):
        pass

    def _register(self, address):
        if address == WHO_AM_I:
            return imu_state.whoami_accel_gyro & 0xFF
        if address in self.control:
            return self.control[address] & 0xFF
        if address == STATUS_REG:
            # bit0 XLDA (accel ready), bit1 GDA (gyro ready), bit2 TDA
            return 0x03 if imu_state.data_ready else 0x00
        if OUTX_L_G <= address < OUTX_L_G + 6:
            return _byte(imu_state.gyro, address - OUTX_L_G)
        if OUTX_L_XL <= address < OUTX_L_XL + 6:
            return _byte(imu_state.accel, address - OUTX_L_XL)
        return 0x00


def _byte(vector, offset):
    """Little-endian signed 16-bit output registers, X then Y then Z."""
    value = int(vector[offset // 2]) & 0xFFFF
    return value & 0xFF if offset % 2 == 0 else (value >> 8) & 0xFF
