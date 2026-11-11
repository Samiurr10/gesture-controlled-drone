// SPDX-License-Identifier: MIT
// PalmPilot hand node: samples flex, ENABLE (left only) and motion, and sends
// one packet per control update to the hub over BLE. The hand reports and flags
// gestures; mapping, HOLD, PRECISION and slew live in the hub (hub_core.h).
//
// Timing uses esp_timer (SYSTIMER-backed), which is verified on this model.
// GPTimer/TIMG is a confirmed model gap and must not be used here
// (CLAUDE.md section 4, 2026-09-17 readiness record).
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "acquire.h"
#include "console.h"
#include "driver/uart.h"
#include "esp_chip_info.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "hand_link.h"
#include "esp_timer.h"
#include "motion.h"
#include "esp_random.h"
#include "packet.h"
#include "persist.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "link.h"

#define FIRMWARE_FIXTURE "palmpilot-hand-v1"

// `palmpilot.py build hand:right` selects sdkconfig.right.
#if CONFIG_PALMPILOT_HAND_RIGHT
#define HAND_SIDE HAND_SIDE_RIGHT
#else
#define HAND_SIDE HAND_SIDE_LEFT
#endif
#define HAND_SIDE_NAME (HAND_SIDE == HAND_SIDE_RIGHT ? "right" : "left")

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

// PROVISIONAL watchdog period. Long enough that ordinary jitter cannot trip it,
// short enough that a stalled loop is caught quickly. UNSET until measured.
#define WATCHDOG_TIMEOUT_MS 1000

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

// What this hand reports: tilt about its own axes and throttle from curl.
static int s_out_roll;
static int s_out_pitch;
static int s_out_throttle;

// Set by the BLE host task, acted on by the control task.
static volatile bool s_neutral_requested;

// Packet identity. The session changes across resets so a hub can invalidate
// continuity; the sequence counts packets built, one per control update, and is
// deliberately separate from the acquisition counter so a frozen sampler behind
// a live link is detectable (FW-04).
static uint32_t s_session;
static uint32_t s_packet_sequence;

// Watchdog bookkeeping. The count is incremented from the timeout handler, so
// a trip is observable without a reset: bench builds leave trigger_panic off,
// so a test can count trips and keep talking to the hand.
static volatile uint32_t s_watchdog_trips;
// Counts services. With the trip count above, the feed count is how the rule
// "service only after real work" is verified (S1-H): feeds stop when the loop
// stalls, and the watchdog then trips.
static volatile uint32_t s_watchdog_feeds;
static bool s_watchdog_ready;
static volatile uint32_t s_stall_sweeps;  // deliberate acquisition stall, test hook
static SemaphoreHandle_t s_control_tick;
static volatile uint32_t s_control_updates;

// Motion is acquired on the same sweep as the flex channels so a command can
// be traced to one coherent set of inputs.
static struct motion_sample s_motion;
static portMUX_TYPE s_motion_lock = portMUX_INITIALIZER_UNLOCKED;
static bool s_motion_available;

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

static size_t build_packet(uint8_t *buffer, size_t capacity)
{
    struct hand_sample sample;
    copy_latest(&sample);
    struct motion_sample motion;
    portENTER_CRITICAL(&s_motion_lock);
    motion = s_motion;
    portEXIT_CRITICAL(&s_motion_lock);

    uint16_t flags = HAND_FLAG_USB_POWER;      // bench power is explicit
    if (s_control.command_valid) flags |= HAND_FLAG_VALID;
    if (sample.enable_raw) flags |= HAND_FLAG_ENABLE;
    if (s_calibration.valid) flags |= HAND_FLAG_CALIBRATED;
    if (s_hold_gesture) flags |= HAND_FLAG_HOLD;
    if (s_precision_gesture) flags |= HAND_FLAG_PRECISION;
    if (s_motion_available && motion.accel_gyro == MOTION_OK) flags |= HAND_FLAG_MOTION_OK;

    struct hand_packet_source source = {
        .side = HAND_SIDE,
        .session = s_session,
        .sequence = ++s_packet_sequence,
        .acquisition = sample.acquisition,
        .timestamp_us = sample.timestamp_us,
        .state = (uint8_t)s_control.state,
        .fault = (uint8_t)s_control.fault,
        .flags = flags,
        .roll_milli = (int16_t)s_out_roll,
        .pitch_milli = (int16_t)s_out_pitch,
        .throttle_milli = (int16_t)s_out_throttle,
    };
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        source.curl_milli[i] = (int16_t)s_curl_milli[i];
    }
    for (int i = 0; i < 3; ++i) {
        source.accel[i] = motion.accel[i];
        source.gyro[i] = motion.gyro[i];
    }

    return hand_packet_encode(&source, buffer, capacity);
}

