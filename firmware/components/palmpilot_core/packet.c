// SPDX-License-Identifier: MIT
#include "packet.h"

#include <string.h>

#define OFFSET_VERSION 0
#define OFFSET_LENGTH 1
#define OFFSET_SIDE 2
#define OFFSET_STATE 3
#define OFFSET_FAULT 4
#define OFFSET_FLAGS 5           // 2 bytes
#define OFFSET_SESSION 7         // 4
#define OFFSET_SEQUENCE 11       // 4
#define OFFSET_ACQUISITION 15    // 4
#define OFFSET_TIMESTAMP 19      // 8
#define OFFSET_CURL 27           // 5 x 2
#define OFFSET_ACCEL 37          // 3 x 2
#define OFFSET_GYRO 43           // 3 x 2
#define OFFSET_ROLL 49           // 2
#define OFFSET_PITCH 51          // 2
#define OFFSET_THROTTLE 53       // 2
#define OFFSET_CRC 55            // 4, covers bytes 0..54; frame is 59 bytes

static void put_u16(uint8_t *out, uint16_t value)
{
    out[0] = (uint8_t)(value & 0xFF);
    out[1] = (uint8_t)((value >> 8) & 0xFF);
}

static void put_u32(uint8_t *out, uint32_t value)
{
    for (int i = 0; i < 4; ++i) out[i] = (uint8_t)((value >> (8 * i)) & 0xFF);
}

static void put_u64(uint8_t *out, uint64_t value)
{
    for (int i = 0; i < 8; ++i) out[i] = (uint8_t)((value >> (8 * i)) & 0xFF);
}

static uint16_t get_u16(const uint8_t *in)
{
    return (uint16_t)((uint16_t)in[0] | ((uint16_t)in[1] << 8));
}

static uint32_t get_u32(const uint8_t *in)
{
    uint32_t value = 0;
    for (int i = 0; i < 4; ++i) value |= (uint32_t)in[i] << (8 * i);
    return value;
}

static uint64_t get_u64(const uint8_t *in)
{
    uint64_t value = 0;
    for (int i = 0; i < 8; ++i) value |= (uint64_t)in[i] << (8 * i);
    return value;
}

uint32_t hand_packet_crc32(const void *data, size_t length)
{
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

size_t hand_packet_encode(const struct hand_packet_source *source,
                          uint8_t *out, size_t capacity)
{
    if (capacity < HAND_PACKET_SIZE) return 0;
    memset(out, 0, HAND_PACKET_SIZE);

    out[OFFSET_VERSION] = HAND_PACKET_VERSION;
    out[OFFSET_LENGTH] = HAND_PACKET_SIZE;
    out[OFFSET_SIDE] = source->side;
    out[OFFSET_STATE] = source->state;
    out[OFFSET_FAULT] = source->fault;
    put_u16(out + OFFSET_FLAGS, source->flags);
    put_u32(out + OFFSET_SESSION, source->session);
    put_u32(out + OFFSET_SEQUENCE, source->sequence);
    put_u32(out + OFFSET_ACQUISITION, source->acquisition);
    put_u64(out + OFFSET_TIMESTAMP, (uint64_t)source->timestamp_us);
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        put_u16(out + OFFSET_CURL + i * 2, (uint16_t)source->curl_milli[i]);
    }
    for (int i = 0; i < 3; ++i) {
        put_u16(out + OFFSET_ACCEL + i * 2, (uint16_t)source->accel[i]);
        put_u16(out + OFFSET_GYRO + i * 2, (uint16_t)source->gyro[i]);
    }
    put_u16(out + OFFSET_ROLL, (uint16_t)source->roll_milli);
    put_u16(out + OFFSET_PITCH, (uint16_t)source->pitch_milli);
    put_u16(out + OFFSET_THROTTLE, (uint16_t)source->throttle_milli);
    put_u32(out + OFFSET_CRC, hand_packet_crc32(out, OFFSET_CRC));
    return HAND_PACKET_SIZE;
}

bool hand_packet_decode(const uint8_t *data, size_t length,
                        struct hand_packet_source *out)
{
    // Framing before content: a truncated or foreign packet's fields are
    // meaningless, and a hub must be able to reject it without interpreting.
    if (length != HAND_PACKET_SIZE) return false;
    if (data[OFFSET_VERSION] != HAND_PACKET_VERSION) return false;
    if (data[OFFSET_LENGTH] != HAND_PACKET_SIZE) return false;
    if (hand_packet_crc32(data, OFFSET_CRC) != get_u32(data + OFFSET_CRC)) return false;

    out->side = data[OFFSET_SIDE];
    out->state = data[OFFSET_STATE];
    out->fault = data[OFFSET_FAULT];
    out->flags = get_u16(data + OFFSET_FLAGS);
    out->session = get_u32(data + OFFSET_SESSION);
    out->sequence = get_u32(data + OFFSET_SEQUENCE);
    out->acquisition = get_u32(data + OFFSET_ACQUISITION);
    out->timestamp_us = (int64_t)get_u64(data + OFFSET_TIMESTAMP);
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        out->curl_milli[i] = (int16_t)get_u16(data + OFFSET_CURL + i * 2);
    }
    for (int i = 0; i < 3; ++i) {
        out->accel[i] = (int16_t)get_u16(data + OFFSET_ACCEL + i * 2);
        out->gyro[i] = (int16_t)get_u16(data + OFFSET_GYRO + i * 2);
    }
    out->roll_milli = (int16_t)get_u16(data + OFFSET_ROLL);
    out->pitch_milli = (int16_t)get_u16(data + OFFSET_PITCH);
    out->throttle_milli = (int16_t)get_u16(data + OFFSET_THROTTLE);
    return true;
}
