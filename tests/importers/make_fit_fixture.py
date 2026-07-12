"""Generate a tiny, valid FIT file with one session message for test fixtures."""

import struct
import sys
from datetime import UTC, datetime

_CRC_TABLE = [
    0x0000,
    0xCC01,
    0xD801,
    0x1400,
    0xF001,
    0x3C00,
    0x2800,
    0xE401,
    0xA001,
    0x6C00,
    0x7800,
    0xB401,
    0x5000,
    0x9C01,
    0x8801,
    0x4400,
]
_FIT_EPOCH = 631065600  # 1989-12-31T00:00:00Z in unix seconds


def fit_crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[byte & 0xF]
        tmp = _CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ _CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def build(elapsed_s, distance_m, avg_hr, sport, start_dt):
    start_ts = int(start_dt.replace(tzinfo=UTC).timestamp()) - _FIT_EPOCH
    # session = global mesg 18; fields: start_time(2,uint32),
    # total_elapsed_time(7,scale1000), total_distance(9,scale100),
    # avg_heart_rate(16,uint8), sport(5,enum)
    fields = [(2, 4, 0x86), (7, 4, 0x86), (9, 4, 0x86), (16, 1, 0x02), (5, 1, 0x00)]
    defn = bytearray()
    defn.append(0x40)  # definition message, local type 0
    defn.append(0x00)  # reserved
    defn.append(0x00)  # architecture: little-endian
    defn += struct.pack("<H", 18)  # global message number: session
    defn.append(len(fields))
    for num, size, base in fields:
        defn += bytes([num, size, base])
    data = bytearray()
    data.append(0x00)  # data message, local type 0
    data += struct.pack("<I", start_ts)
    data += struct.pack("<I", round(elapsed_s * 1000))
    data += struct.pack("<I", round(distance_m * 100))
    data += struct.pack("<B", avg_hr)
    data += struct.pack("<B", sport)
    records = bytes(defn) + bytes(data)
    header = bytearray()
    header.append(12)  # header size
    header.append(0x10)  # protocol version 1.0
    header += struct.pack("<H", 2189)  # profile version
    header += struct.pack("<I", len(records))
    header += b".FIT"
    body = bytes(header) + records
    return body + struct.pack("<H", fit_crc(body))


if __name__ == "__main__":
    out = sys.argv[1]
    # sport 1 = running
    blob = build(
        elapsed_s=2730.0,
        distance_m=8000.0,
        avg_hr=152,
        sport=1,
        start_dt=datetime(2026, 6, 15, 7, 30, 0),
    )
    with open(out, "wb") as fh:
        fh.write(blob)
    print(f"wrote {len(blob)} bytes to {out}")
