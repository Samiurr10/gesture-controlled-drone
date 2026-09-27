// SPDX-License-Identifier: MIT
// FreeRTOS tick under esp_timer load, on any SYSTIMER-based ESP chip.
//
// A periodic esp_timer at 9.9 ms re-arms SYSTIMER target 2 more often than the
// 10 ms tick period. ESP-IDF moves that alarm with a read-modify-write of the
// shared CONF register (systimer_hal_set_alarm_target), which rewrites the
// tick's TARGET0_WORK_EN unchanged. On silicon that is inert; a model that
// re-arms on it starves the tick. Reports are printed from a 1 s esp_timer, not
// from a task, so they keep coming even if the tick stops.
//
// Pass: tick rate = CONFIG_FREERTOS_HZ and vTaskDelay(10 ms) loops = 100/s.
#include <inttypes.h>
#include <stdio.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define LOAD_PERIOD_US 9900

static volatile uint32_t s_load_calls;
static volatile uint32_t s_delay_loops;
static uint32_t s_last_tick, s_last_loops, s_last_load;
static int s_report;

static void load_cb(void *arg)
{
    s_load_calls++;
}

static void report_cb(void *arg)
{
    const uint32_t tick = xTaskGetTickCount();
    const uint32_t loops = s_delay_loops, load = s_load_calls;
    printf("{\"type\":\"rate\",\"n\":%d,\"t_us\":%" PRId64 ",\"ticks\":%" PRIu32 ",\"delay_loops\":%" PRIu32
           ",\"esp_timer_load\":%" PRIu32 ",\"tick_hz\":%d}\n",
           ++s_report, esp_timer_get_time(), tick - s_last_tick, loops - s_last_loops, load - s_last_load,
           configTICK_RATE_HZ);
    s_last_tick = tick;
    s_last_loops = loops;
    s_last_load = load;
}

static void delay_task(void *arg)
{
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(10));
        s_delay_loops++;
    }
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"boot\",\"fixture\":\"palmpilot-systick-probe\",\"target\":\"%s\"}\n", CONFIG_IDF_TARGET);
    xTaskCreate(delay_task, "delay", 2048, NULL, 5, NULL);

    esp_timer_handle_t load, report;
    const esp_timer_create_args_t load_args = {.callback = load_cb, .name = "load"};
    const esp_timer_create_args_t report_args = {.callback = report_cb, .name = "report"};
    esp_timer_create(&load_args, &load);
    esp_timer_create(&report_args, &report);
    s_last_tick = xTaskGetTickCount();
    esp_timer_start_periodic(load, LOAD_PERIOD_US);
    esp_timer_start_periodic(report, 1000000);
    printf("{\"type\":\"ready\",\"load_period_us\":%d}\n", LOAD_PERIOD_US);
}
