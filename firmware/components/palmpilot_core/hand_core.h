// SPDX-License-Identifier: MIT
// Pure controller logic: no ESP-IDF dependencies, so the same code can be
// exercised in host tests and in the MCU build (FW-01).
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "board.h"

// Mirrored from motion.h so this translation unit stays free of ESP-IDF
// headers and can be compiled in host tests.
#define MOTION_ACCEL_LSB_PER_G 16384
// Below this magnitude the gravity direction is meaningless (free fall, or a
// dead sensor reading zeros).
#define MOTION_MAGNITUDE_FLOOR 2000

// Flex channel health. A near-rail reading is a FAULT, never a command
// (FW-02, CTRL-011): an unplugged sensor is pulled toward GND through the
// 47 kOhm shunt, and a shorted one saturates at the local 3V3 rail.
enum flex_status {
    FLEX_OK = 0,
    FLEX_FAULT_OPEN = 1,      // near ground - disconnected or open circuit
    FLEX_FAULT_SHORT = 2,     // near rail - shorted to 3V3
};

// PROVISIONAL thresholds. The measured physical ground check returned raw 0-6
// at attenuation 3, so the open guard sits above that floor with margin. These
// are implementation starting points and are NOT qualified limits; C1/CTRL-011
// must measure real open, shorted and settled values before they are frozen.
#define FLEX_RAW_OPEN_BELOW 40
#define FLEX_RAW_SHORT_ABOVE 4040

struct flex_channel {
    int raw;
    int millivolts;
    enum flex_status status;
};

struct hand_sample {
    uint32_t acquisition;         // increments once per completed sweep
    int64_t timestamp_us;         // local monotonic, esp_timer clock
    struct flex_channel flex[HAND_FLEX_COUNT];
    bool enable_raw;              // debounced ENABLE, true = pressed (active low)
    uint32_t fault_mask;          // bit n set when flex[n].status != FLEX_OK
};

enum flex_status hand_classify_flex(int raw);
uint32_t hand_fault_mask(const struct flex_channel *flex, int count);
bool hand_sample_healthy(const struct hand_sample *sample);

// Debounce: requires `stable_required` consecutive identical observations
// before the reported level changes. 20 ms is the candidate in FW-02; the
// actual value must be measured (CTRL-030).
struct debounce {
    bool level;                   // debounced output
    bool candidate;
    int count;
    int stable_required;
};

void debounce_init(struct debounce *d, int stable_required, bool initial);
bool debounce_update(struct debounce *d, bool observation);

// ---------------------------------------------------------------------------
// Calibration (FW-03)
//
// The flex divider is 3V3 -> flex -> node, with 47 kOhm from node to GND.
// Bending raises the sensor's resistance, so the node voltage FALLS: an
// extended finger reads HIGH and a curled finger reads LOW.
// ---------------------------------------------------------------------------

#define HAND_CALIBRATION_VERSION 1
#define HAND_CALIBRATION_SAMPLES 32

// PROVISIONAL. Adafruit #1070 spans roughly 25 kOhm extended to 100 kOhm bent,
// which is about 1000 counts of travel through this divider, so a 200-count
// floor rejects a sensor that is barely moving. Spread guards against a capture
// taken while the hand was still moving. Neither is qualified; CTRL-022 must
// measure comfortable ranges on the real hand before these are frozen.
#define HAND_MIN_TRAVEL_RAW 200
#define HAND_MAX_CAPTURE_SPREAD_RAW 120

// All control arithmetic is fixed-point in milli-units (0..1000). This began as
// a workaround: engine 0.5.7 aborted on the first Xtensa FPU instruction, which
// no longer happens on 0.6.3.
// Integer math is also the better choice for a fixed-rate control loop.
#define HAND_MILLI 1000

// Travel ignored at the extended end, so a resting hand reads zero.
#define HAND_CURL_DEADBAND_MILLI 30

enum hand_side { HAND_SIDE_LEFT = 0, HAND_SIDE_RIGHT = 1 };

