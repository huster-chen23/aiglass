"""
gtp.py — GTP/1.0 Glasses Telemetry Protocol
============================================
自研遥测协议：眼镜端与手表/手机/对端眼镜之间的传感器数据帧格式。

帧结构（适配 BLE MTU 247，整帧 ≤ 214 字节）：
    ┌─────────┬─────────┬────────┬─────────┬──────────┬────────┐
    │ meta0   │ meta1   │ ts 4B  │ len 2B  │ payload  │ crc 2B │
    │ 1B      │ 1B      │        │         │ 0~200B   │        │
    └─────────┴─────────┴────────┴─────────┴──────────┴────────┘
    meta0 = (ver << 6) | type          ver 2bit 版本 / type 6bit 数据类型
    meta1 = (flags << 4) | seq         flags 4bit 标志 / seq 4bit 抗重窗口
    ts    = uint32 大端，Unix 秒
    len   = uint16 大端，payload 字节数
    crc   = CRC-16/MODBUS，覆盖 crc 之前的全部字节

设计点（答辩）：
  1. 增量上报：数值变化 < 阈值不发，静默期由上层节流器兜底定时发送
  2. 自适应节流：DeltaThrottle —— 变化立即发，静止期 max_interval 兜底
  3. 前向兼容：未知 type 直接丢弃不报错，新增传感器无需升协议版本
"""

import struct
import time

GTP_VER = 1

# 数据类型（6bit，0~63）
TYPE_HR = 0x01     # 心率，payload = 1 字节 bpm
TYPE_BATT = 0x02   # 电量，payload = 1 字节百分比
TYPE_STEPS = 0x03  # 步数，payload = 4 字节大端
TYPE_GPS = 0x04    # 坐标（v1.3）
TYPE_TEXT = 0x05   # 文本（UTF-8）
TYPE_VOICE = 0x06  # 语音分片（v1.3）

TYPE_NAMES = {TYPE_HR: "HR", TYPE_BATT: "BATT", TYPE_STEPS: "STEPS",
              TYPE_GPS: "GPS", TYPE_TEXT: "TEXT", TYPE_VOICE: "VOICE"}

FLAG_ACK_REQ = 0x1   # 需要确认（保留）
FLAG_ALARM = 0x2     # 告警消息（如心率超限）

HEADER = struct.Struct("!BBIH")   # meta0 1B, meta1 1B, ts 4B, len 2B
CRC_SIZE = 2
MAX_PAYLOAD = 200
FRAME_OVERHEAD = HEADER.size + CRC_SIZE


class GTPError(Exception):
    """帧非法（CRC 错/版本错/长度错）。"""


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/MODBUS（多项式 0xA001，初值 0xFFFF）。"""
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def pack(msg_type: int, payload: bytes = b"", seq: int = 0, flags: int = 0,
         ts: float | None = None) -> bytes:
    """编码一帧 GTP。"""
    if msg_type > 0x3F:
        raise ValueError("type 超出 6bit 范围")
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload 超过 %d 字节，请再分片" % MAX_PAYLOAD)
    ts = int((ts or time.time()) * 1) & 0xFFFFFFFF
    meta0 = (GTP_VER << 6) | msg_type
    meta1 = ((flags & 0xF) << 4) | (seq & 0xF)
    body = HEADER.pack(meta0, meta1, ts, len(payload)) + payload
    return body + struct.pack("!H", crc16(body))


def unpack(frame: bytes):
    """解码一帧 GTP。

    返回 dict：{type, type_name, flags, seq, ts, payload}
    非法帧抛出 GTPError。
    """
    if len(frame) < FRAME_OVERHEAD:
        raise GTPError("帧长不足")
    data, crc_stored = frame[:-CRC_SIZE], frame[-CRC_SIZE:]
    if crc16(data) != struct.unpack("!H", frame[-CRC_SIZE:])[0]:
        raise GTPError("CRC 校验失败")
    meta0, meta1, ts, length = HEADER.unpack(data[:HEADER.size])
    ver, msg_type = meta0 >> 6, meta0 & 0x3F
    payload = data[HEADER.size:]
    if ver != GTP_VER:
        raise GTPError("版本不匹配 ver=%d" % ver)
    if length != len(payload):
        raise GTPError("长度字段与实际不符")
    return {
        "type": msg_type,
        "type_name": TYPE_NAMES.get(msg_type, "UNK%02X" % msg_type),
        "flags": meta1 >> 4,
        "seq": meta1 & 0xF,
        "ts": ts,
        "payload": payload,
    }


# ---------- 便捷编解码 ----------
def encode_hr(bpm: int, **kw) -> bytes:
    if not 0 <= bpm <= 255:
        raise ValueError("bpm 超出 uint8")
    return pack(TYPE_HR, bytes([bpm]), **kw)


def decode_hr(frame: bytes) -> int:
    return unpack(frame)["payload"][0]


def encode_batt(pct: int, **kw) -> bytes:
    if not 0 <= pct <= 100:
        raise ValueError("pct 超出范围")
    return pack(TYPE_BATT, bytes([pct]), **kw)


class DeltaThrottle:
    """增量节流器：变化 ≥ min_delta 立即发；静止期 max_interval 秒兜底发一次。"""

    def __init__(self, min_delta=2, max_interval=5.0):
        self.min_delta = min_delta
        self.max_interval = max_interval
        self.last_value = None
        self.last_time = 0.0

    def should_send(self, value: float, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        due = now - self.last_time >= self.max_interval
        changed = (self.last_value is None
                   or abs(value - self.last_value) >= self.min_delta)
        if changed or due:
            self.last_value, self.last_time = value, now
            return True
        return False