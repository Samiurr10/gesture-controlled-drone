# The computer's MAVLink link to ArduCopter's telemetry port (SERIAL1), as a
# ScriptedUartPeer. Every 20 ms it sends rc_link's channels as
# RC_CHANNELS_OVERRIDE (system 255, ArduPilot's default SYSID_MYGCS), unless
# rc_link is in failsafe or its last command has expired. It asks for
# RC_CHANNELS at 10 Hz and records what ArduCopter reports back.
import rc_link
from pymavlink.dialects.v20 import ardupilotmega as mavlink

TICK_US = 20_000
TICKS_PER_SECOND = 50


class Peer:
    def __init__(self, ctx):
        self.ctx = ctx
        self.mav = mavlink.MAVLink(None, srcSystem=255, srcComponent=190)
        self.ticks = 0
        ctx.schedule_periodic(TICK_US)

    def send(self, message):
        self.ctx.send(bytes(message.pack(self.mav)))

    def on_timer(self):
        self.ticks += 1
        if self.ticks % TICKS_PER_SECOND == 1:
            self.send(self.mav.heartbeat_encode(mavlink.MAV_TYPE_GCS, mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0))
            if rc_link.rc_reported is None:
                self.send(self.mav.command_long_encode(
                    1, 1, mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                    mavlink.MAVLINK_MSG_ID_RC_CHANNELS, 100_000, 0, 0, 0, 0, 0))
        while rc_link.outbox:
            self.send(rc_link.outbox.pop(0)(self.mav))
        rc_link.ticks_since_command += 1
        if not rc_link.failsafe and not rc_link.expired():
            self.send(self.mav.rc_channels_override_encode(1, 1, *rc_link.channels, *([0] * 10)))
            rc_link.overrides_sent += 1

    def on_byte(self, b):
        message = self.mav.parse_char(bytes([b]))
        if message is None:
            return
        kind = message.get_type()
        now = self.ticks * TICK_US / 1e6
        if message.get_srcSystem() == 1:
            rc_link.latest[kind] = message
        if kind == "STATUSTEXT":
            rc_link.statustext.append((now, message.severity, message.text))
        elif kind == "PARAM_VALUE":
            rc_link.params.append(message)
        elif kind == "COMMAND_ACK":
            rc_link.acks.append((now, message.command, message.result))
        if kind == "RC_CHANNELS":
            rc_link.rc_reported = [getattr(message, f"chan{i}_raw") for i in range(1, 9)]
        elif kind == "HEARTBEAT" and message.get_srcSystem() == 1:
            rc_link.heartbeat = {"type": message.type, "base_mode": message.base_mode,
                                 "custom_mode": message.custom_mode,
                                 "system_status": message.system_status}
            rc_link.heartbeats += 1
