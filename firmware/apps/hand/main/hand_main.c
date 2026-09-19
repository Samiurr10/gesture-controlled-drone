// SPDX-License-Identifier: MIT
// PalmPilot hand node - S1 acquisition increment.
//
// Timing uses esp_timer (SYSTIMER-backed), which is verified on this model.
// GPTimer/TIMG is a confirmed model gap and must not be used here
// (CLAUDE.md section 4, 2026-09-17 readiness record).
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "acquire.h"
#include "driver/uart.h"
#include "esp_chip_info.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#define FIRMWARE_FIXTURE "palmpilot-hand-v1"

// PROVISIONAL rate. FW-04 leaves acquisition rate UNSET pending measurement.
#define SAMPLE_PERIOD_US 10000        // 100 Hz
#define ACQUISITION_TASK_STACK 4096
#define ACQUISITION_TASK_PRIORITY 6
#define CONTROL_TASK_STACK 4096
#define CONTROL_TASK_PRIORITY 5
#define CONTROL_PERIOD_MS 20

// PROVISIONAL. Five missed sweeps at the 100 Hz sample rate. FW-04 leaves the
// real freshness limit UNSET pending measurement.
#define SAMPLE_STALE_LIMIT_US 50000

static SemaphoreHandle_t s_tick;
static struct hand_sample s_latest;
static portMUX_TYPE s_latest_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_ticks;      // timer callbacks issued
static volatile uint32_t s_overruns;   // ticks that found the previous one pending
static volatile int32_t s_stream_remaining;

// --- calibration state (FW-03) ---------------------------------------------
// Capture runs inside the acquisition task so every sample passes through the
// same driver path as normal operation. Command output stays inhibited for the
// whole capture: calibration never emits valid motion commands.
static struct hand_calibration s_calibration;
static struct capture_accumulator s_capture[HAND_FLEX_COUNT];
static volatile bool s_capture_active;
static bool s_capture_extended;
static uint32_t s_capture_faults;

// --- control state (FW-05) --------------------------------------------------
// The control task runs independently of acquisition, so a frozen acquisition
// task is observed as stale data rather than silently freezing the last
// command (FW-04, FW-06).
static struct hand_control s_control;
static int s_curl_milli[HAND_FLEX_COUNT];
static int s_throttle_milli = -1;
static bool s_hold_gesture;
static bool s_precision_gesture;
static volatile uint32_t s_stall_sweeps;  // deliberate acquisition stall, test hook
static SemaphoreHandle_t s_control_tick;
static volatile uint32_t s_control_updates;

static void copy_latest(struct hand_sample *out)
{
    portENTER_CRITICAL(&s_latest_lock);
    *out = s_latest;
    portEXIT_CRITICAL(&s_latest_lock);
}

static const char *calibration_reason(enum calibration_result result)
{
    switch (result) {
    case CALIBRATION_OK: return "ok";
    case CALIBRATION_ERR_FAULT: return "sensor_fault";
    case CALIBRATION_ERR_UNSTABLE: return "unstable_capture";
    case CALIBRATION_ERR_TRAVEL: return "insufficient_travel";
    case CALIBRATION_ERR_INVERTED: return "inverted_ends";
    case CALIBRATION_ERR_INCOMPLETE: return "incomplete";
    }
    return "unknown";
}

static const char *state_name(enum hand_state state)
{
    switch (state) {
    case HAND_STATE_SELFTEST: return "selftest";
    case HAND_STATE_SERVICE: return "service";
    case HAND_STATE_WAITING: return "waiting";
    case HAND_STATE_PERMITTED: return "permitted";
    case HAND_STATE_FAULT: return "fault";
    case HAND_STATE_RECOVERY: return "recovery";
    }
    return "unknown";
}

static void print_control(void)
{
    printf("{\"type\":\"control\",\"state\":\"%s\",\"valid\":%d,\"fault\":%d,"
           "\"inhibit\":%d,\"throttle_milli\":%d,\"hold\":%d,\"precision\":%d,"
           "\"updates\":%" PRIu32 ",\"curl_milli\":[",
           state_name(s_control.state), s_control.command_valid ? 1 : 0,
           (int)s_control.fault, (int)s_control.inhibit, s_throttle_milli,
           s_hold_gesture ? 1 : 0, s_precision_gesture ? 1 : 0, s_control_updates);
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        printf("%s%d", i ? "," : "", s_curl_milli[i]);
    }
    printf("]}\n");
    fflush(stdout);
}

