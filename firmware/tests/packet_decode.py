#!/usr/bin/env python3
"""Independent decoder for the hand -> hub packet (FW-04), shared by S1-G and the bench.

Written from the layout in packet.h, not from the firmware's own encoder, so a
passing round trip means the contract is interoperable rather than two copies of
the same code agreeing.

Bench use: paste the hex from a hand's `packet` reply.

    python3 firmware/tests/packet_decode.py 013b00...
"""
import json
import struct
import sys
import zlib

PACKET_SIZE, PACKET_VERSION = 59, 1
(FLAG_VALID, FLAG_ENABLE, FLAG_CALIBRATED, FLAG_HOLD,
 FLAG_PRECISION, FLAG_MOTION_OK, FLAG_USB_POWER) = (1 << i for i in range(7))
FLAG_NAMES = ["valid", "enable", "calibrated", "hold", "precision", "motion_ok", "usb_power"]


def decode(raw: bytes) -> dict:
    """Framing is checked before any field is read."""
    if len(raw) != PACKET_SIZE:
        raise ValueError(f"wrong length {len(raw)}")
    if raw[0] != PACKET_VERSION:
        raise ValueError(f"wrong version {raw[0]}")
    if raw[1] != PACKET_SIZE:
        raise ValueError(f"declared length {raw[1]} != {PACKET_SIZE}")
    crc = struct.unpack_from("<I", raw, 55)[0]
    if zlib.crc32(raw[:55]) & 0xFFFFFFFF != crc:
        raise ValueError("CRC mismatch")
    side, state, fault = raw[2], raw[3], raw[4]
    flags, session, sequence, acquisition = struct.unpack_from("<HIII", raw, 5)
    (timestamp,) = struct.unpack_from("<q", raw, 19)
    curl = list(struct.unpack_from("<5h", raw, 27))
    accel = list(struct.unpack_from("<3h", raw, 37))
    gyro = list(struct.unpack_from("<3h", raw, 43))
    roll, pitch, throttle = struct.unpack_from("<3h", raw, 49)
    return dict(side=side, state=state, fault=fault, flags=flags, session=session,
                sequence=sequence, acquisition=acquisition, timestamp=timestamp,
                curl=curl, accel=accel, gyro=gyro, roll=roll, pitch=pitch,
                throttle=throttle)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        packet = decode(bytes.fromhex(sys.argv[1]))
    except ValueError as error:
        sys.exit(f"REJECTED: {error}")
    packet["flag_names"] = [n for i, n in enumerate(FLAG_NAMES) if packet["flags"] & (1 << i)]
    print(json.dumps(packet))
