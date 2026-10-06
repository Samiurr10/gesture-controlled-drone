// SPDX-License-Identifier: MIT
// Stand-in hand: the hand's real BLE peripheral (hand_link.c) sending packets a
// host script supplies, so a test sets exactly what the hub receives over BLE.
// UART0, one command per line:
//   set <118 hex>  the packet (59 bytes, CRC checked). Every 20 ms the hand
//                  sends it with sequence, acquisition and timestamp advanced.
//   freeze 0|1     stop advancing acquisition, as a stalled sampler would
//   mute 0|1       stop sending, as a hand that went silent would
//   status
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "console.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "hand_link.h"
#include "nvs_flash.h"
#include "packet.h"

#if CONFIG_PALMPILOT_HAND_RIGHT
#define HAND_SIDE HAND_SIDE_RIGHT
#else
#define HAND_SIDE HAND_SIDE_LEFT
#endif

#define SEND_PERIOD_US 20000

static struct hand_packet_source s_packet;
static bool s_have_packet, s_frozen, s_muted;
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static SemaphoreHandle_t s_tick;

static void on_tick(void *argument)
{
    (void)argument;
    xSemaphoreGive(s_tick);
}

static void send_task(void *argument)
{
    (void)argument;
    for (;;) {
        xSemaphoreTake(s_tick, portMAX_DELAY);
        struct hand_packet_source packet;
        bool send;
        portENTER_CRITICAL(&s_lock);
        send = s_have_packet && !s_muted;
        if (send) {
            ++s_packet.sequence;
            if (!s_frozen) ++s_packet.acquisition;
            s_packet.timestamp_us = esp_timer_get_time();
            packet = s_packet;
        }
        portEXIT_CRITICAL(&s_lock);
        if (!send) continue;
        uint8_t raw[HAND_PACKET_SIZE];
        hand_link_publish(raw, hand_packet_encode(&packet, raw, sizeof(raw)));
    }
}

static int hex_nibble(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static void set_packet(const char *hex)
{
    uint8_t raw[HAND_PACKET_SIZE];
    struct hand_packet_source packet;
    bool ok = strlen(hex) == 2 * HAND_PACKET_SIZE;
    for (size_t i = 0; ok && i < HAND_PACKET_SIZE; ++i) {
        const int high = hex_nibble(hex[2 * i]), low = hex_nibble(hex[2 * i + 1]);
        ok = high >= 0 && low >= 0;
        raw[i] = (uint8_t)(high << 4 | low);
    }
    ok = ok && hand_packet_decode(raw, sizeof(raw), &packet);
    if (ok) {
        portENTER_CRITICAL(&s_lock);
        // Keep counting from where this boot is, so a new packet never replays.
        if (s_have_packet && packet.session == s_packet.session) {
            packet.sequence = s_packet.sequence;
            packet.acquisition = s_packet.acquisition;
        }
        s_packet = packet;
        s_have_packet = true;
        portEXIT_CRITICAL(&s_lock);
    }
    console_printf("{\"type\":\"set\",\"ok\":%d}\n", ok ? 1 : 0);
}

static void handle_command(char *line)
{
    if (!strncmp(line, "set ", 4)) {
        set_packet(line + 4);
    } else if (!strcmp(line, "freeze 0") || !strcmp(line, "freeze 1")) {
        s_frozen = line[7] == '1';
        console_printf("{\"type\":\"freeze\",\"on\":%d}\n", s_frozen);
    } else if (!strcmp(line, "mute 0") || !strcmp(line, "mute 1")) {
        s_muted = line[5] == '1';
        console_printf("{\"type\":\"mute\",\"on\":%d}\n", s_muted);
    } else if (!strcmp(line, "status")) {
        struct hand_link_status link;
        hand_link_get_status(&link);
        console_printf("{\"type\":\"status\",\"connected\":%d,\"subscribed\":%d,\"mtu\":%u,"
                       "\"sent\":%" PRIu32 ",\"skipped\":%" PRIu32 "}\n",
                       link.connected, link.subscribed, (unsigned)link.mtu, link.sent, link.skipped);
    } else {
        console_printf("{\"type\":\"error\",\"op\":\"command\"}\n");
    }
}

static void on_link_command(uint8_t opcode)
{
    console_printf("{\"type\":\"link_command\",\"opcode\":%u}\n", opcode);
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    esp_err_t status = nvs_flash_init();
    if (status == ESP_ERR_NVS_NO_FREE_PAGES || status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        if (nvs_flash_erase() == ESP_OK) status = nvs_flash_init();
    }
    s_tick = xSemaphoreCreateBinary();
    const esp_timer_create_args_t tick = {.callback = on_tick, .name = "send"};
    esp_timer_handle_t timer;
    if (status != ESP_OK || !s_tick
            || xTaskCreate(send_task, "send", 4096, NULL, 5, NULL) != pdPASS
            || esp_timer_create(&tick, &timer) != ESP_OK
            || esp_timer_start_periodic(timer, SEND_PERIOD_US) != ESP_OK
            || uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0) != ESP_OK
            || hand_link_start(HAND_SIDE, on_link_command) != ESP_OK) {
        console_printf("{\"type\":\"error\",\"op\":\"start\",\"status\":%d}\n", status);
        return;
    }
    console_printf("{\"type\":\"ready\",\"fixture\":\"palmpilot-replay-v1\",\"side\":%u}\n", HAND_SIDE);

    char line[160];
    size_t used = 0;
    bool discard = false;
    for (;;) {
        unsigned char c;
        if (uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c == '\r' || c == '\n') {
            if (discard) console_printf("{\"type\":\"error\",\"op\":\"line_too_long\"}\n");
            else if (used) { line[used] = 0; handle_command(line); }
            used = 0;
            discard = false;
        } else if (used < sizeof(line) - 1 && !discard) {
            line[used++] = c;
        } else {
            discard = true;
        }
    }
}
