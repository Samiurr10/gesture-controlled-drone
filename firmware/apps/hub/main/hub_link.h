// SPDX-License-Identifier: MIT
// Hub side of the BLE link (components/palmpilot_core/link.h): a NimBLE
// central that finds each hand by its advertised name, connects, negotiates the
// MTU, confirms the PalmPilot service by discovery and subscribes to packets.
// It keeps scanning until both hands are linked, and again after any drop.
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

// Both callbacks run on the NimBLE host task. `side` is enum hand_side.
typedef void (*hub_link_packet_fn)(int side, const uint8_t *data, size_t length);
// `ready` is true once the hand is subscribed and packets can flow, false when
// the link drops.
typedef void (*hub_link_ready_fn)(int side, bool ready);

struct hub_link_status {
    bool connected;
    bool ready;
    uint16_t mtu;
    uint32_t notifications;
    uint32_t connects;
    uint32_t drops;
    uint32_t adverts;
};

// NVS must already be initialised: the BLE PHY stores its RF calibration there.
esp_err_t hub_link_start(hub_link_packet_fn on_packet, hub_link_ready_fn on_ready);

// Writes one opcode to a linked hand's command characteristic.
esp_err_t hub_link_send(int side, uint8_t opcode);

void hub_link_get_status(int side, struct hub_link_status *out);
