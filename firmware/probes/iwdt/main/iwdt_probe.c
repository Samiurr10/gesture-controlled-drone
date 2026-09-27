// SPDX-License-Identifier: MIT
// Interrupt watchdog (IWDT) probe with production settings (300 ms, TIMG1 MWDT,
// fed from the FreeRTOS tick hook). Commands, one per line on UART0:
//
//   idle <ms>   stay healthy for <ms>; the IWDT must never fire
//   spin <ms>   busy-wait with interrupts disabled; the IWDT must panic ~300 ms in
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "driver/uart.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static void run_command(const char *line)
{
    unsigned ms = 0;
    if (sscanf(line, "idle %u", &ms) == 1) {
        const int64_t end = esp_timer_get_time() + (int64_t)ms * 1000;
        while (esp_timer_get_time() < end) {
            vTaskDelay(pdMS_TO_TICKS(10));
        }
        printf("{\"type\":\"idle_done\",\"ms\":%u,\"ticks\":%" PRIu32 "}\n", ms, (uint32_t)xTaskGetTickCount());
    } else if (sscanf(line, "spin %u", &ms) == 1) {
        printf("{\"type\":\"spin_start\",\"ms\":%u,\"t_us\":%" PRId64 "}\n", ms, esp_timer_get_time());
        fflush(stdout);
        portDISABLE_INTERRUPTS();
        const int64_t end = esp_timer_get_time() + (int64_t)ms * 1000;
        while (esp_timer_get_time() < end) {
        }
        portENABLE_INTERRUPTS();
        printf("{\"type\":\"spin_survived\",\"ms\":%u}\n", ms);
    } else {
        printf("{\"type\":\"error\",\"line\":\"%s\"}\n", line);
    }
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"boot\",\"fixture\":\"palmpilot-iwdt-probe\",\"reset_reason\":%d}\n", esp_reset_reason());
    uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
    printf("{\"type\":\"ready\"}\n");
    char line[48];
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