static void on_control_tick(void *argument)
{
    (void)argument;
    xSemaphoreGive(s_control_tick);
}

static void control_task(void *argument)
{
    (void)argument;
    for (;;) {
        // Paced by esp_timer, not vTaskDelay: task delays run long on this
        // model, which left the control state lagging the sampled data.
        if (xSemaphoreTake(s_control_tick, portMAX_DELAY) != pdTRUE) continue;
        struct hand_sample sample;
        copy_latest(&sample);
        for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
            s_curl_milli[i] = hand_curl_milli(&s_calibration, i, sample.flex[i].raw);
        }
        s_throttle_milli = hand_throttle_milli(s_curl_milli);
        s_hold_gesture = hand_hold_gesture(s_curl_milli);
        s_precision_gesture = hand_precision_gesture(s_curl_milli);

        const int64_t age = esp_timer_get_time() - sample.timestamp_us;
        const struct hand_inputs inputs = {
            .started = sample.acquisition != 0,
            .healthy = hand_sample_healthy(&sample),
            .calibrated = s_calibration.valid,
            .calibrating = s_capture_active,
            // A live control loop must not treat an old sample as current.
            .fresh = age < SAMPLE_STALE_LIMIT_US,
            .enable = sample.enable_raw,
            .throttle_milli = s_throttle_milli,
        };
        hand_control_update(&s_control, &inputs);
        ++s_control_updates;
    }
}

static void print_sample(const char *kind, const struct hand_sample *sample)
{
    printf("{\"type\":\"%s\",\"acq\":%" PRIu32 ",\"t_us\":%" PRId64 ",\"raw\":[",
           kind, sample->acquisition, sample->timestamp_us);
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        printf("%s%d", i ? "," : "", sample->flex[i].raw);
    }
    printf("],\"mv\":[");
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        printf("%s%d", i ? "," : "", sample->flex[i].millivolts);
    }
    printf("],\"status\":[");
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        printf("%s%d", i ? "," : "", (int)sample->flex[i].status);
    }
    printf("],\"curl_milli\":[");
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        // -1 marks "no usable calibration", so an uncalibrated channel can
        // never be mistaken for zero travel.
        printf("%s%d", i ? "," : "",
               hand_curl_milli(&s_calibration, i, sample->flex[i].raw));
    }
    printf("],\"fault_mask\":%" PRIu32 ",\"enable\":%d,\"healthy\":%d,"
           "\"calibrated\":%d,\"calibrating\":%d}\n",
           sample->fault_mask, sample->enable_raw ? 1 : 0,
           hand_sample_healthy(sample) ? 1 : 0,
           s_calibration.valid ? 1 : 0, s_capture_active ? 1 : 0);
}

static void on_tick(void *argument)
{
    (void)argument;
    ++s_ticks;
    // A full queue means the previous tick was never serviced: acquisition is
    // running behind, which must be observable rather than silently absorbed.
    if (xSemaphoreGive(s_tick) != pdTRUE) ++s_overruns;
}

static void acquisition_task(void *argument)
{
    (void)argument;
    for (;;) {
        if (xSemaphoreTake(s_tick, portMAX_DELAY) != pdTRUE) continue;
        if (s_stall_sweeps) {
            // Deliberate fault injection: acquisition stops progressing while
            // the control task and UART keep running, which is the FW-04
            // stalled-acquisition case. Counted in sweeps rather than
            // milliseconds so the injected stall is deterministic.
            --s_stall_sweeps;
            continue;
        }
        struct hand_sample sample;
        hand_acquire_sweep(&sample);
        portENTER_CRITICAL(&s_latest_lock);
        s_latest = sample;
        portEXIT_CRITICAL(&s_latest_lock);
        if (s_capture_active) {
            s_capture_faults |= sample.fault_mask;
            bool complete = true;
            for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
                capture_add(&s_capture[i], sample.flex[i].raw);
                if (s_capture[i].count < HAND_CALIBRATION_SAMPLES) complete = false;
            }
            if (complete) {
                const enum calibration_result result = hand_calibration_store(
                    &s_calibration, s_capture_extended, s_capture, s_capture_faults);
                s_capture_active = false;
                printf("{\"type\":\"capture\",\"end\":\"%s\",\"result\":%d,"
                       "\"reason\":\"%s\",\"spread\":[",
                       s_capture_extended ? "extended" : "curled", (int)result,
                       calibration_reason(result));
                for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
                    printf("%s%d", i ? "," : "", capture_spread(&s_capture[i]));
                }
                printf("],\"mean\":[");
                for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
                    printf("%s%d", i ? "," : "", capture_mean(&s_capture[i]));
                }
                printf("]}\n");
            }
        }
        if (s_stream_remaining > 0) {
            --s_stream_remaining;
            print_sample("acq", &sample);
        }
    }
}