// ---------------------------------------------------------------------------
// Tilt (FW-05)
//
// Roll and pitch come from where gravity sits in the hand's frame, which has a
// fixed external reference and cannot drift. The magnetometer and integrated
// gyro yaw are deliberately excluded from the command path.
//
// The measure is sin(tilt angle), not the angle: the command is the gravity
// component along an axis divided by the measured gravity magnitude. That is
// monotonic in angle over the useful range, needs no trigonometry, and is
// independent of the accelerometer's scale factor. It is a control law, not an
// attitude estimate, and it is NOT linear in degrees.
// ---------------------------------------------------------------------------

// PROVISIONAL. sin(30 deg) and sin(3 deg) in milli-units; CTRL-051 must
// measure comfortable travel and real hand tremor before these are frozen.
#define HAND_TILT_SATURATION_MILLI 500
#define HAND_TILT_DEADBAND_MILLI 52

// A hand at rest reads one gravity. A magnitude far from that means the hand is
// accelerating, so the reading is not a pure tilt and neutral capture must be
// refused. PROVISIONAL +-20%.
#define HAND_GRAVITY_TOLERANCE_MILLI 200

// Slew limits per control update, from the candidate rates in the gesture
// mapping: 4.0/s attitude and 1.5/s throttle at a 20 ms control period.
#define HAND_SLEW_ATTITUDE_MILLI 80
#define HAND_SLEW_THROTTLE_MILLI 30

// PRECISION halves every axis.
#define HAND_PRECISION_NUMERATOR 1
#define HAND_PRECISION_DENOMINATOR 2

// Integer square root; accepts the sum of three squared int16 values.
int32_t hand_isqrt(int64_t value);

// Gravity component along `axis` (0=x, 1=y, 2=z) as a fraction of the measured
// magnitude, in milli-units. Returns 0 when the magnitude is unusable.
int hand_tilt_ratio_milli(const int16_t *accel, int axis);

// Deadband, scale to saturation and clamp to [-1000, 1000].
int hand_axis_command_milli(int ratio_milli, int neutral_milli);

// Moves `current` toward `target` by at most `max_step`.
int hand_slew(int current, int target, int max_step);

int hand_apply_precision(int command_milli, bool precision);

enum calibration_result {
    CALIBRATION_OK = 0,
    CALIBRATION_ERR_FAULT = 1,        // a channel faulted during capture
    CALIBRATION_ERR_UNSTABLE = 2,     // readings moved too much while capturing
    CALIBRATION_ERR_TRAVEL = 3,       // extended and curled are too close
    CALIBRATION_ERR_INVERTED = 4,     // curled read higher than extended
    CALIBRATION_ERR_INCOMPLETE = 5,   // an end was never captured
};

struct capture_accumulator {
    int count;
    long total;
    int minimum;
    int maximum;
};

struct flex_calibration {
    int extended_raw;
    int curled_raw;
};

struct hand_calibration {
    uint16_t version;
    uint8_t side;
    bool extended_captured;
    bool curled_captured;
    bool motion_captured;
    bool valid;
    struct flex_calibration flex[HAND_FLEX_COUNT];
    // Gravity ratios at the hand's resting orientation, in milli-units.
    int neutral_ratio[3];
};

// Captures the resting orientation. Refuses a hand that is moving, which a
// magnitude far from one gravity reveals.
enum calibration_result hand_calibration_store_neutral(
    struct hand_calibration *c, const int16_t *accel);

void capture_reset(struct capture_accumulator *a);
void capture_add(struct capture_accumulator *a, int raw);
int capture_mean(const struct capture_accumulator *a);
int capture_spread(const struct capture_accumulator *a);

void hand_calibration_reset(struct hand_calibration *c, enum hand_side side);

// Stores one captured end. `extended` selects which end is being recorded.
enum calibration_result hand_calibration_store(
    struct hand_calibration *c, bool extended,
    const struct capture_accumulator *accumulators, uint32_t fault_mask);

// Validates both ends together and sets `valid`.
enum calibration_result hand_calibration_finish(struct hand_calibration *c);

// Normalised curl in milli-units: 0 extended, 1000 fully curled. Returns -1
// when the channel has no usable calibration, so a caller cannot mistake it
// for zero travel.
int hand_curl_milli(const struct hand_calibration *c, int index, int raw);

