// SPDX-License-Identifier: MIT
#include "motion.h"

#include "board.h"
#include "driver/i2c_master.h"

#define REG_WHO_AM_I 0x0F
#define LSM_CTRL1_XL 0x10
#define LSM_CTRL2_G 0x11
#define LSM_CTRL3_C 0x12
#define LSM_STATUS_REG 0x1E
#define LSM_OUTX_L_G 0x22          // gyro XYZ then accel XYZ, 12 bytes
#define LIS_CTRL_REG1 0x20
#define LIS_CTRL_REG2 0x21
#define LIS_CTRL_REG3 0x22
#define LIS_STATUS_REG 0x27
#define LIS_OUT_X_L 0x28
#define LIS_AUTO_INCREMENT 0x80    // LIS3MDL needs bit 7 for multi-byte reads

// PROVISIONAL. 100 kHz is the documented starting bus speed (C2); the transfer
// timeout must be measured against the real sensor at CTRL-021.
#define MOTION_BUS_HZ 100000
#define MOTION_TIMEOUT_MS 50

static i2c_master_bus_handle_t s_bus;
static i2c_master_dev_handle_t s_accel_gyro;
static i2c_master_dev_handle_t s_mag;
static uint8_t s_accel_gyro_identity;
static uint8_t s_mag_identity;
static bool s_accel_gyro_ready;
static bool s_mag_ready;

static esp_err_t read_registers(i2c_master_dev_handle_t device, uint8_t address,
                                uint8_t *out, size_t length)
{
    return i2c_master_transmit_receive(device, &address, 1, out, length,
                                       MOTION_TIMEOUT_MS);
}

static esp_err_t write_register(i2c_master_dev_handle_t device, uint8_t address,
                                uint8_t value)
{
    const uint8_t payload[2] = {address, value};
    return i2c_master_transmit(device, payload, sizeof(payload), MOTION_TIMEOUT_MS);
}

static void decode(const uint8_t *bytes, int16_t *out)
{
    // Little-endian signed 16-bit, X then Y then Z.
    for (int axis = 0; axis < 3; ++axis) {
        out[axis] = (int16_t)((uint16_t)bytes[axis * 2]
                              | ((uint16_t)bytes[axis * 2 + 1] << 8));
    }
}

esp_err_t motion_init(void)
{
    const i2c_master_bus_config_t bus = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = HAND_I2C_SDA_GPIO,
        .scl_io_num = HAND_I2C_SCL_GPIO,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        // The breakout supplies its own pull-ups; do not add internal ones
        // without reviewing total bus loading (build guide, C2).
        .flags.enable_internal_pullup = false,
    };
    esp_err_t status = i2c_new_master_bus(&bus, &s_bus);
    if (status != ESP_OK) return status;

    i2c_device_config_t device = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = LSM6DS3TRC_ADDRESS,
        .scl_speed_hz = MOTION_BUS_HZ,
    };
    status = i2c_master_bus_add_device(s_bus, &device, &s_accel_gyro);
    if (status != ESP_OK) return status;
    device.device_address = LIS3MDL_ADDRESS;
    status = i2c_master_bus_add_device(s_bus, &device, &s_mag);
    if (status != ESP_OK) return status;

    // Identity first. An address that merely acknowledges is not the sensor we
    // designed for; a successful scan is insufficient (FW-02).
    if (read_registers(s_accel_gyro, REG_WHO_AM_I, &s_accel_gyro_identity, 1) == ESP_OK
        && s_accel_gyro_identity == LSM6DS3TRC_WHO_AM_I_VALUE) {
        // BDU so a burst read cannot mix halves of two samples; IF_INC for the
        // auto-incrementing burst below.
        if (write_register(s_accel_gyro, LSM_CTRL3_C, 0x44) == ESP_OK
            && write_register(s_accel_gyro, LSM_CTRL1_XL, 0x60) == ESP_OK
            && write_register(s_accel_gyro, LSM_CTRL2_G, 0x60) == ESP_OK) {
            s_accel_gyro_ready = true;
        }
    }
    if (read_registers(s_mag, REG_WHO_AM_I, &s_mag_identity, 1) == ESP_OK
        && s_mag_identity == LIS3MDL_WHO_AM_I_VALUE) {
        if (write_register(s_mag, LIS_CTRL_REG1, 0x70) == ESP_OK
            && write_register(s_mag, LIS_CTRL_REG2, 0x00) == ESP_OK
            && write_register(s_mag, LIS_CTRL_REG3, 0x00) == ESP_OK) {
            s_mag_ready = true;
        }
    }
    // A missing sensor is reported through motion_read, not by failing init:
    // the acquisition loop must keep running and mark the fault.
    return ESP_OK;
}

uint8_t motion_accel_gyro_identity(void) { return s_accel_gyro_identity; }
uint8_t motion_mag_identity(void) { return s_mag_identity; }

bool motion_read(struct motion_sample *out)
{
    for (int axis = 0; axis < 3; ++axis) {
        out->accel[axis] = 0;
        out->gyro[axis] = 0;
        out->mag[axis] = 0;
    }
    out->accel_gyro = MOTION_ERR_BUS;
    out->mag_status = MOTION_ERR_BUS;

    if (!s_accel_gyro_ready) {
        out->accel_gyro = MOTION_ERR_IDENTITY;
    } else {
        uint8_t status_register = 0;
        if (read_registers(s_accel_gyro, LSM_STATUS_REG, &status_register, 1) == ESP_OK) {
            if ((status_register & 0x03) != 0x03) {
                out->accel_gyro = MOTION_ERR_NOT_READY;
            } else {
                uint8_t burst[12];
                if (read_registers(s_accel_gyro, LSM_OUTX_L_G, burst, sizeof(burst))
                    == ESP_OK) {
                    decode(burst, out->gyro);
                    decode(burst + 6, out->accel);
                    out->accel_gyro = MOTION_OK;
                }
            }
        }
    }

    if (!s_mag_ready) {
        out->mag_status = MOTION_ERR_IDENTITY;
    } else {
        uint8_t status_register = 0;
        if (read_registers(s_mag, LIS_STATUS_REG | LIS_AUTO_INCREMENT,
                           &status_register, 1) == ESP_OK) {
            if (!(status_register & 0x08)) {
                out->mag_status = MOTION_ERR_NOT_READY;
            } else {
                uint8_t burst[6];
                if (read_registers(s_mag, LIS_OUT_X_L | LIS_AUTO_INCREMENT,
                                   burst, sizeof(burst)) == ESP_OK) {
                    decode(burst, out->mag);
                    out->mag_status = MOTION_OK;
                }
            }
        }
    }
    return out->accel_gyro == MOTION_OK;
}
