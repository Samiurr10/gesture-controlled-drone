"""LIS3MDL magnetometer register fixture (I2C 0x1C).

Same scope limits as the accelerometer fixture. Magnetic data is read and
reported but must not reach the command path: yaw is gravity-referenced, never
magnetic (docs/controller/gesture-mapping.md).
"""
import imu_state

WHO_AM_I = 0x0F
CTRL_REG1, CTRL_REG5 = 0x20, 0x24
STATUS_REG = 0x27
OUT_X_L = 0x28
AUTO_INCREMENT = 0x80          # LIS3MDL requires bit 7 set for multi-byte reads


class Slave:
    def __init__(self, ctx):
        self.pointer = 0
        self.increment = False
        self.control = {address: 0x00 for address in range(CTRL_REG1, CTRL_REG5 + 1)}

    def on_write(self, data):
        if not imu_state.mag_present or not data:
            return
        self.increment = bool(data[0] & AUTO_INCREMENT)
        self.pointer = data[0] & 0x7F
        for value in data[1:]:
            if self.pointer in self.control:
                self.control[self.pointer] = value
            if self.increment:
                self.pointer = (self.pointer + 1) & 0x7F

    def on_read(self, count):
        if not imu_state.mag_present:
            return bytes()
        out = bytearray()
        for _ in range(count):
            out.append(self._register(self.pointer))
            if self.increment:
                self.pointer = (self.pointer + 1) & 0x7F
        return bytes(out)

    def on_finish(self):
        pass

    def _register(self, address):
        if address == WHO_AM_I:
            return imu_state.whoami_mag & 0xFF
        if address in self.control:
            return self.control[address] & 0xFF
        if address == STATUS_REG:
            return 0x08 if imu_state.data_ready else 0x00   # ZYXDA
        if OUT_X_L <= address < OUT_X_L + 6:
            offset = address - OUT_X_L
            value = int(imu_state.mag[offset // 2]) & 0xFFFF
            return value & 0xFF if offset % 2 == 0 else (value >> 8) & 0xFF
        return 0x00
