// SPDX-License-Identifier: MIT
// Frozen bench pin map - docs/controller/build-guide.md, CLAUDE.md section 2.
// Header position numbers are not GPIO numbers. Do not translate Feather labels.
#pragma once

#include <stdint.h>

#define HAND_FLEX_COUNT 5

// Finger order is fixed and shared with the host tooling. ADC1 channel n is
// GPIO n+1 on ESP32-S3; GPIO3 is skipped because it is a strapping pin.
enum hand_finger {
    FINGER_THUMB = 0,
    FINGER_INDEX = 1,
    FINGER_MIDDLE = 2,
    FINGER_RING = 3,
    FINGER_LITTLE = 4,
};

static const int HAND_FLEX_GPIO[HAND_FLEX_COUNT] = {1, 2, 4, 5, 6};
static const int HAND_FLEX_ADC_CHANNEL[HAND_FLEX_COUNT] = {0, 1, 3, 4, 5};
static const char *const HAND_FINGER_NAME[HAND_FLEX_COUNT] = {
    "thumb", "index", "middle", "ring", "little"};

#define HAND_ENABLE_GPIO 7       // LEFT hand ENABLE / HUB CALIBRATE, active low
// PROVISIONAL: 2 sweeps at the 100 Hz sample rate is the 20 ms candidate from
// FW-02. The real value must be measured at CTRL-030.
#define HAND_ENABLE_DEBOUNCE_SAMPLES 2
#define HAND_I2C_SDA_GPIO 8
#define HAND_I2C_SCL_GPIO 9
#define HAND_BATTERY_GPIO 10     // RESERVED - must stay physically disconnected

// ESP-IDF attenuation enum encoding 3: the widest documented span, 0-3100 mV on
// ESP32-S3. Never reuse the nRF `raw * 3.6 / 4096` conversion.
#define HAND_ADC_ATTENUATION 3
#define HAND_ADC_BITWIDTH 12
#define HAND_ADC_MAX_RAW 4095

// Build-time hand identity. C4/CTRL-040 requires a distinct, immutable per-board
// identity; this default is a bench placeholder, not that identity.
#ifndef HAND_SIDE_DEFAULT
#define HAND_SIDE_DEFAULT 0          // 0 = LEFT, 1 = RIGHT
#endif