// Emitted before driver init, so a failure during init is still attributable.
static void emit_boot(void)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);
    printf("{\"type\":\"boot\",\"fixture\":\"%s\",\"idf\":\"%s\",\"cores\":%d,"
           "\"revision\":%d,\"reset_reason\":%d}\n",
           FIRMWARE_FIXTURE, esp_get_idf_version(), chip.cores, chip.revision,
           esp_reset_reason());
}

// Emitted only after the drivers exist; reports what was actually configured.
static void emit_info(void)
{
    printf("{\"type\":\"info\",\"fixture\":\"%s\",\"idf\":\"%s\","
           "\"sample_period_us\":%d,\"adc_attenuation\":%d,\"adc_bits\":%d,"
           "\"adc_calibrated\":%d,\"flex_gpio\":[%d,%d,%d,%d,%d],"
           "\"enable_gpio\":%d,\"debounce_samples\":%d}\n",
           FIRMWARE_FIXTURE, esp_get_idf_version(), SAMPLE_PERIOD_US,
           HAND_ADC_ATTENUATION, HAND_ADC_BITWIDTH,
           hand_acquire_calibrated() ? 1 : 0,
           HAND_FLEX_GPIO[0], HAND_FLEX_GPIO[1], HAND_FLEX_GPIO[2],
           HAND_FLEX_GPIO[3], HAND_FLEX_GPIO[4], HAND_ENABLE_GPIO,
           HAND_ENABLE_DEBOUNCE_SAMPLES);
}

static void emit_stats(void)
{
    struct hand_sample sample;
    copy_latest(&sample);
    printf("{\"type\":\"stats\",\"ticks\":%" PRIu32 ",\"acq\":%" PRIu32
           ",\"overruns\":%" PRIu32 ",\"uptime_us\":%" PRId64 "}\n",
           s_ticks, sample.acquisition, s_overruns, esp_timer_get_time());
}

