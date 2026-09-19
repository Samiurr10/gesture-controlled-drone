// SPDX-License-Identifier: MIT
// Minimal deterministic probe: does a software reset execute?
//
// Isolates a simulator fault seen when the hand application called
// esp_restart() to verify calibration persistence across a reboot. The engine
// aborted with "Collection was modified; enumeration operation may not
// execute" - the same host error as the FPU gap, so the two may share a cause.
//
// Prints the reset reason so a successful restart is visible as a second boot.
#include <stdio.h>

#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"boot\",\"fixture\":\"palmpilot-reset-probe\","
           "\"reset_reason\":%d}\n", esp_reset_reason());
    fflush(stdout);

    // A first boot restarts once; the restarted instance reports its reason
    // and stops, so exactly one restart is attempted.
    if (esp_reset_reason() == ESP_RST_SW) {
        printf("{\"type\":\"restarted\",\"reason\":%d}\n", esp_reset_reason());
        fflush(stdout);
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }

    printf("{\"type\":\"stage\",\"name\":\"before_esp_restart\"}\n");
    fflush(stdout);
    esp_restart();
    printf("{\"type\":\"stage\",\"name\":\"after_esp_restart_unreachable\"}\n");
    fflush(stdout);
}
