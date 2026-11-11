// SPDX-License-Identifier: MIT
// PalmPilot hub: hands --BLE--> hub_link --> hub_core --> one command on UART0.
// All mixing and interlocks live in hub_core; this file only moves data.
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "board.h"
#include "console.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "hand_core.h"
#include "hub_core.h"
#include "hub_link.h"
#include "link.h"
#include "nvs_flash.h"

#define FIRMWARE_FIXTURE "palmpilot-hub-v1"

// PROVISIONAL: 50 Hz, the hands' control rate.
#define CONTROL_PERIOD_US 20000
#define CONTROL_TASK_PRIORITY 5
#define HOST_TASK_PRIORITY 3
#define WATCHDOG_TIMEOUT_MS 1000

// PROVISIONAL: 20 ms, as the hands; CTRL-030 must measure it.
#define CALIBRATE_DEBOUNCE_SAMPLES 1

static struct hub s_hub;
static SemaphoreHandle_t s_hub_lock;
static SemaphoreHandle_t s_control_tick;
static QueueHandle_t s_host_queue;         // latest command only, for the host
static struct debounce s_calibrate;
static bool s_watchdog_ready;
static uint32_t s_updates;

struct host_record {
    uint32_t sequence;
    int64_t time_us;
    struct hub_command command;
};

// --- BLE callbacks (NimBLE host task) -------------------------------------

// The first few rejections are reported individually; then only counted.
#define REPORTED_REJECTIONS 16

static void on_packet(int side, const uint8_t *data, size_t length)
{
    static int reported;
    const int64_t now = esp_timer_get_time();
    xSemaphoreTake(s_hub_lock, portMAX_DELAY);
    const uint32_t last_sequence = s_hub.hand[side].packet.sequence;
    const bool accepted = hub_receive(&s_hub, side, data, length, now);
    xSemaphoreGive(s_hub_lock);
    if (!accepted && reported < REPORTED_REJECTIONS) {
        ++reported;
        struct hand_packet_source packet = {0};
        const bool decoded = hand_packet_decode(data, length, &packet);
        console_printf("{\"type\":\"rejected\",\"side\":\"%s\",\"t_us\":%" PRId64
                       ",\"length\":%u,\"decoded\":%d,\"sequence\":%" PRIu32
                       ",\"last_sequence\":%" PRIu32 "}\n", side ? "right" : "left", now,
                       (unsigned)length, decoded ? 1 : 0, packet.sequence, last_sequence);
    }
}

static void on_ready(int side, bool ready)
{
    xSemaphoreTake(s_hub_lock, portMAX_DELAY);
    hub_link_changed(&s_hub, side, ready);
    xSemaphoreGive(s_hub_lock);
}

// --- control ------------------------------------------------------------------

static void on_control_tick(void *argument)
{
    (void)argument;
    xSemaphoreGive(s_control_tick);
}

static void control_task(void *argument)
{
    (void)argument;
    s_watchdog_ready = esp_task_wdt_add(NULL) == ESP_OK;
    for (;;) {
        if (xSemaphoreTake(s_control_tick, portMAX_DELAY) != pdTRUE) continue;
        const bool was_calibrating = s_calibrate.level;
        const bool calibrating = debounce_update(&s_calibrate,
                                                 gpio_get_level(HAND_ENABLE_GPIO) == 0);
        if (calibrating && !was_calibrating) {
            const esp_err_t left = hub_link_send(HAND_SIDE_LEFT, LINK_COMMAND_CAPTURE_NEUTRAL);
            const esp_err_t right = hub_link_send(HAND_SIDE_RIGHT, LINK_COMMAND_CAPTURE_NEUTRAL);
            console_printf("{\"type\":\"calibrate\",\"left\":%d,\"right\":%d}\n", left, right);
        }

        struct host_record record = {.time_us = esp_timer_get_time()};
        xSemaphoreTake(s_hub_lock, portMAX_DELAY);
        hub_update(&s_hub, calibrating, record.time_us, &record.command);
        xSemaphoreGive(s_hub_lock);
        record.sequence = ++s_updates;
        xQueueOverwrite(s_host_queue, &record);

        if (s_watchdog_ready) esp_task_wdt_reset();
    }
}

