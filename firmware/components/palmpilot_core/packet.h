// SPDX-License-Identifier: MIT
// Hand -> hub packet contract (FW-04).
//
// The BLE stack itself is unqualified on this platform, so this defines and
// freezes the *payload* only. Transport binding, MTU, notification rate,
// bonding and reconnect remain open and are S2 work.
//
// Layout is fixed little-endian with an explicit version and length, so a hub
// can reject an incompatible or truncated packet without guessing.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "hand_core.h"

#define HAND_PACKET_VERSION 1
#define HAND_PACKET_SIZE 59

// Flag bits. Health and permission are carried separately from the values, so
// a hub never has to infer validity from the numbers themselves.
#define HAND_FLAG_VALID (1u << 0)        // this hand permits commands right now
#define HAND_FLAG_ENABLE (1u << 1)       // debounced ENABLE, left hand only
#define HAND_FLAG_CALIBRATED (1u << 2)
#define HAND_FLAG_HOLD (1u << 3)
#define HAND_FLAG_PRECISION (1u << 4)
#define HAND_FLAG_MOTION_OK (1u << 5)
#define HAND_FLAG_USB_POWER (1u << 6)    // explicit bench power; never inferred

struct hand_packet_source {
    uint8_t side;
    uint32_t session;            // changes across resets, stable within a boot
    uint32_t sequence;
    uint32_t acquisition;        // sampling progress, not packets sent
    int64_t timestamp_us;        // hand-local monotonic sample time
    uint8_t state;
    uint8_t fault;
    uint16_t flags;
    int16_t curl_milli[HAND_FLEX_COUNT];
    int16_t accel[3];
    int16_t gyro[3];
    int16_t roll_milli;
    int16_t pitch_milli;
    int16_t throttle_milli;
};

// Writes exactly HAND_PACKET_SIZE bytes. Returns bytes written, or 0 if the
// buffer is too small.
size_t hand_packet_encode(const struct hand_packet_source *source,
                          uint8_t *out, size_t capacity);

// Verifies length, version and CRC before anything else is read.
bool hand_packet_decode(const uint8_t *data, size_t length,
                        struct hand_packet_source *out);

uint32_t hand_packet_crc32(const void *data, size_t length);