static void handle_command(const char *line)
{
    int count;
    char extra;
    if (!strcmp(line, "info")) {
        emit_info();
    } else if (!strcmp(line, "sample")) {
        struct hand_sample sample;
        copy_latest(&sample);
        print_sample("sample", &sample);
    } else if (!strcmp(line, "stats")) {
        emit_stats();
    } else if (!strcmp(line, "control")) {
        print_control();
    } else if (sscanf(line, "stall %d %c", &count, &extra) == 1
               && count >= 0 && count <= 5000) {
        s_stall_sweeps = (uint32_t)count;
        printf("{\"type\":\"stalling\",\"sweeps\":%d}\n", count);
    } else if (!strcmp(line, "cal extended") || !strcmp(line, "cal curled")) {
        if (s_capture_active) {
            printf("{\"type\":\"error\",\"op\":\"cal\",\"reason\":\"busy\"}\n");
        } else {
            s_capture_extended = (line[4] == 'e');
            s_capture_faults = 0;
            for (int i = 0; i < HAND_FLEX_COUNT; ++i) capture_reset(&s_capture[i]);
            s_capture_active = true;
            printf("{\"type\":\"capturing\",\"end\":\"%s\",\"samples\":%d}\n",
                   s_capture_extended ? "extended" : "curled", HAND_CALIBRATION_SAMPLES);
        }
    } else if (!strcmp(line, "cal finish")) {
        const enum calibration_result result = hand_calibration_finish(&s_calibration);
        printf("{\"type\":\"calibration\",\"result\":%d,\"reason\":\"%s\","
               "\"valid\":%d}\n", (int)result, calibration_reason(result),
               s_calibration.valid ? 1 : 0);
    } else if (!strcmp(line, "cal reset")) {
        s_capture_active = false;
        hand_calibration_reset(&s_calibration, (enum hand_side)HAND_SIDE_DEFAULT);
        printf("{\"type\":\"calibration\",\"result\":0,\"reason\":\"reset\","
               "\"valid\":0}\n");
    } else if (!strcmp(line, "profile")) {
        printf("{\"type\":\"profile\",\"version\":%u,\"side\":%u,\"valid\":%d,"
               "\"extended\":[", s_calibration.version, s_calibration.side,
               s_calibration.valid ? 1 : 0);
        for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
            printf("%s%d", i ? "," : "", s_calibration.flex[i].extended_raw);
        }
        printf("],\"curled\":[");
        for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
            printf("%s%d", i ? "," : "", s_calibration.flex[i].curled_raw);
        }
        printf("]}\n");
    } else if (sscanf(line, "stream %d %c", &count, &extra) == 1
               && count >= 0 && count <= 4096) {
        s_stream_remaining = count;
        printf("{\"type\":\"streaming\",\"count\":%d}\n", count);
    } else {
        printf("{\"type\":\"error\",\"op\":\"command\","
               "\"help\":\"info | sample | stats | control | stream N | stall MS | "
               "cal extended | cal curled | cal finish | cal reset | profile\"}\n");
    }
    fflush(stdout);
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    emit_boot();

    hand_calibration_reset(&s_calibration, (enum hand_side)HAND_SIDE_DEFAULT);
    hand_control_init(&s_control);
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) s_curl_milli[i] = -1;
    esp_err_t status = hand_acquire_init();
    if (status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"acquire_init\",\"status\":%d}\n", status);
        return;
    }
    s_tick = xSemaphoreCreateBinary();
    if (!s_tick) {
        printf("{\"type\":\"error\",\"op\":\"semaphore\"}\n");
        return;
    }
    if (xTaskCreate(acquisition_task, "acq", ACQUISITION_TASK_STACK, NULL,
                    ACQUISITION_TASK_PRIORITY, NULL) != pdPASS) {
        printf("{\"type\":\"error\",\"op\":\"task\"}\n");
        return;
    }

    const esp_timer_create_args_t timer = {
        .callback = on_tick, .name = "acq_tick", .dispatch_method = ESP_TIMER_TASK,
    };
    esp_timer_handle_t handle;
    status = esp_timer_create(&timer, &handle);
    if (status == ESP_OK) status = esp_timer_start_periodic(handle, SAMPLE_PERIOD_US);
    if (status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"esp_timer\",\"status\":%d}\n", status);
        return;
    }

    s_control_tick = xSemaphoreCreateBinary();
    if (!s_control_tick
        || xTaskCreate(control_task, "control", CONTROL_TASK_STACK, NULL,
                       CONTROL_TASK_PRIORITY, NULL) != pdPASS) {
        printf("{\"type\":\"error\",\"op\":\"control_task\"}\n");
        return;
    }
    const esp_timer_create_args_t control_timer = {
        .callback = on_control_tick, .name = "ctl_tick",
        .dispatch_method = ESP_TIMER_TASK,
    };
    esp_timer_handle_t control_handle;
    status = esp_timer_create(&control_timer, &control_handle);
    if (status == ESP_OK) {
        status = esp_timer_start_periodic(control_handle, CONTROL_PERIOD_MS * 1000);
    }
    if (status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"control_timer\",\"status\":%d}\n", status);
        return;
    }

    status = uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
    if (status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"uart_install\",\"status\":%d}\n", status);
        return;
    }
    emit_info();
    printf("{\"type\":\"ready\",\"side\":%u}\n", s_calibration.side);

    char line[96];
    size_t used = 0;
    bool discard = false;
    for (;;) {
        unsigned char c;
        if (uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(100)) != 1) continue;
        if (c == '\r' || c == '\n') {
            if (discard) printf("{\"type\":\"error\",\"op\":\"line_too_long\"}\n");
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