// Last packet built for the hub; `packet` prints it without touching the sequence.
static uint8_t s_last_packet[HAND_PACKET_SIZE];
static size_t s_last_packet_size;
static portMUX_TYPE s_packet_lock = portMUX_INITIALIZER_UNLOCKED;

static void print_packet(void)
{
    uint8_t buffer[HAND_PACKET_SIZE];
    portENTER_CRITICAL(&s_packet_lock);
    const size_t written = s_last_packet_size;
    memcpy(buffer, s_last_packet, sizeof(buffer));
    portEXIT_CRITICAL(&s_packet_lock);
    printf("{\"type\":\"packet\",\"bytes\":%u,\"hex\":\"", (unsigned)written);
    for (size_t i = 0; i < written; ++i) printf("%02x", buffer[i]);
    printf("\"}\n");
    fflush(stdout);
}

static void print_storage(const char *operation, enum persist_status status)
{
    printf("{\"type\":\"storage\",\"op\":\"%s\",\"status\":%d,"
           "\"available\":%d,\"calibrated\":%d}\n",
           operation, (int)status, persist_available() ? 1 : 0,
           s_calibration.valid ? 1 : 0);
    fflush(stdout);
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
           "\"updates\":%" PRIu32 ",\"roll_milli\":%d,\"pitch_milli\":%d,"
           "\"out_throttle_milli\":%d,\"curl_milli\":[",
           state_name(s_control.state), s_control.command_valid ? 1 : 0,
           (int)s_control.fault, (int)s_control.inhibit, s_throttle_milli,
           s_hold_gesture ? 1 : 0, s_precision_gesture ? 1 : 0, s_control_updates,
           s_out_roll, s_out_pitch, s_out_throttle);
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        printf("%s%d", i ? "," : "", s_curl_milli[i]);
    }
    printf("]}\n");
    fflush(stdout);
}

// Overrides the weak ESP-IDF symbol. Runs in ISR context: count only.
void esp_task_wdt_isr_user_handler(void)
{
    ++s_watchdog_trips;
}

static enum calibration_result capture_neutral(void)
{
    struct motion_sample motion;
    portENTER_CRITICAL(&s_motion_lock);
    motion = s_motion;
    portEXIT_CRITICAL(&s_motion_lock);
    if (!s_motion_available || motion.accel_gyro != MOTION_OK) return CALIBRATION_ERR_FAULT;
    return hand_calibration_store_neutral(&s_calibration, motion.accel);
}

// Hub CALIBRATE. Refused while permitted, like every calibration change.
static void capture_neutral_for_hub(void)
{
    enum calibration_result result = CALIBRATION_ERR_INCOMPLETE;
    const bool refused = s_control.state == HAND_STATE_PERMITTED;
    if (!refused) {
        result = capture_neutral();
        const enum calibration_result finish = hand_calibration_finish(&s_calibration);
        if (result == CALIBRATION_OK) result = finish;
    }
    console_printf("{\"type\":\"neutral\",\"source\":\"hub\",\"refused\":%d,\"result\":%d,"
           "\"reason\":\"%s\",\"valid\":%d,\"ratio\":[%d,%d,%d]}\n",
           refused ? 1 : 0, (int)result, calibration_reason(result),
           s_calibration.valid ? 1 : 0, s_calibration.neutral_ratio[0],
           s_calibration.neutral_ratio[1], s_calibration.neutral_ratio[2]);
}

