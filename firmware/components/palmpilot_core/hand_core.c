// SPDX-License-Identifier: MIT
#include "hand_core.h"

enum flex_status hand_classify_flex(int raw)
{
    if (raw < 0) return FLEX_FAULT_OPEN;            // failed conversion
    if (raw <= FLEX_RAW_OPEN_BELOW) return FLEX_FAULT_OPEN;
    if (raw >= FLEX_RAW_SHORT_ABOVE) return FLEX_FAULT_SHORT;
    return FLEX_OK;
}

uint32_t hand_fault_mask(const struct flex_channel *flex, int count)
{
    uint32_t mask = 0;
    for (int i = 0; i < count; ++i) {
        if (flex[i].status != FLEX_OK) mask |= (uint32_t)1 << i;
    }
    return mask;
}

bool hand_sample_healthy(const struct hand_sample *sample)
{
    return sample->fault_mask == 0;
}

void debounce_init(struct debounce *d, int stable_required, bool initial)
{
    d->level = initial;
    d->candidate = initial;
    d->count = 0;
    d->stable_required = stable_required > 0 ? stable_required : 1;
}

bool debounce_update(struct debounce *d, bool observation)
{
    if (observation != d->candidate) {
        d->candidate = observation;
        d->count = 1;
    } else if (d->candidate != d->level) {
        if (++d->count >= d->stable_required) d->level = d->candidate;
    }
    return d->level;
}

// --- calibration -----------------------------------------------------------

void capture_reset(struct capture_accumulator *a)
{
    a->count = 0;
    a->total = 0;
    a->minimum = HAND_ADC_MAX_RAW;
    a->maximum = 0;
}

void capture_add(struct capture_accumulator *a, int raw)
{
    if (raw < 0) return;
    a->total += raw;
    ++a->count;
    if (raw < a->minimum) a->minimum = raw;
    if (raw > a->maximum) a->maximum = raw;
}

int capture_mean(const struct capture_accumulator *a)
{
    return a->count ? (int)(a->total / a->count) : -1;
}

int capture_spread(const struct capture_accumulator *a)
{
    return a->count ? a->maximum - a->minimum : HAND_ADC_MAX_RAW;
}

void hand_calibration_reset(struct hand_calibration *c, enum hand_side side)
{
    c->version = HAND_CALIBRATION_VERSION;
    c->side = (uint8_t)side;
    c->extended_captured = false;
    c->curled_captured = false;
    c->motion_captured = false;
    c->valid = false;
    for (int axis = 0; axis < 3; ++axis) c->neutral_ratio[axis] = 0;
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        c->flex[i].extended_raw = -1;
        c->flex[i].curled_raw = -1;
    }
}

enum calibration_result hand_calibration_store(
    struct hand_calibration *c, bool extended,
    const struct capture_accumulator *accumulators, uint32_t fault_mask)
{
    // A capture taken while any channel is faulted is rejected whole: a bad
    // channel must not be frozen into a profile that later looks valid.
    if (fault_mask) return CALIBRATION_ERR_FAULT;
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        if (accumulators[i].count < HAND_CALIBRATION_SAMPLES) {
            return CALIBRATION_ERR_INCOMPLETE;
        }
        if (capture_spread(&accumulators[i]) > HAND_MAX_CAPTURE_SPREAD_RAW) {
            return CALIBRATION_ERR_UNSTABLE;
        }
    }
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        const int mean = capture_mean(&accumulators[i]);
        if (extended) c->flex[i].extended_raw = mean;
        else c->flex[i].curled_raw = mean;
    }
    if (extended) c->extended_captured = true;
    else c->curled_captured = true;
    c->valid = false;      // revalidate through hand_calibration_finish
    return CALIBRATION_OK;
}

enum calibration_result hand_calibration_finish(struct hand_calibration *c)
{
    c->valid = false;
    if (!c->extended_captured || !c->curled_captured || !c->motion_captured) {
        return CALIBRATION_ERR_INCOMPLETE;
    }
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        const int travel = c->flex[i].extended_raw - c->flex[i].curled_raw;
        // Extended must read higher than curled; the opposite means the sensor
        // is wired backwards or the two ends were captured in the wrong order.
        if (travel <= 0) return CALIBRATION_ERR_INVERTED;
        if (travel < HAND_MIN_TRAVEL_RAW) return CALIBRATION_ERR_TRAVEL;
    }
    c->valid = true;
    return CALIBRATION_OK;
}

