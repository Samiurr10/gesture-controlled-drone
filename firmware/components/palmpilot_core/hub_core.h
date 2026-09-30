// SPDX-License-Identifier: MIT
// Hub logic: validates both hands and mixes them into one drone command.
// Pure C, no ESP-IDF. Mapping (docs/controller/gesture-mapping.md):
//
//   roll = right roll tilt     pitch = right pitch tilt
//   yaw  = left roll tilt      throttle = left four-finger curl
//   HOLD (right fist): attitude to zero, throttle frozen
//   PRECISION (left thumb): roll, pitch and yaw halved
//
// then slew limits and bounds. Valid only while both hands are fresh and
// healthy and the left hand permits it. Any loss of validity latches until
// the left ENABLE is released and pressed again.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "packet.h"

// PROVISIONAL: five 20 ms updates, on the hub's own clock.
#define HUB_PACKET_MAX_AGE_US 100000      // last packet must be this recent
#define HUB_PROGRESS_MAX_AGE_US 100000    // and the hand's sampler must have advanced

enum hub_reason {
    HUB_OK = 0,
    HUB_LEFT_MISSING = 1,        // no link or no packet yet
    HUB_RIGHT_MISSING = 2,
    HUB_LEFT_STALE = 3,          // packets stopped
    HUB_RIGHT_STALE = 4,
    HUB_LEFT_FROZEN = 5,         // packets arrive, acquisition stopped
    HUB_RIGHT_FROZEN = 6,
    HUB_LEFT_NOT_READY = 7,      // fault or uncalibrated
    HUB_RIGHT_NOT_READY = 8,
    HUB_CALIBRATING = 9,         // hub CALIBRATE held
    HUB_NOT_ENABLED = 10,        // left hand not permitting
    HUB_AWAIT_RELEASE = 11,      // latched: release ENABLE, press again
};

struct hub_hand {
    bool connected;
    bool have_packet;
    struct hand_packet_source packet;
    int64_t received_us;             // hub clock, last accepted packet
    int64_t progressed_us;           // hub clock, last acquisition advance
    uint32_t accepted;
    uint32_t rejected_unlinked;
    uint32_t rejected_format;        // length, version or CRC
    uint32_t rejected_side;          // the other hand's packet on this link
    uint32_t rejected_replay;        // sequence did not advance
};

struct hub_command {
    bool valid;
    enum hub_reason reason;
    int roll_milli;                  // [-1000, 1000]
    int pitch_milli;
    int yaw_milli;
    int throttle_milli;              // [0, 1000]
    bool hold;
    bool precision;
};

struct hub {
    struct hub_hand hand[2];         // indexed by enum hand_side
    bool active;
    bool await_release;
    int hold_throttle;
    bool was_holding;
    struct hub_command out;          // last command; the slew state
};

void hub_init(struct hub *hub);

// Dropping a link forgets its packets, so a reconnect starts from nothing.
void hub_link_changed(struct hub *hub, int side, bool connected);

// Returns true when the packet was accepted.
bool hub_receive(struct hub *hub, int side, const uint8_t *data, size_t length,
                 int64_t now_us);

void hub_update(struct hub *hub, bool calibrating, int64_t now_us,
                struct hub_command *out);

const char *hub_reason_name(enum hub_reason reason);