static void on_link_command(uint8_t opcode)
{
    if (opcode == LINK_COMMAND_CAPTURE_NEUTRAL) s_neutral_requested = true;
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

        struct motion_sample motion;
        portENTER_CRITICAL(&s_motion_lock);
        motion = s_motion;
        portEXIT_CRITICAL(&s_motion_lock);
        const bool motion_ok = s_motion_available && motion.accel_gyro == MOTION_OK;

        int roll_target = 0, pitch_target = 0;
        int throttle_target = s_throttle_milli < 0 ? 0 : s_throttle_milli;
        if (motion_ok && s_calibration.valid) {
            roll_target = hand_axis_command_milli(
                hand_tilt_ratio_milli(motion.accel, 1), s_calibration.neutral_ratio[1]);
            pitch_target = hand_axis_command_milli(
                hand_tilt_ratio_milli(motion.accel, 0), s_calibration.neutral_ratio[0]);
        }
        s_out_roll = roll_target;
        s_out_pitch = pitch_target;
        s_out_throttle = throttle_target;

        const int64_t age = esp_timer_get_time() - sample.timestamp_us;
        const struct hand_inputs inputs = {
            .started = sample.acquisition != 0,
            .healthy = hand_sample_healthy(&sample),
            .calibrated = s_calibration.valid,
            .calibrating = s_capture_active,
            .motion_ok = motion_ok,
            // A live control loop must not treat an old sample as current.
            .fresh = age < SAMPLE_STALE_LIMIT_US,
            .enable = sample.enable_raw,
            .throttle_milli = s_throttle_milli,
        };
        if (!s_watchdog_ready) {
            // Subscribe from inside the task that must prove liveness.
            s_watchdog_ready = esp_task_wdt_add(NULL) == ESP_OK;
        }
        hand_control_update(&s_control, &inputs);
        ++s_control_updates;
        if (s_neutral_requested) {
            s_neutral_requested = false;
            capture_neutral_for_hub();
        }

        uint8_t packet[HAND_PACKET_SIZE];
        const size_t size = build_packet(packet, sizeof(packet));
        portENTER_CRITICAL(&s_packet_lock);
        memcpy(s_last_packet, packet, sizeof(packet));
        s_last_packet_size = size;
        portEXIT_CRITICAL(&s_packet_lock);
        hand_link_publish(packet, size);

        // FW-06: feed only after the loop has actually done its work on fresh
        // data - acquisition progressed, validation ran and the output stage
        // was updated. A timer-driven feed would prove only that the timer
        // still ticks, which is exactly what a watchdog must not accept.
        if (s_watchdog_ready && inputs.started && inputs.fresh) {
            esp_task_wdt_reset();
            ++s_watchdog_feeds;
        }
    }
}

static void print_motion(void)
{
    struct motion_sample motion;
    portENTER_CRITICAL(&s_motion_lock);
    motion = s_motion;
    portEXIT_CRITICAL(&s_motion_lock);
    printf("{\"type\":\"motion\",\"accel_gyro\":%d,\"mag_status\":%d,"
           "\"accel\":[%d,%d,%d],\"gyro\":[%d,%d,%d],\"mag\":[%d,%d,%d],"
           "\"id_accel_gyro\":%u,\"id_mag\":%u}\n",
           (int)motion.accel_gyro, (int)motion.mag_status,
           motion.accel[0], motion.accel[1], motion.accel[2],
           motion.gyro[0], motion.gyro[1], motion.gyro[2],
           motion.mag[0], motion.mag[1], motion.mag[2],
           motion_accel_gyro_identity(), motion_mag_identity());
    fflush(stdout);
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
        if (s_motion_available) {
            struct motion_sample motion;
            motion_read(&motion);
            portENTER_CRITICAL(&s_motion_lock);
            s_motion = motion;
            portEXIT_CRITICAL(&s_motion_lock);
        }
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
                console_lock();
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
                console_unlock();
            }
        }
        if (s_stream_remaining > 0) {
            --s_stream_remaining;
            console_lock();
            print_sample("acq", &sample);
            console_unlock();
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
           "\"enable_gpio\":%d,\"debounce_samples\":%d,\"i2c_sda\":%d,"
           "\"i2c_scl\":%d,\"motion_init\":%d}\n",
           FIRMWARE_FIXTURE, esp_get_idf_version(), SAMPLE_PERIOD_US,
           HAND_ADC_ATTENUATION, HAND_ADC_BITWIDTH,
           hand_acquire_calibrated() ? 1 : 0,
           HAND_FLEX_GPIO[0], HAND_FLEX_GPIO[1], HAND_FLEX_GPIO[2],
           HAND_FLEX_GPIO[3], HAND_FLEX_GPIO[4], HAND_ENABLE_GPIO,
           HAND_ENABLE_DEBOUNCE_SAMPLES, HAND_I2C_SDA_GPIO, HAND_I2C_SCL_GPIO,
           s_motion_available ? 1 : 0);
}