// 115200 baud can't always keep up with 50 Hz, so the host gets the newest
// command from its own task; a skipped line shows as a gap in `seq`.
static void host_task(void *argument)
{
    (void)argument;
    for (;;) {
        struct host_record r;
        if (xQueueReceive(s_host_queue, &r, portMAX_DELAY) != pdTRUE) continue;
        const struct hub_command *c = &r.command;
        console_printf("{\"type\":\"command\",\"seq\":%" PRIu32 ",\"t_us\":%" PRId64 ",\"valid\":%d,"
               "\"reason\":\"%s\",\"roll\":%d,\"pitch\":%d,\"yaw\":%d,\"throttle\":%d,"
               "\"hold\":%d,\"precision\":%d}\n",
               r.sequence, r.time_us, c->valid ? 1 : 0, hub_reason_name(c->reason),
               c->roll_milli, c->pitch_milli, c->yaw_milli, c->throttle_milli,
               c->hold ? 1 : 0, c->precision ? 1 : 0);
    }
}

// --- host commands ----------------------------------------------------------

static void emit_status(void)
{
    const int64_t now = esp_timer_get_time();
    console_lock();
    printf("{\"type\":\"status\",\"t_us\":%" PRId64 ",\"updates\":%" PRIu32 ",\"hands\":[",
           now, s_updates);
    for (int side = 0; side < 2; ++side) {
        struct hub_link_status link;
        hub_link_get_status(side, &link);
        xSemaphoreTake(s_hub_lock, portMAX_DELAY);
        const struct hub_hand hand = s_hub.hand[side];
        xSemaphoreGive(s_hub_lock);
        printf("%s{\"side\":\"%s\",\"connected\":%d,\"ready\":%d,\"mtu\":%u,"
               "\"notifications\":%" PRIu32 ",\"accepted\":%" PRIu32 ",\"rejected\":{\"unlinked\":%"
               PRIu32 ",\"format\":%" PRIu32 ",\"side\":%" PRIu32 ",\"replay\":%" PRIu32 "}"
               ",\"connects\":%" PRIu32 ",\"drops\":%" PRIu32 ",\"adverts\":%" PRIu32 ",\"age_us\":%" PRId64
               ",\"session\":%" PRIu32 ",\"acq\":%" PRIu32 ",\"state\":%u,\"flags\":%u}",
               side ? "," : "", side ? "right" : "left", link.connected ? 1 : 0,
               link.ready ? 1 : 0, (unsigned)link.mtu, link.notifications, hand.accepted,
               hand.rejected_unlinked, hand.rejected_format, hand.rejected_side,
               hand.rejected_replay, link.connects, link.drops, link.adverts,
               hand.have_packet ? now - hand.received_us : (int64_t)-1,
               hand.packet.session, hand.packet.acquisition, hand.packet.state,
               hand.packet.flags);
    }
    printf("]}\n");
    console_unlock();
}

// The latest packet each hand delivered over BLE, as decoded: lets the host see
// a hand through the link even while the combined command is invalid.
static void emit_hands(void)
{
    const int64_t now = esp_timer_get_time();
    console_lock();
    printf("{\"type\":\"hands\",\"t_us\":%" PRId64 ",\"hands\":[", now);
    for (int side = 0; side < 2; ++side) {
        xSemaphoreTake(s_hub_lock, portMAX_DELAY);
        const struct hub_hand hand = s_hub.hand[side];
        xSemaphoreGive(s_hub_lock);
        const struct hand_packet_source *p = &hand.packet;
        printf("%s{\"side\":\"%s\",\"have\":%d,\"age_us\":%" PRId64 ",\"seq\":%" PRIu32
               ",\"acq\":%" PRIu32 ",\"state\":%u,\"fault\":%u,\"flags\":%u,\"curl\":[%d,%d,%d,%d,%d]"
               ",\"accel\":[%d,%d,%d],\"gyro\":[%d,%d,%d],\"roll\":%d,\"pitch\":%d,\"throttle\":%d}",
               side ? "," : "", side ? "right" : "left", hand.have_packet ? 1 : 0,
               hand.have_packet ? now - hand.received_us : (int64_t)-1, p->sequence,
               p->acquisition, p->state, p->fault, p->flags,
               p->curl_milli[0], p->curl_milli[1], p->curl_milli[2], p->curl_milli[3], p->curl_milli[4],
               p->accel[0], p->accel[1], p->accel[2], p->gyro[0], p->gyro[1], p->gyro[2],
               p->roll_milli, p->pitch_milli, p->throttle_milli);
    }
    printf("]}\n");
    console_unlock();
}

