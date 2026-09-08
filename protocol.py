"""
protocol.py — UDP 视频帧分片协议（与课程实践完全一致，独立副本便于项目自包含）

头部 20 字节大端: magic(2) frame_id(4) total(2) seq(2) payload_len(2) ts_ms(8)
"""

import struct

MAGIC = b"VR"
HEADER = struct.Struct("!2sIHHHQ")
HEADER_SIZE = HEADER.size  # 20

MAX_DATAGRAM = 60000
MAX_PAYLOAD = MAX_DATAGRAM - HEADER_SIZE


def make_header(frame_id, total, seq, payload_len, ts_ms):
    return HEADER.pack(MAGIC, frame_id, total, seq, payload_len, ts_ms)


def parse_header(datagram):
    if len(datagram) < HEADER_SIZE:
        return None
    magic, frame_id, total, seq, payload_len, ts_ms = HEADER.unpack(
        datagram[:HEADER_SIZE])
    if magic != MAGIC or total == 0 or seq >= total:
        return None
    if payload_len > len(datagram) - HEADER_SIZE:
        return None
    return frame_id, total, seq, payload_len, ts_ms


def fragment(frame_id, frame_bytes, ts_ms, max_datagram=MAX_DATAGRAM):
    max_payload = max_datagram - HEADER_SIZE
    total = (len(frame_bytes) + max_payload - 1) // max_payload
    for seq in range(total):
        start = seq * max_payload
        chunk = frame_bytes[start:start + max_payload]
        yield make_header(frame_id, total, seq, len(chunk), ts_ms) + chunk


def defragment(datagram):
    parsed = parse_header(datagram)
    if parsed is None:
        return None
    frame_id, total, seq, payload_len, ts_ms = parsed
    payload = datagram[HEADER_SIZE:HEADER_SIZE + payload_len]
    return frame_id, total, seq, payload_len, ts_ms, payload