static void emit_stats(void)
{
    struct hand_sample sample;
    copy_latest(&sample);
    printf("{\"type\":\"stats\",\"ticks\":%" PRIu32 ",\"acq\":%" PRIu32
           ",\"overruns\":%" PRIu32 ",\"uptime_us\":%" PRId64
           ",\"watchdog_trips\":%" PRIu32 ",\"watchdog_feeds\":%" PRIu32
           ",\"watchdog\":%d}\n",
           s_ticks, sample.acquisition, s_overruns, esp_timer_get_time(),
           s_watchdog_trips, s_watchdog_feeds, s_watchdog_ready ? 1 : 0);
}

// Runs with the console held, so every reply is one uninterrupted line.
static void handle_command_locked(const char *line)
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
    } else if (!strcmp(line, "packet")) {
        print_packet();
    } else if (!strcmp(line, "motion")) {
        print_motion();
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
    } else if (!strcmp(line, "cal save")) {
        // A flash write suspends the scheduler on real hardware, so it must
        // never run while this hand is permitting commands. Only a validated
        // profile is worth persisting.
        if (s_control.state == HAND_STATE_PERMITTED) {
            print_storage("save", PERSIST_ERR_WRITE);
        } else {
            print_storage("save", s_calibration.valid
                          ? persist_save(&s_calibration)
                          : PERSIST_ERR_VERSION);
        }
    } else if (!strcmp(line, "cal load")) {
        struct hand_calibration loaded;
        const enum persist_status status =
            persist_load(&loaded, (uint8_t)HAND_SIDE);
        if (status == PERSIST_OK) {
            // Re-derive validity rather than trusting the stored flag.
            hand_calibration_finish(&loaded);
            s_calibration = loaded;
        }
        print_storage("load", status);
    } else if (!strcmp(line, "cal erase")) {
        print_storage("erase", s_control.state == HAND_STATE_PERMITTED
                      ? PERSIST_ERR_WRITE : persist_erase());
    } else if (!strcmp(line, "cal corrupt")) {
        print_storage("corrupt", persist_corrupt_stored_crc());
    } else if (!strcmp(line, "reboot")) {
        printf("{\"type\":\"rebooting\"}\n");
        fflush(stdout);
        esp_restart();
    } else if (!strcmp(line, "link")) {
        struct hand_link_status link;
        hand_link_get_status(&link);
        printf("{\"type\":\"link\",\"side\":\"%s\",\"connected\":%d,\"subscribed\":%d,"
               "\"mtu\":%u,\"sent\":%" PRIu32 ",\"skipped\":%" PRIu32 ",\"connects\":%" PRIu32 "}\n",
               HAND_SIDE_NAME, link.connected ? 1 : 0, link.subscribed ? 1 : 0,
               (unsigned)link.mtu, link.sent, link.skipped, link.connects);
    } else if (!strcmp(line, "cal neutral")) {
        const enum calibration_result result = capture_neutral();
        printf("{\"type\":\"neutral\",\"result\":%d,\"reason\":\"%s\","
               "\"ratio\":[%d,%d,%d]}\n", (int)result, calibration_reason(result),
               s_calibration.neutral_ratio[0], s_calibration.neutral_ratio[1],
               s_calibration.neutral_ratio[2]);
    } else if (!strcmp(line, "cal finish")) {
        const enum calibration_result result = hand_calibration_finish(&s_calibration);
        printf("{\"type\":\"calibration\",\"result\":%d,\"reason\":\"%s\","
               "\"valid\":%d}\n", (int)result, calibration_reason(result),
               s_calibration.valid ? 1 : 0);
    } else if (!strncmp(line, "cal set ", 8)) {
        // Bench convenience: re-enter both ends from an earlier capture's means
        // (extended x5, then curled x5). Finish still validates them.
        int e[HAND_FLEX_COUNT], c[HAND_FLEX_COUNT];
        const int n = sscanf(line + 8, "%d %d %d %d %d %d %d %d %d %d",
                             &e[0], &e[1], &e[2], &e[3], &e[4], &c[0], &c[1], &c[2], &c[3], &c[4]);
        if (n != 2 * HAND_FLEX_COUNT || s_capture_active
                || s_control.state == HAND_STATE_PERMITTED) {
            printf("{\"type\":\"error\",\"op\":\"cal set\",\"reason\":\"%s\"}\n",
                   n != 2 * HAND_FLEX_COUNT ? "needs 10 values" : "busy");
        } else {
            for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
                s_calibration.flex[i].extended_raw = e[i];
                s_calibration.flex[i].curled_raw = c[i];
            }
            s_calibration.extended_captured = s_calibration.curled_captured = true;
            s_calibration.valid = false;
            printf("{\"type\":\"capture\",\"end\":\"set\",\"result\":0,\"reason\":\"ok\"}\n");
        }
    } else if (!strcmp(line, "cal reset")) {
        s_capture_active = false;
        hand_calibration_reset(&s_calibration, HAND_SIDE);
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
        printf("],\"neutral\":[%d,%d,%d],\"motion_captured\":%d}\n",
               s_calibration.neutral_ratio[0], s_calibration.neutral_ratio[1],
               s_calibration.neutral_ratio[2], s_calibration.motion_captured ? 1 : 0);
    } else if (sscanf(line, "stream %d %c", &count, &extra) == 1
               && count >= 0 && count <= 4096) {
        s_stream_remaining = count;
        printf("{\"type\":\"streaming\",\"count\":%d}\n", count);
    } else {
        printf("{\"type\":\"error\",\"op\":\"command\","
               "\"help\":\"info | sample | stats | control | stream N | stall MS | "
               "cal extended | cal curled | cal set E*5 C*5 | cal neutral | cal finish | cal reset | "
               "cal save | cal load | cal erase | cal corrupt | profile | "
               "link | reboot\"}\n");
    }
}