int hand_curl_milli(const struct hand_calibration *c, int index, int raw)
{
    if (!c->valid || index < 0 || index >= HAND_FLEX_COUNT || raw < 0) return -1;
    const struct flex_calibration *f = &c->flex[index];
    const int travel = f->extended_raw - f->curled_raw;
    if (travel <= 0) return -1;

    // Integer only: no Xtensa FPU instruction may be emitted on this path.
    long curl = (long)(f->extended_raw - raw) * HAND_MILLI / travel;
    if (curl < 0) curl = 0;
    if (curl > HAND_MILLI) curl = HAND_MILLI;

    // Deadband at the extended end, rescaled so full curl still reaches 1000.
    if (curl <= HAND_CURL_DEADBAND_MILLI) return 0;
    return (int)((curl - HAND_CURL_DEADBAND_MILLI) * HAND_MILLI
                 / (HAND_MILLI - HAND_CURL_DEADBAND_MILLI));
}

// --- gesture mapping -------------------------------------------------------

int hand_throttle_milli(const int *curl_milli)
{
    long total = 0;
    // The thumb is excluded: it carries PRECISION, not throttle.
    for (int i = FINGER_INDEX; i <= FINGER_LITTLE; ++i) {
        if (curl_milli[i] < 0) return -1;
        total += curl_milli[i];
    }
    return (int)(total / 4);
}

bool hand_hold_gesture(const int *curl_milli)
{
    for (int i = 0; i < HAND_FLEX_COUNT; ++i) {
        if (curl_milli[i] < HAND_HOLD_CURL_MILLI) return false;
    }
    return true;
}

bool hand_precision_gesture(const int *curl_milli)
{
    return curl_milli[FINGER_THUMB] >= HAND_PRECISION_CURL_MILLI;
}

// --- control state machine -------------------------------------------------

void hand_control_init(struct hand_control *c)
{
    c->state = HAND_STATE_SELFTEST;
    c->fault = HAND_FAULT_NONE;
    c->inhibit = HAND_INHIBIT_NO_PRESS;
    // Assume pressed, so a button held through boot produces no rising edge
    // until it is released and pressed again (FW-03, CTRL-030).
    c->previous_enable = true;
    c->refusal = HAND_INHIBIT_NONE;
    c->command_valid = false;
}

void hand_control_update(struct hand_control *c, const struct hand_inputs *in)
{
    const bool rising = in->enable && !c->previous_enable;
    c->previous_enable = in->enable;
    if (!in->enable) c->refusal = HAND_INHIBIT_NONE;   // a release clears it
    c->command_valid = false;
    c->inhibit = HAND_INHIBIT_NONE;

    // Before the first sweep there is nothing to judge. Absence of data at
    // startup is not a sensor fault, and must not latch one.
    if (!in->started) {
        c->state = HAND_STATE_SELFTEST;
        c->fault = HAND_FAULT_NONE;
        c->inhibit = HAND_INHIBIT_NO_PRESS;
        return;
    }

    // Faults are evaluated next and latch: nothing below can override them.
    enum hand_fault_reason fault = HAND_FAULT_NONE;
    if (!in->healthy) fault = HAND_FAULT_SENSOR;
    else if (!in->motion_ok) fault = HAND_FAULT_MOTION;
    else if (!in->fresh) fault = HAND_FAULT_STALE;

    if (fault != HAND_FAULT_NONE) {
        c->state = HAND_STATE_FAULT;
        c->fault = fault;
        c->inhibit = HAND_INHIBIT_FAULT;
        return;
    }

    switch (c->state) {
    case HAND_STATE_FAULT:
        // Inputs are healthy again, but a recovered stream is not consent.
        c->state = HAND_STATE_RECOVERY;
        c->inhibit = HAND_INHIBIT_FAULT;
        break;
    case HAND_STATE_RECOVERY:
        // Leaving recovery requires an actual release, not merely good data.
        if (!in->enable) {
            c->state = HAND_STATE_WAITING;
            c->fault = HAND_FAULT_NONE;
        }
        c->inhibit = HAND_INHIBIT_FAULT;
        break;
    case HAND_STATE_SELFTEST:
        if (in->calibrated) c->state = HAND_STATE_WAITING;
        c->inhibit = HAND_INHIBIT_NO_PRESS;
        break;
    case HAND_STATE_SERVICE:
        if (!in->calibrating) c->state = HAND_STATE_WAITING;
        c->inhibit = HAND_INHIBIT_CALIBRATING;
        break;
    case HAND_STATE_WAITING:
    case HAND_STATE_PERMITTED:
        break;
    }

    if (c->state == HAND_STATE_FAULT || c->state == HAND_STATE_RECOVERY) return;

    // Calibration always wins over control: it never emits valid commands.
    if (in->calibrating) {
        c->state = HAND_STATE_SERVICE;
        c->inhibit = HAND_INHIBIT_CALIBRATING;
        return;
    }
    if (!in->calibrated) {
        c->state = HAND_STATE_SELFTEST;
        c->fault = HAND_FAULT_UNCALIBRATED;
        c->inhibit = HAND_INHIBIT_NO_PRESS;
        return;
    }
    c->fault = HAND_FAULT_NONE;

    if (c->state == HAND_STATE_PERMITTED) {
        if (!in->enable) {
            c->state = HAND_STATE_WAITING;     // release always ends permission
            c->inhibit = HAND_INHIBIT_NO_PRESS;
            return;
        }
        c->command_valid = true;
        return;
    }

    // WAITING: only a new press can grant permission, and only with the
    // throttle low. Enabling with a closed fist must never be possible.
    if (!rising) {
        c->inhibit = c->refusal != HAND_INHIBIT_NONE ? c->refusal
                                                     : HAND_INHIBIT_NO_PRESS;
        return;
    }
    if (in->throttle_milli < 0 || in->throttle_milli > HAND_ARM_THROTTLE_MAX_MILLI) {
        c->refusal = HAND_INHIBIT_THROTTLE_HIGH;
        c->inhibit = HAND_INHIBIT_THROTTLE_HIGH;
        return;
    }
    c->refusal = HAND_INHIBIT_NONE;
    c->state = HAND_STATE_PERMITTED;
    c->command_valid = true;
}

