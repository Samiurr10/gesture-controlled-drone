"""The computer-side link from the hub's command stream to the drone.

The hub prints one command per 20 ms (roll, pitch, yaw in [-1000, 1000],
throttle in [0, 1000], valid). This module turns the latest one into RC
channels, and `gcs_peer.py` sends them to ArduCopter as MAVLink
RC_CHANNELS_OVERRIDE on its telemetry port, as a ground station would. The peer
also records what ArduCopter reports back (RC_CHANNELS, HEARTBEAT). A test
sets `channels` and `failsafe`; the peer reads them each tick, as the I2C
fixtures read imu_state.

PROVISIONAL mapping, AETR order (ArduPilot's default RCMAP):
  ch1 roll, ch2 pitch, ch3 throttle, ch4 yaw: 1000..2000 us, 1500 centre.
  Pitch forward (+) is a LOW ch2, as on a Mode 2 transmitter.
  ch5 flight mode: fixed at 1500 us.
An invalid command stops the overrides, and so does no fresh command for
EXPIRY_TICKS peer ticks (100 ms): the expiry is the receiver's own, so a hub
that freezes without a final invalid message cannot hold the sticks. ArduCopter's
RC failsafe then takes over.
"""

CENTRE_US, MIN_US, MAX_US = 1500, 1000, 2000
CHANNELS = 8

channels = [CENTRE_US] * CHANNELS
channels[2] = MIN_US                 # throttle low
failsafe = True                      # until a valid command arrives
overrides_sent = 0
commands_seen = 0
ticks_since_command = 0              # advanced by gcs_peer every 20 ms
EXPIRY_TICKS = 5

# What ArduCopter reports, filled in by gcs_peer.
rc_reported = None                   # last RC_CHANNELS chan1..8, microseconds
heartbeat = None                     # last HEARTBEAT: dict of type, base_mode, custom_mode, system_status
heartbeats = 0
latest = {}                          # last message of each type ArduCopter sent
statustext = []                      # (time_s, severity, text), in order
acks = []                            # (time_s, command, result)
params = []                          # PARAM_VALUE replies
outbox = []                          # messages a test queues for the peer to send


def reset() -> None:
    global failsafe, overrides_sent, commands_seen, ticks_since_command
    global rc_reported, heartbeat, heartbeats
    for log in (latest, statustext, acks, params, outbox):
        log.clear()
    channels[:] = [CENTRE_US] * CHANNELS
    channels[2] = MIN_US
    failsafe, overrides_sent, commands_seen, ticks_since_command = True, 0, 0, 0
    rc_reported, heartbeat, heartbeats = None, None, 0


def _axis(milli: int) -> int:
    return CENTRE_US + milli * (MAX_US - CENTRE_US) // 1000


def expired() -> bool:
    return ticks_since_command > EXPIRY_TICKS


def apply_command(command: dict | None) -> None:
    """Updates the channels from one hub `command` record (or None)."""
    global failsafe, commands_seen, ticks_since_command
    commands_seen += 1
    ticks_since_command = 0
    if not command or not command.get("valid"):
        failsafe = True
        channels[2] = MIN_US
        return
    failsafe = False
    channels[0] = _axis(command["roll"])
    channels[1] = _axis(-command["pitch"])
    channels[2] = MIN_US + command["throttle"] * (MAX_US - MIN_US) // 1000
    channels[3] = _axis(command["yaw"])
    channels[4] = CENTRE_US