static void handle_command(const char *line)
{
    console_lock();
    handle_command_locked(line);
    console_unlock();
}

void app_main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    emit_boot();

    hand_calibration_reset(&s_calibration, HAND_SIDE);
    // Restore a stored profile if one survives; a rejected profile simply
    // leaves the hand uncalibrated rather than loading partial data.
    const bool storage_ready = persist_init() == ESP_OK;
    enum persist_status restore = PERSIST_ERR_UNAVAILABLE;
    if (storage_ready) {
        struct hand_calibration loaded;
        restore = persist_load(&loaded, (uint8_t)HAND_SIDE);
        if (restore == PERSIST_OK) {
            hand_calibration_finish(&loaded);
            s_calibration = loaded;
        }
    }
    hand_control_init(&s_control);
    // A fresh session per boot, so a hub cannot carry continuity across a
    // reset. Randomness quality is not qualified on this platform; uniqueness
    // across real power cycles must be confirmed at C5.
    s_session = esp_random();
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) s_curl_milli[i] = -1;
    esp_err_t status = hand_acquire_init(HAND_SIDE == HAND_SIDE_LEFT);
    if (status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"acquire_init\",\"status\":%d}\n", status);
        return;
    }
    // A missing or wrong sensor must not stop acquisition; it is reported as
    // a motion fault instead (FW-02).
    s_motion_available = motion_init() == ESP_OK;
    if (!s_motion_available) {
        printf("{\"type\":\"error\",\"op\":\"motion_init\"}\n");
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
    // The ESP32-S3 task watchdog is backed by the Timer Group watchdog. Its
    // timeout fires in simulation (S1-H). Bench builds leave trigger_panic off
    // so a trip is counted rather than resetting the chip; the panic and the
    // reset after a trip are tested on hardware only (test plan B2).
    // The feed discipline is verified through the feed counter.
    // PRODUCTION MUST ENABLE trigger_panic.
    const esp_task_wdt_config_t watchdog = {
        .timeout_ms = WATCHDOG_TIMEOUT_MS,
        .idle_core_mask = 0,
        .trigger_panic = false,
    };
    esp_err_t watchdog_status = esp_task_wdt_reconfigure(&watchdog);
    if (watchdog_status == ESP_ERR_INVALID_STATE) {
        watchdog_status = esp_task_wdt_init(&watchdog);
    }
    if (watchdog_status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"watchdog_init\",\"status\":%d}\n",
               watchdog_status);
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
    print_storage("restore", restore);
    // A radio failure is reported, not fatal: the hand still works over UART.
    status = storage_ready ? hand_link_start(HAND_SIDE, on_link_command) : ESP_ERR_INVALID_STATE;
    if (status != ESP_OK) {
        printf("{\"type\":\"error\",\"op\":\"link_start\",\"status\":%d}\n", status);
    }
    printf("{\"type\":\"ready\",\"side\":%u,\"name\":\"%s\"}\n", HAND_SIDE, HAND_SIDE_NAME);

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
