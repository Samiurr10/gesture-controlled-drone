// SPDX-License-Identifier: MIT
// External Adafruit #5543 motion module: LSM6DS3TR-C accelerometer/gyroscope
// at 0x6A and LIS3MDL magnetometer at 0x1C, on GPIO8/9 (FW-02).
//
// Magnetic data is acquired and reported but must never reach the command
// path: yaw is gravity-referenced, never magnetic.
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"

#define LSM6DS3TRC_ADDRESS 0x6A
#define LIS3MDL_ADDRESS 0x1C
#define LSM6DS3TRC_WHO_AM_I_VALUE 0x6A
#define LIS3MDL_WHO_AM_I_VALUE 0x3D

// +-2 g full scale: 0.061 mg/LSB, so one g is about 16384 LSB. Used to
// normalise tilt; the exact sensitivity must be confirmed against the selected
// configuration and measured at CTRL-021.
#ifndef MOTION_ACCEL_LSB_PER_G
#define MOTION_ACCEL_LSB_PER_G 16384
#endif

enum motion_status {
    MOTION_OK = 0,
    MOTION_ERR_BUS = 1,         // transaction failed, NACK or timeout
    MOTION_ERR_IDENTITY = 2,    // WHO_AM_I did not match
    MOTION_ERR_NOT_READY = 3,   // status register reports no new data
};

struct motion_sample {
    int16_t accel[3];           // x, y, z in LSB
    int16_t gyro[3];
    int16_t mag[3];
    enum motion_status accel_gyro;
    enum motion_status mag_status;
};

esp_err_t motion_init(void);

// True when the accelerometer and gyroscope were read successfully. The
// magnetometer is reported separately: it is not required for control.
bool motion_read(struct motion_sample *out);

// Identity values observed at init, for diagnostics.
uint8_t motion_accel_gyro_identity(void);
uint8_t motion_mag_identity(void);