// ---------------------------------------------------------------------------
// Gesture mapping and control state (FW-05, docs/gesture-mapping.md)
//
// Left hand: index+middle+ring+little mean curl = throttle; thumb = PRECISION.
// Right hand: all five curled = HOLD. (Bench profile: no thumb gestures.)
// All values are milli-units. No floating point - see the 2026-09-18 FPU record.
// ---------------------------------------------------------------------------

// Bench profile (CONFIG_PALMPILOT_BENCH, built as hand:left_bench, hand:right_bench
// and hub:bench): settings the first physical flights on 2026-11-17 used. The
// default build keeps the designed behaviour, which the simulation suites test;
// docs/bench-bringup.md records why each bench setting exists.
#ifndef PALMPILOT_BENCH
#define PALMPILOT_BENCH 0
#endif

// PROVISIONAL thresholds; CTRL-051 must measure these on a real hand.
#if PALMPILOT_BENCH
// The open left hand read up to ~17% curl on its saved calibration.
#define HAND_ARM_THROTTLE_MAX_MILLI 200   // enable refused above 20% throttle
#else
#define HAND_ARM_THROTTLE_MAX_MILLI 50    // enable refused above 5% throttle
#endif
// 1: ENABLE toggles (press on, press again off) instead of a held deadman.
// Losing a hand, a fault or a reset still ends permission.
#define HAND_ENABLE_LATCH PALMPILOT_BENCH
// 1: no thumb gestures. HOLD is index..little; PRECISION is never raised.
#define HAND_NO_THUMB_GESTURES PALMPILOT_BENCH
#define HAND_HOLD_CURL_MILLI 800          // all five fingers -> HOLD
#define HAND_PRECISION_CURL_MILLI 600     // left thumb -> PRECISION

enum hand_state {
    HAND_STATE_SELFTEST = 0,   // before drivers and calibration are ready
    HAND_STATE_SERVICE = 1,    // calibrating; output inhibited
    HAND_STATE_WAITING = 2,    // healthy and calibrated, awaiting a new press
    HAND_STATE_PERMITTED = 3,  // the only state that reports a valid command
    HAND_STATE_FAULT = 4,      // latched; needs healthy inputs to leave
    HAND_STATE_RECOVERY = 5,   // fault cleared, awaiting ENABLE release
};

enum hand_fault_reason {
    HAND_FAULT_NONE = 0,
    HAND_FAULT_SENSOR = 1,         // a flex channel is open or shorted
    HAND_FAULT_UNCALIBRATED = 2,   // no valid profile
    HAND_FAULT_STALE = 3,          // acquisition stopped progressing
    HAND_FAULT_MOTION = 4,         // motion module missing, wrong or silent
};

// Why a new ENABLE press was refused. Reported so a refusal is never silent.
enum hand_inhibit {
    HAND_INHIBIT_NONE = 0,
    HAND_INHIBIT_NO_PRESS = 1,        // waiting for release-then-press
    HAND_INHIBIT_THROTTLE_HIGH = 2,   // throttle above the arming limit
    HAND_INHIBIT_CALIBRATING = 3,
    HAND_INHIBIT_FAULT = 4,
};

struct hand_inputs {
    bool started;          // at least one sweep has completed
    bool healthy;          // no flex channel fault
    bool calibrated;       // valid profile
    bool calibrating;      // capture in progress
    bool motion_ok;        // accelerometer readable; required for attitude
    bool fresh;            // acquisition progressed since the last update
    bool enable;           // debounced ENABLE, true = pressed
    int throttle_milli;    // 0..1000, or -1 when uncalibrated
};

struct hand_control {
    enum hand_state state;
    enum hand_fault_reason fault;
    enum hand_inhibit inhibit;
    bool previous_enable;  // starts true so a button held at boot is inert
    // Why the last press was refused. Latched until ENABLE is released, so the
    // operator can still see the reason after the deciding instant has passed.
    enum hand_inhibit refusal;
    bool command_valid;
};

void hand_control_init(struct hand_control *c);
void hand_control_update(struct hand_control *c, const struct hand_inputs *in);

// Mean curl of index, middle, ring and little. Returns -1 if any is invalid.
int hand_throttle_milli(const int *curl_milli);
bool hand_hold_gesture(const int *curl_milli);
bool hand_precision_gesture(const int *curl_milli);
