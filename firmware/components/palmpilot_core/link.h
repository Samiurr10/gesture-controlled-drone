// SPDX-License-Identifier: MIT
// Hand <-> hub BLE contract. Each hand is a peripheral advertising its name;
// the hub is the central. One GATT service per hand:
//   packet   notify/read  the 59-byte hand packet (packet.h), once per update
//   command  write        one opcode byte from the hub
#pragma once

#include "host/ble_uuid.h"

#define LINK_NAME_LEFT "PalmPilot-L"
#define LINK_NAME_RIGHT "PalmPilot-R"

// 6f1d00xx-9a4e-4c2b-8d3f-5a17c0b1e2d0, in NimBLE's little-endian order.
#define LINK_UUID(id) BLE_UUID128_INIT(0xd0, 0xe2, 0xb1, 0xc0, 0x17, 0x5a, 0x3f, 0x8d, \
                                       0x2b, 0x4c, 0x4e, 0x9a, (id), 0x00, 0x1d, 0x6f)
#define LINK_SERVICE_UUID LINK_UUID(0x01)
#define LINK_PACKET_UUID LINK_UUID(0x02)
#define LINK_COMMAND_UUID LINK_UUID(0x03)

// A packet needs MTU >= 62 (59 + 3-byte notify header); the default is 23.
#define LINK_MTU 128

#define LINK_COMMAND_CAPTURE_NEUTRAL 0x01

// PROVISIONAL: 15 ms interval, 500 ms supervision timeout.
#define LINK_INTERVAL_UNITS 12           // x 1.25 ms
#define LINK_SUPERVISION_UNITS 50        // x 10 ms
