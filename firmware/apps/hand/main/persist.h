// SPDX-License-Identifier: MIT
// Calibration persistence (FW-03). Profiles are versioned, tied to a hand
// identity and integrity-checked, so a profile from another build, another
// hand or a partial write cannot be loaded as valid.
#pragma once

#include "esp_err.h"
#include "hand_core.h"

enum persist_status {
    PERSIST_OK = 0,
    PERSIST_ERR_UNAVAILABLE = 1,   // storage did not initialise
    PERSIST_ERR_MISSING = 2,       // nothing stored yet
    PERSIST_ERR_SIZE = 3,          // stored blob is the wrong size
    PERSIST_ERR_VERSION = 4,       // written by a different profile version
    PERSIST_ERR_SIDE = 5,          // belongs to the other hand
    PERSIST_ERR_CRC = 6,           // corrupt or interrupted write
    PERSIST_ERR_WRITE = 7,
};

esp_err_t persist_init(void);
bool persist_available(void);

enum persist_status persist_save(const struct hand_calibration *calibration);
enum persist_status persist_load(struct hand_calibration *out, uint8_t expected_side);
enum persist_status persist_erase(void);

// Exposed so a test can corrupt a stored profile without knowing the layout.
enum persist_status persist_corrupt_stored_crc(void);

uint32_t persist_crc32(const void *data, size_t length);