static void handle_command(const char *line)
{
    if (!strcmp(line, "status")) {
        emit_status();
    } else if (!strcmp(line, "hands")) {
        emit_hands();
    } else {
        console_printf("{\"type\":\"error\",\"op\":\"command\",\"help\":\"status | hands\"}\n");
    }
}

// A startup failure stops the hub: no command is better than a wrong one.
static void fail(const char *op, int status)
{
    console_printf("{\"type\":\"error\",\"op\":\"%s\",\"status\":%d}\n", op, status);
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    console_printf("{\"type\":\"boot\",\"fixture\":\"%s\",\"idf\":\"%s\",\"reset_reason\":%d}\n",
           FIRMWARE_FIXTURE, esp_get_idf_version(), esp_reset_reason());

    hub_init(&s_hub);
    s_hub_lock = xSemaphoreCreateMutex();
    s_control_tick = xSemaphoreCreateBinary();
    s_host_queue = xQueueCreate(1, sizeof(struct host_record));
    if (!s_hub_lock || !s_control_tick || !s_host_queue) { fail("alloc", 0); return; }

    // NVS holds the BLE PHY's RF calibration.
    esp_err_t status = nvs_flash_init();
    if (status == ESP_ERR_NVS_NO_FREE_PAGES || status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        if (nvs_flash_erase() == ESP_OK) status = nvs_flash_init();
    }
    if (status != ESP_OK) { fail("nvs_init", status); return; }

    // Active low, external pull-up (build guide).
    const gpio_config_t calibrate_pin = {
        .pin_bit_mask = 1ULL << HAND_ENABLE_GPIO,
        .mode = GPIO_MODE_INPUT,
    };
    if ((status = gpio_config(&calibrate_pin)) != ESP_OK) { fail("gpio", status); return; }
    debounce_init(&s_calibrate, CALIBRATE_DEBOUNCE_SAMPLES, false);

    const esp_task_wdt_config_t watchdog = {
        .timeout_ms = WATCHDOG_TIMEOUT_MS, .idle_core_mask = 0, .trigger_panic = false,
    };
    status = esp_task_wdt_reconfigure(&watchdog);
    if (status == ESP_ERR_INVALID_STATE) status = esp_task_wdt_init(&watchdog);
    if (status != ESP_OK) fail("watchdog_init", status);

    if (xTaskCreate(control_task, "control", 4096, NULL, CONTROL_TASK_PRIORITY, NULL) != pdPASS
            || xTaskCreate(host_task, "host", 4096, NULL, HOST_TASK_PRIORITY, NULL) != pdPASS) {
        { fail("task", 0); return; }
    }
    const esp_timer_create_args_t tick = {
        .callback = on_control_tick, .name = "hub_tick", .dispatch_method = ESP_TIMER_TASK,
    };
    esp_timer_handle_t timer;
    status = esp_timer_create(&tick, &timer);
    if (status == ESP_OK) status = esp_timer_start_periodic(timer, CONTROL_PERIOD_US);
    if (status != ESP_OK) { fail("control_timer", status); return; }

    if ((status = hub_link_start(on_packet, on_ready)) != ESP_OK) { fail("link_start", status); return; }
    if ((status = uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0)) != ESP_OK) {
        { fail("uart_install", status); return; }
    }
    console_printf("{\"type\":\"ready\",\"fixture\":\"%s\"}\n", FIRMWARE_FIXTURE);

    char line[64];
    size_t used = 0;
    for (;;) {
        unsigned char c;
        if (uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c == '\r' || c == '\n') {
            if (used) { line[used] = 0; handle_command(line); }
            used = 0;
        } else if (used < sizeof(line) - 1) {
            line[used++] = c;
        }
    }
}
