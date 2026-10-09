// SPDX-License-Identifier: MIT
#include "hub_core.h"

#include <string.h>

#include "hand_core.h"

void hub_init(struct hub *hub)
{
    memset(hub, 0, sizeof(*hub));
    hub->await_release = true;       // a hand already enabled at hub boot must re-press
    hub->out.reason = HUB_LEFT_MISSING;
}

void hub_link_changed(struct hub *hub, int side, bool connected)
{
    if (side != HAND_SIDE_LEFT && side != HAND_SIDE_RIGHT) return;
    struct hub_hand *hand = &hub->hand[side];
    const struct hub_hand counters = *hand;
    memset(hand, 0, sizeof(*hand));
    hand->accepted = counters.accepted;
    hand->rejected_unlinked = counters.rejected_unlinked;
    hand->rejected_format = counters.rejected_format;
    hand->rejected_side = counters.rejected_side;
    hand->rejected_replay = counters.rejected_replay;
    hand->connected = connected;
}

bool hub_receive(struct hub *hub, int side, const uint8_t *data, size_t length,
                 int64_t now_us)
{
    if (side != HAND_SIDE_LEFT && side != HAND_SIDE_RIGHT) return false;
    struct hub_hand *hand = &hub->hand[side];
    struct hand_packet_source packet;
    if (!hand->connected) {
        ++hand->rejected_unlinked;
        return false;
    }
    if (!hand_packet_decode(data, length, &packet)) {
        ++hand->rejected_format;
        return false;
    }
    if (packet.side != side) {
        ++hand->rejected_side;
        return false;
    }
    if (hand->have_packet && packet.session == hand->packet.session
            && (int32_t)(packet.sequence - hand->packet.sequence) <= 0) {
        ++hand->rejected_replay;
        return false;
    }
    const bool new_session = !hand->have_packet
                             || packet.session != hand->packet.session;
    if (new_session || packet.acquisition != hand->packet.acquisition) {
        hand->progressed_us = now_us;
    }
    if (new_session && hand->have_packet) {
        hub->await_release = true;   // the hand rebooted
    }
    hand->packet = packet;
    hand->have_packet = true;
    hand->received_us = now_us;
    ++hand->accepted;
    return true;
}

// Link, freshness, progress and health; ENABLE is judged separately.
static enum hub_reason hand_problem(const struct hub_hand *hand, int side, int64_t now_us)
{
    const bool left = side == HAND_SIDE_LEFT;
    if (!hand->connected || !hand->have_packet) {
        return left ? HUB_LEFT_MISSING : HUB_RIGHT_MISSING;
    }
    if (now_us - hand->received_us > HUB_PACKET_MAX_AGE_US) {
        return left ? HUB_LEFT_STALE : HUB_RIGHT_STALE;
    }
    if (now_us - hand->progressed_us > HUB_PROGRESS_MAX_AGE_US) {
        return left ? HUB_LEFT_FROZEN : HUB_RIGHT_FROZEN;
    }
    const struct hand_packet_source *p = &hand->packet;
    const bool ready = p->fault == HAND_FAULT_NONE
                       && (p->state == HAND_STATE_WAITING || p->state == HAND_STATE_PERMITTED)
                       && (p->flags & HAND_FLAG_CALIBRATED)
                       && (p->flags & HAND_FLAG_MOTION_OK);
    if (!ready) return left ? HUB_LEFT_NOT_READY : HUB_RIGHT_NOT_READY;
    return HUB_OK;
}

static int clamp(int value, int low, int high)
{
    return value < low ? low : value > high ? high : value;
}

static int slew(int current, int target, int step, int low)
{
    return clamp(hand_slew(current, target, step), low, HAND_MILLI);
}

void hub_update(struct hub *hub, bool calibrating, int64_t now_us,
                struct hub_command *out)
{
    const struct hub_hand *left = &hub->hand[HAND_SIDE_LEFT];
    const struct hub_hand *right = &hub->hand[HAND_SIDE_RIGHT];

    enum hub_reason reason = hand_problem(left, HAND_SIDE_LEFT, now_us);
    if (reason == HUB_OK) reason = hand_problem(right, HAND_SIDE_RIGHT, now_us);
    if (reason == HUB_OK && calibrating) reason = HUB_CALIBRATING;

    const bool enable = reason == HUB_OK && (left->packet.flags & HAND_FLAG_ENABLE);
    const bool permitted = reason == HUB_OK && (left->packet.flags & HAND_FLAG_VALID);
    // The latch clears only on a release seen while both hands are healthy.
    if (hub->await_release && reason == HUB_OK && !enable) hub->await_release = false;
    if (reason == HUB_OK && !permitted) reason = HUB_NOT_ENABLED;
    if (reason == HUB_OK && hub->await_release) reason = HUB_AWAIT_RELEASE;

    struct hub_command *command = &hub->out;
    if (reason != HUB_OK) {
        if (hub->active) hub->await_release = true;
        hub->active = false;
        hub->was_holding = false;
        memset(command, 0, sizeof(*command));
        command->reason = reason;
        *out = *command;
        return;
    }
    hub->active = true;

    const struct hand_packet_source *l = &left->packet, *r = &right->packet;
    const bool hold = r->flags & HAND_FLAG_HOLD;
    const bool precision = l->flags & HAND_FLAG_PRECISION;

    int roll = r->roll_milli, pitch = r->pitch_milli, yaw = l->roll_milli;
    int throttle = clamp(l->throttle_milli, 0, HAND_MILLI);
    if (hold) {
        if (!hub->was_holding) hub->hold_throttle = command->throttle_milli;
        roll = pitch = yaw = 0;
        throttle = hub->hold_throttle;
    }
    hub->was_holding = hold;
    roll = hand_apply_precision(roll, precision);
    pitch = hand_apply_precision(pitch, precision);
    yaw = hand_apply_precision(yaw, precision);

    // Slew after mapping (interlock 6).
    command->roll_milli = slew(command->roll_milli, roll, HAND_SLEW_ATTITUDE_MILLI, -HAND_MILLI);
    command->pitch_milli = slew(command->pitch_milli, pitch, HAND_SLEW_ATTITUDE_MILLI, -HAND_MILLI);
    command->yaw_milli = slew(command->yaw_milli, yaw, HAND_SLEW_ATTITUDE_MILLI, -HAND_MILLI);
    command->throttle_milli = slew(command->throttle_milli, throttle, HAND_SLEW_THROTTLE_MILLI, 0);
    command->hold = hold;
    command->precision = precision;
    command->valid = true;
    command->reason = HUB_OK;
    *out = *command;
}

const char *hub_reason_name(enum hub_reason reason)
{
    switch (reason) {
    case HUB_OK: return "ok";
    case HUB_LEFT_MISSING: return "left_missing";
    case HUB_RIGHT_MISSING: return "right_missing";
    case HUB_LEFT_STALE: return "left_stale";
    case HUB_RIGHT_STALE: return "right_stale";
    case HUB_LEFT_FROZEN: return "left_frozen";
    case HUB_RIGHT_FROZEN: return "right_frozen";
    case HUB_LEFT_NOT_READY: return "left_not_ready";
    case HUB_RIGHT_NOT_READY: return "right_not_ready";
    case HUB_CALIBRATING: return "calibrating";
    case HUB_NOT_ENABLED: return "not_enabled";
    case HUB_AWAIT_RELEASE: return "await_release";
    }
    return "unknown";
}
