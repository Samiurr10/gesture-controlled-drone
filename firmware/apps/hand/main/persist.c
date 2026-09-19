// SPDX-License-Identifier: MIT
#include "persist.h"

#include <string.h>

#include "nvs.h"
#include "nvs_flash.h"

#define NAMESPACE "palmpilot"
#define KEY_PROFILE "calibration"

struct stored_profile {
    uint16_t version;
    uint8_t side;
    uint8_t reserved;
    struct hand_calibration calibration;
    uint32_t crc;                  // over everything above
};

static bool s_available;

uint32_t persist_crc32(const void *data, size_t length)
{
    // Bitwise CRC-32 (reflected, polynomial 0xEDB88320). Integer only; no
    // table, because the profile is small and this runs rarely.
    const uint8_t *bytes = (const uint8_t *)data;
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < length; ++i) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; ++bit) {
            crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1)));
        }
    }
    return ~crc;
}

esp_err_t persist_init(void)
{
    esp_err_t status = nvs_flash_init();
    if (status == ESP_ERR_NVS_NO_FREE_PAGES || status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        // A truncated or outdated partition is recoverable by erasing it; the
        // stored profile is lost, which is safer than loading a partial one.
        if (nvs_flash_erase() == ESP_OK) status = nvs_flash_init();
    }
    s_available = status == ESP_OK;
    return status;
}

bool persist_available(void) { return s_available; }

static size_t crc_span(void)
{
    return offsetof(struct stored_profile, crc);
}

enum persist_status persist_save(const struct hand_calibration *calibration)
{
    if (!s_available) return PERSIST_ERR_UNAVAILABLE;
    struct stored_profile stored = {
        .version = HAND_CALIBRATION_VERSION,
        .side = calibration->side,
        .reserved = 0,
        .calibration = *calibration,
    };
    stored.crc = persist_crc32(&stored, crc_span());

    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
        return PERSIST_ERR_UNAVAILABLE;
    }
    enum persist_status result = PERSIST_OK;
    if (nvs_set_blob(handle, KEY_PROFILE, &stored, sizeof(stored)) != ESP_OK
        || nvs_commit(handle) != ESP_OK) {
        result = PERSIST_ERR_WRITE;
    }
    nvs_close(handle);
    return result;
}

static enum persist_status read_stored(struct stored_profile *stored)
{
    if (!s_available) return PERSIST_ERR_UNAVAILABLE;
    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READONLY, &handle) != ESP_OK) {
        return PERSIST_ERR_MISSING;
    }
    size_t length = 0;
    enum persist_status result = PERSIST_OK;
    if (nvs_get_blob(handle, KEY_PROFILE, NULL, &length) != ESP_OK) {
        result = PERSIST_ERR_MISSING;
    } else if (length != sizeof(*stored)) {
        result = PERSIST_ERR_SIZE;
    } else if (nvs_get_blob(handle, KEY_PROFILE, stored, &length) != ESP_OK) {
        result = PERSIST_ERR_MISSING;
    }
    nvs_close(handle);
    return result;
}

enum persist_status persist_load(struct hand_calibration *out, uint8_t expected_side)
{
    struct stored_profile stored;
    const enum persist_status read = read_stored(&stored);
    if (read != PERSIST_OK) return read;

    // Integrity before interpretation: a corrupt blob's fields mean nothing.
    if (persist_crc32(&stored, crc_span()) != stored.crc) return PERSIST_ERR_CRC;
    if (stored.version != HAND_CALIBRATION_VERSION) return PERSIST_ERR_VERSION;
    if (stored.side != expected_side) return PERSIST_ERR_SIDE;
    if (stored.calibration.side != expected_side) return PERSIST_ERR_SIDE;

    *out = stored.calibration;
    return PERSIST_OK;
}

enum persist_status persist_erase(void)
{
    if (!s_available) return PERSIST_ERR_UNAVAILABLE;
    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
        return PERSIST_ERR_UNAVAILABLE;
    }
    nvs_erase_key(handle, KEY_PROFILE);
    const esp_err_t status = nvs_commit(handle);
    nvs_close(handle);
    return status == ESP_OK ? PERSIST_OK : PERSIST_ERR_WRITE;
}

enum persist_status persist_corrupt_stored_crc(void)
{
    struct stored_profile stored;
    const enum persist_status read = read_stored(&stored);
    if (read != PERSIST_OK) return read;
    stored.crc ^= 0xA5A5A5A5u;          // deliberate integrity failure

    nvs_handle_t handle;
    if (nvs_open(NAMESPACE, NVS_READWRITE, &handle) != ESP_OK) {
        return PERSIST_ERR_UNAVAILABLE;
    }
    enum persist_status result = PERSIST_OK;
    if (nvs_set_blob(handle, KEY_PROFILE, &stored, sizeof(stored)) != ESP_OK
        || nvs_commit(handle) != ESP_OK) {
        result = PERSIST_ERR_WRITE;
    }
    nvs_close(handle);
    return result;
}
