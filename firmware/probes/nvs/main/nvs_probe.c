// SPDX-License-Identifier: MIT
// Minimal deterministic probe: which NVS operations complete?
//
// Isolates a hang seen in the hand application's calibration persistence.
// Reads and blob writes complete, but nvs_erase_key never returns: the task
// stops with no error, no panic and no further output, and stays silent for
// at least 60 simulated seconds.
//
// Each stage prints before and after, so the exact blocking call is visible.
#include <stdio.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"

#define NAMESPACE "probe"
#define KEY "blob"

static SemaphoreHandle_t s_wake;
static volatile uint32_t s_ticks;

static void on_tick(void *argument)
{
    (void)argument;
    ++s_ticks;
    xSemaphoreGive(s_wake);
}

// Runs from flash, like the hand application's acquisition and control tasks.
static void background_task(void *argument)
{
    (void)argument;
    volatile uint32_t accumulator = 0;
    for (;;) {
        if (xSemaphoreTake(s_wake, portMAX_DELAY) != pdTRUE) continue;
        for (int i = 0; i < 64; ++i) accumulator += i;
    }
}

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

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("{\"type\":\"ready\",\"fixture\":\"palmpilot-nvs-probe\"}\n");
    fflush(stdout);

    stage("flash_init");
    esp_err_t status = nvs_flash_init();
    if (status == ESP_ERR_NVS_NO_FREE_PAGES || status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        status = nvs_flash_init();
    }
    result("flash_init", status);
    if (status != ESP_OK) return;

    uint8_t payload[72];
    memset(payload, 0x5A, sizeof(payload));
    nvs_handle_t handle;

    stage("open_readwrite");
    result("open_readwrite", nvs_open(NAMESPACE, NVS_READWRITE, &handle));
    stage("set_blob");
    result("set_blob", nvs_set_blob(handle, KEY, payload, sizeof(payload)));
    stage("commit_write");
    result("commit_write", nvs_commit(handle));
    nvs_close(handle);

    stage("open_readonly");
    result("open_readonly", nvs_open(NAMESPACE, NVS_READONLY, &handle));
    size_t length = sizeof(payload);
    stage("get_blob");
    result("get_blob", nvs_get_blob(handle, KEY, payload, &length));
    nvs_close(handle);

    // Everything above completes. The call below is the one that never
    // returns, so no stage after it is ever printed.
    stage("open_readwrite_for_erase");
    result("open_readwrite_for_erase", nvs_open(NAMESPACE, NVS_READWRITE, &handle));
    stage("erase_key");
    result("erase_key", nvs_erase_key(handle, KEY));
    stage("commit_erase");
    result("commit_erase", nvs_commit(handle));
    nvs_close(handle);

    // Stage 2: repeat the same cycle with a periodic esp_timer driving a
    // background task, which is what the hand application actually does. A
    // flash erase disables the cache and suspends the scheduler, so this is
    // where the two differ.
    printf("{\"type\":\"phase\",\"name\":\"background_tasks_started\"}\n");
    fflush(stdout);
    s_wake = xSemaphoreCreateBinary();
    xTaskCreate(background_task, "bg", 4096, NULL, 6, NULL);
    const esp_timer_create_args_t timer = {
        .callback = on_tick, .name = "bg_tick", .dispatch_method = ESP_TIMER_TASK,
    };
    esp_timer_handle_t handle_timer;
    esp_timer_create(&timer, &handle_timer);
    esp_timer_start_periodic(handle_timer, 10000);     // 100 Hz, as the hand does
    vTaskDelay(pdMS_TO_TICKS(200));
    printf("{\"type\":\"ticks\",\"count\":%u}\n", (unsigned)s_ticks);
    fflush(stdout);

    stage("busy_open_readwrite");
    result("busy_open_readwrite", nvs_open(NAMESPACE, NVS_READWRITE, &handle));
    stage("busy_set_blob");
    result("busy_set_blob", nvs_set_blob(handle, KEY, payload, sizeof(payload)));
    stage("busy_commit_write");
    result("busy_commit_write", nvs_commit(handle));
    stage("busy_erase_key");
    result("busy_erase_key", nvs_erase_key(handle, KEY));
    stage("busy_commit_erase");
    result("busy_commit_erase", nvs_commit(handle));
    nvs_close(handle);

    printf("{\"type\":\"done\"}\n");
    fflush(stdout);
}
