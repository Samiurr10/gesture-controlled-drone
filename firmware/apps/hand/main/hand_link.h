// SPDX-License-Identifier: MIT
// Hand side of the BLE link (components/palmpilot_core/link.h): a NimBLE
// peripheral that advertises until the hub connects, then notifies one hand
// packet per control update.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "hand_core.h"

// Called from the NimBLE host task when the hub writes an opcode.
typedef void (*hand_link_command_fn)(uint8_t opcode);

struct hand_link_status {
    bool connected;
    bool subscribed;
    uint16_t mtu;
    uint32_t sent;
    uint32_t skipped;        // publish calls made while no packet could go out
    uint32_t connects;
};

// NVS must already be initialised (persist_init): the BLE PHY stores its RF
// calibration there.
esp_err_t hand_link_start(enum hand_side side, hand_link_command_fn on_command);

// Notifies one packet if the hub is connected, subscribed and has negotiated
// an MTU that fits it. Never blocks the caller on the radio.
void hand_link_publish(const uint8_t *packet, size_t length);

void hand_link_get_status(struct hand_link_status *out);
