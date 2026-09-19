"""Shared, test-mutable motion state for the two IMU fixtures.

The fixtures run inside the simulator's Python interpreter, which is the same
one the test script runs in, so a test mutates this module directly and the
next I2C transaction observes it. That keeps stimulus generation project-owned
while the data still reaches firmware through the real ESP-IDF I2C driver.

Units are raw sensor LSBs, because that is what the driver actually reads.
Defaults place the hand flat and still: gravity on +Z, no rotation.
"""

# LSM6DS3TR-C at +-2 g full scale: 0.061 mg/LSB, so 1 g is about 16384 LSB.
ACCEL_LSB_PER_G = 16384

accel = [0, 0, ACCEL_LSB_PER_G]   # x, y, z
gyro = [0, 0, 0]
mag = [0, 0, 0]

# Fault injection.
accel_gyro_present = True         # False makes the device NACK
mag_present = True
whoami_accel_gyro = 0x6A          # corrupt these to test identity rejection
whoami_mag = 0x3D
data_ready = True                 # False clears STATUS_REG data-ready bits


def set_tilt(roll_component=0, pitch_component=0, magnitude=ACCEL_LSB_PER_G):
    """Place the gravity vector for a given tilt, in LSB components.

    A positive roll_component puts gravity on +Y; a positive pitch_component
    puts it on +X. Z takes whatever is left so the vector keeps `magnitude`,
    which is what a real accelerometer at rest would report.
    """
    remainder = magnitude * magnitude - roll_component ** 2 - pitch_component ** 2
    z = int(remainder ** 0.5) if remainder > 0 else 0
    accel[0] = pitch_component
    accel[1] = roll_component
    accel[2] = z


def reset():
    accel[:] = [0, 0, ACCEL_LSB_PER_G]
    gyro[:] = [0, 0, 0]
    mag[:] = [0, 0, 0]
    global accel_gyro_present, mag_present, whoami_accel_gyro, whoami_mag, data_ready
    accel_gyro_present = True
    mag_present = True
    whoami_accel_gyro = 0x6A
    whoami_mag = 0x3D
    data_ready = True
