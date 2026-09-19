// SPDX-License-Identifier: MIT
// Public ESP-IDF gptimer driver probe: does the timer group actually count?
//
// Against the stock model this hangs in gptimer_get_raw_count, inside
// timer_ll_trigger_soft_capture (timer_ll.h:194), because the UPDATE bit never
// self-clears. Each stage prints before and after, so a hang is attributable.
#include <inttypes.h>
#include <stdio.h>

#include "driver/gptimer.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define RESOLUTION_HZ 1000000       // 1 MHz, so counts are microseconds
#define ALARM_COUNT 50000           // 50 ms

static volatile uint32_t s_alarms;
static volatile bool s_log_from_isr;
static volatile uint64_t s_last_count;

static void stage(const char *name)
{
    printf("{\"type\":\"stage\",\"name\":\"%s\"}\n", name);
    fflush(stdout);
}

static void result(const char *name, esp_err_t status)
{
    printf("{\"type\":\"result\",\"name\":\"%s\",\"status\":%d}\n", name, status);
    fflush(stdout);
}

static bool IRAM_ATTR on_alarm(gptimer_handle_t timer,
                               const gptimer_alarm_event_data_t *event, void *context)
{
    (void)timer; (void)context;
    ++s_alarms;
    s_last_count = event->count_value;
    // The task watchdog's ISR logs heavily through esp_rom_printf, which writes
    // UART registers directly from interrupt context. Reproduce that here to
    // separate "interrupt delivery" from "logging inside an ISR".
    if(s_log_from_isr) {
        esp_rom_printf("{\"type\":\"isr_log\",\"alarm\":%u}\n",
                       (unsigned)s_alarms);
    }
    return false;
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"ready\",\"fixture\":\"palmpilot-gptimer-probe\"}\n");
    fflush(stdout);

    gptimer_handle_t timer = NULL;
    const gptimer_config_t config = {
        .clk_src = GPTIMER_CLK_SRC_DEFAULT,
        .direction = GPTIMER_COUNT_UP,
        .resolution_hz = RESOLUTION_HZ,
    };
    stage("new_timer");
    result("new_timer", gptimer_new_timer(&config, &timer));

    const gptimer_event_callbacks_t callbacks = { .on_alarm = on_alarm };
    stage("register_callbacks");
    result("register_callbacks", gptimer_register_event_callbacks(timer, &callbacks, NULL));

    const gptimer_alarm_config_t alarm = {
        .alarm_count = ALARM_COUNT,
        .reload_count = 0,
        .flags.auto_reload_on_alarm = true,
    };
    stage("set_alarm_action");
    result("set_alarm_action", gptimer_set_alarm_action(timer, &alarm));
    stage("enable");
    result("enable", gptimer_enable(timer));
    stage("start");
    result("start", gptimer_start(timer));

    // The call that hangs against the stock model.
    stage("get_raw_count");
    uint64_t count = 0;
    result("get_raw_count", gptimer_get_raw_count(timer, &count));
    printf("{\"type\":\"count\",\"when\":\"first\",\"value\":%" PRIu64 "}\n", count);
    fflush(stdout);

    // 30 ms against a 50 ms alarm, so sampling is not phase-locked to the
    // reload and a stuck counter is distinguishable from a periodic one.
    for(int i = 0; i < 10; ++i) {
        vTaskDelay(pdMS_TO_TICKS(30));
        gptimer_get_raw_count(timer, &count);
        printf("{\"type\":\"sample\",\"index\":%d,\"count\":%" PRIu64
               ",\"alarms\":%" PRIu32 ",\"last_alarm_count\":%" PRIu64
               ",\"esp_timer_us\":%" PRId64 "}\n",
               i, count, s_alarms, s_last_count, esp_timer_get_time());
        fflush(stdout);
    }

    // Now repeat with the ISR logging, which is what the TWDT ISR does.
    stage("enable_isr_logging");
    s_log_from_isr = true;
    vTaskDelay(pdMS_TO_TICKS(200));
    result("enable_isr_logging", ESP_OK);
    s_log_from_isr = false;

    // Two reads with no delay between them: the second must be larger, which
    // a latched-but-static snapshot could not produce.
    uint64_t back_to_back_a = 0, back_to_back_b = 0;
    gptimer_get_raw_count(timer, &back_to_back_a);
    for(volatile int spin = 0; spin < 2000; ++spin) { }
    gptimer_get_raw_count(timer, &back_to_back_b);
    printf("{\"type\":\"advance\",\"first\":%" PRIu64 ",\"second\":%" PRIu64
           ",\"advanced\":%d}\n", back_to_back_a, back_to_back_b,
           back_to_back_b > back_to_back_a ? 1 : 0);
    fflush(stdout);

    printf("{\"type\":\"done\",\"alarms\":%" PRIu32 "}\n", s_alarms);
    fflush(stdout);
}