// --- tilt ------------------------------------------------------------------

int32_t hand_isqrt(int64_t value)
{
    if (value <= 0) return 0;
    // Newton's method from a power-of-two seed; integer only, no FPU.
    int64_t guess = value, previous = 0;
    while (guess != previous) {
        previous = guess;
        guess = (guess + value / guess) / 2;
        if (guess <= 0) return 0;
    }
    return (int32_t)guess;
}

int hand_tilt_ratio_milli(const int16_t *accel, int axis)
{
    if (axis < 0 || axis > 2) return 0;
    int64_t sum = 0;
    for (int i = 0; i < 3; ++i) {
        sum += (int64_t)accel[i] * (int64_t)accel[i];
    }
    const int32_t magnitude = hand_isqrt(sum);
    // Free fall or a dead sensor gives no usable direction; report level
    // rather than inventing a tilt.
    if (magnitude < MOTION_MAGNITUDE_FLOOR) return 0;
    return (int)(((int64_t)accel[axis] * HAND_MILLI) / magnitude);
}

int hand_axis_command_milli(int ratio_milli, int neutral_milli)
{
    int delta = ratio_milli - neutral_milli;
    const int sign = delta < 0 ? -1 : 1;
    int magnitude = delta < 0 ? -delta : delta;

    if (magnitude <= HAND_TILT_DEADBAND_MILLI) return 0;
    magnitude -= HAND_TILT_DEADBAND_MILLI;

    const int span = HAND_TILT_SATURATION_MILLI - HAND_TILT_DEADBAND_MILLI;
    int command = span > 0 ? (int)(((long)magnitude * HAND_MILLI) / span) : 0;
    if (command > HAND_MILLI) command = HAND_MILLI;
    return sign * command;
}

int hand_slew(int current, int target, int max_step)
{
    if (max_step <= 0) return target;
    const int delta = target - current;
    if (delta > max_step) return current + max_step;
    if (delta < -max_step) return current - max_step;
    return target;
}

int hand_apply_precision(int command_milli, bool precision)
{
    if (!precision) return command_milli;
    return (int)(((long)command_milli * HAND_PRECISION_NUMERATOR)
                 / HAND_PRECISION_DENOMINATOR);
}

enum calibration_result hand_calibration_store_neutral(
    struct hand_calibration *c, const int16_t *accel)
{
    int64_t sum = 0;
    for (int i = 0; i < 3; ++i) {
        sum += (int64_t)accel[i] * (int64_t)accel[i];
    }
    const int32_t magnitude = hand_isqrt(sum);
    const int32_t expected = MOTION_ACCEL_LSB_PER_G;
    const int32_t tolerance = (int32_t)(((int64_t)expected
                                         * HAND_GRAVITY_TOLERANCE_MILLI) / HAND_MILLI);
    // A hand that is accelerating is not showing its resting orientation.
    if (magnitude < expected - tolerance || magnitude > expected + tolerance) {
        return CALIBRATION_ERR_UNSTABLE;
    }
    for (int axis = 0; axis < 3; ++axis) {
        c->neutral_ratio[axis] = hand_tilt_ratio_milli(accel, axis);
    }
    c->motion_captured = true;
    c->valid = false;              // revalidate through hand_calibration_finish
    return CALIBRATION_OK;
}
