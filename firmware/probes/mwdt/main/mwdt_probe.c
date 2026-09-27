// SPDX-License-Identifier: MIT
// Timer-group main watchdog (MWDT) probe, driven through ESP-IDF's own wdt_hal.
//
// Exercises what the IDF task and interrupt watchdogs rely on, on either timer
// group: a stage-0 interrupt at a programmed timeout, feeding that postpones
// it, the write-protect key, and a stage-0 system reset with its reset reason.
// Commands arrive one per line on UART0; results are one JSON object per line.
//
//   int <group> <ms>        arm stage 0 = interrupt, report when the ISR runs
//   feed <group> <ms> <n>   arm as above, feed every ms/4 for n feeds, then stop
//   locked <group> <ms>     arm, lock, then try to clear WDT_EN with a raw write
//   reset <group> <ms>      arm stage 0 = system reset; the next boot reports why
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "driver/uart.h"
#include "esp_intr_alloc.h"
#include "esp_rom_sys.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "hal/wdt_hal.h"
#include "soc/interrupts.h"
#include "soc/reset_reasons.h"
#include "soc/timer_group_reg.h"

// 80 MHz APB / 40000 = one tick per 500 us, the prescaler the IDF watchdogs use.
#define PRESCALER 40000
#define TICKS_PER_MS 2

static wdt_hal_context_t s_hal[2];
static intr_handle_t s_intr[2];
static volatile int64_t s_fired_us[2];
static volatile int s_fired_count[2];

static void IRAM_ATTR wdt_isr(void *arg)
{
    const int group = (int)arg;
    s_fired_us[group] = esp_timer_get_time();
    s_fired_count[group]++;
    wdt_hal_write_protect_disable(&s_hal[group]);
    wdt_hal_handle_intr(&s_hal[group]);
    wdt_hal_disable(&s_hal[group]);
    wdt_hal_write_protect_enable(&s_hal[group]);
}

static void arm(int group, uint32_t ms, wdt_stage_action_t action)
{
    wdt_hal_context_t *hal = &s_hal[group];
    wdt_hal_init(hal, group ? WDT_MWDT1 : WDT_MWDT0, PRESCALER, action == WDT_STAGE_ACTION_INT);
    s_fired_count[group] = 0;
    s_fired_us[group] = 0;
    wdt_hal_write_protect_disable(hal);
    wdt_hal_config_stage(hal, WDT_STAGE0, ms * TICKS_PER_MS, action);
    wdt_hal_enable(hal);
    wdt_hal_write_protect_enable(hal);
}

static void disarm(int group)
{
    wdt_hal_write_protect_disable(&s_hal[group]);
    wdt_hal_disable(&s_hal[group]);
    wdt_hal_write_protect_enable(&s_hal[group]);
}

// Wait up to limit_ms of esp_timer time for the ISR; report the latency.
static void report_int(const char *test, int group, uint32_t ms, int64_t from_us, uint32_t limit_ms)
{
    const int64_t deadline = from_us + (int64_t)limit_ms * 1000;
    while (s_fired_count[group] == 0 && esp_timer_get_time() < deadline) {
        vTaskDelay(1);
    }
    const int fired = s_fired_count[group];
    const int64_t elapsed = fired ? s_fired_us[group] - from_us : -1;
    printf("{\"type\":\"result\",\"test\":\"%s\",\"group\":%d,\"programmed_ms\":%" PRIu32
           ",\"fired\":%d,\"elapsed_us\":%" PRId64 "}\n", test, group, ms, fired, elapsed);
    disarm(group);
}

static void run_command(char *line)
{
    char name[16] = {0};
    int group = -1;
    unsigned ms = 0, count = 0;
    if (sscanf(line, "%15s %d %u %u", name, &group, &ms, &count) < 3 || group < 0 || group > 1) {
        printf("{\"type\":\"error\",\"line\":\"%s\"}\n", line);
        return;
    }
    if (!strcmp(name, "int")) {
        const int64_t start = esp_timer_get_time();
        arm(group, ms, WDT_STAGE_ACTION_INT);
        report_int("int", group, ms, start, ms * 3);
    } else if (!strcmp(name, "feed")) {
        arm(group, ms, WDT_STAGE_ACTION_INT);
        int64_t last_feed = esp_timer_get_time();
        const int64_t period_us = (int64_t)ms * 1000 / 4;
        for (unsigned i = 0; i < count; i++) {
            while (esp_timer_get_time() - last_feed < period_us) {
                vTaskDelay(1);
            }
            wdt_hal_write_protect_disable(&s_hal[group]);
            wdt_hal_feed(&s_hal[group]);
            wdt_hal_write_protect_enable(&s_hal[group]);
            last_feed = esp_timer_get_time();
        }
        printf("{\"type\":\"fed\",\"group\":%d,\"feeds\":%u,\"fired_while_fed\":%d}\n",
               group, count, s_fired_count[group]);
        report_int("feed_then_stop", group, ms, last_feed, ms * 3);
    } else if (!strcmp(name, "locked")) {
        const int64_t start = esp_timer_get_time();
        arm(group, ms, WDT_STAGE_ACTION_INT);
        // Protected: silicon ignores this write while WDTWPROTECT is locked.
        REG_WRITE(TIMG_WDTCONFIG0_REG(group), 0);
        report_int("locked", group, ms, start, ms * 3);
    } else if (!strcmp(name, "reset")) {
        printf("{\"type\":\"arming_reset\",\"group\":%d,\"programmed_ms\":%u,\"t_us\":%" PRId64 "}\n",
               group, ms, esp_timer_get_time());
        fflush(stdout);
        arm(group, ms, WDT_STAGE_ACTION_RESET_SYSTEM);
        for (;;) {
            vTaskDelay(1);
        }
    } else {
        printf("{\"type\":\"error\",\"line\":\"%s\"}\n", line);
    }
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"boot\",\"fixture\":\"palmpilot-mwdt-probe\",\"reset_reason\":%d,"
           "\"rom_reason\":%d}\n", esp_reset_reason(), (int)esp_rom_get_reset_reason(0));

    for (int group = 0; group < 2; group++) {
        const int source = group ? ETS_TG1_WDT_LEVEL_INTR_SOURCE : ETS_TG0_WDT_LEVEL_INTR_SOURCE;
        const esp_err_t status = esp_intr_alloc(source, 0, wdt_isr, (void *)group, &s_intr[group]);
        printf("{\"type\":\"intr\",\"group\":%d,\"source\":%d,\"status\":%d}\n", group, source, status);
    }

    uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
    printf("{\"type\":\"ready\"}\n");
    char line[64];
    size_t used = 0;
    for (;;) {
        uint8_t c;
        if (uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c == '\r') continue;
        if (c != '\n' && used < sizeof(line) - 1) {
            line[used++] = (char)c;
            continue;
        }
        line[used] = '\0';
        used = 0;
        run_command(line);
        printf("{\"type\":\"done\"}\n");
    }
}
