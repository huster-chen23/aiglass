"""
test_gtp.py — GTP/1.0 单元测试（无外部依赖，直接运行）
覆盖：编解码往返 / CRC 篡改检出 / 长度篡改检出 / 版本错 / 节流器行为
"""

import time

import gtp


def test_roundtrip():
    f = gtp.pack(gtp.TYPE_HR, b"\x84", seq=3)
    d = gtp.unpack(f)
    assert d["type"] == gtp.TYPE_HR and d["payload"] == b"\x84"
    assert d["seq"] == 3 and d["type_name"] == "HR"
    print("[PASS] 编解码往返")


def test_crc_tamper():
    f = bytearray(gtp.encode_hr(120))
    f[5] ^= 0xFF  # 篡改 payload
    try:
        gtp.unpack(bytes(f))
        raise AssertionError("篡改帧未被检出")
    except gtp.GTPError as e:
        assert "CRC" in str(e)
    print("[PASS] CRC 篡改检出")


def test_len_tamper():
    import struct
    f = bytearray(gtp.encode_hr(120))
    f[6] ^= 0x01  # 篡改长度字段低字节（头部 meta0/meta1 之后第 5-6 字节）
    # 情形1：直接篡改 → CRC 先检出
    try:
        gtp.unpack(bytes(f))
        raise AssertionError("篡改帧未被检出")
    except gtp.GTPError as e:
        assert "CRC" in str(e) or "长度" in str(e)
    # 情形2：攻击者重算合法 CRC 绕过 → 长度校验必须兜底
    data = bytes(f[:-2])
    fixed = data + struct.pack("!H", gtp.crc16(data))
    try:
        gtp.unpack(fixed)
        raise AssertionError("长度不一致未被检出")
    except gtp.GTPError as e:
        assert "长度" in str(e)
    print("[PASS] 长度篡改检出（CRC 拦截 + 长度校验兜底）")


def test_version():
    import struct
    f = bytearray(gtp.encode_hr(120))
    f[0] = (2 << 6) | gtp.TYPE_HR  # 伪造 ver=2
    data = bytes(f[:-2])
    f2 = data + struct.pack("!H", gtp.crc16(data))  # 重算 CRC 绕过校验
    try:
        gtp.unpack(f2)
        raise AssertionError("版本错误未被检出")
    except gtp.GTPError as e:
        assert "版本" in str(e)
    print("[PASS] 版本错检出")


def test_text():
    f = gtp.pack(gtp.TYPE_TEXT, "支援，我在垭口".encode("utf-8"))
    d = gtp.unpack(f)
    assert d["payload"].decode("utf-8") == "支援，我在垭口"
    print("[PASS] 中文 TEXT 往返")


def test_throttle():
    th = gtp.DeltaThrottle(min_delta=2, max_interval=0.3)
    now = 1000.0
    assert th.should_send(100, now) is True            # 首次必发
    assert th.should_send(101, now + 0.1) is False     # 变化<2 且未到期
    assert th.should_send(110, now + 0.2) is True      # 变化≥2 立即发
    assert th.should_send(110, now + 0.25) is False    # 刚发过
    assert th.should_send(110, now + 0.55) is True     # 0.3s 兜底到期
    assert th.should_send(110, now + 0.6) is False     # 又进入静默期
    print("[PASS] 增量节流器")


def test_hr_range():
    try:
        gtp.encode_hr(300)
        raise AssertionError("越界 bpm 未被拒绝")
    except ValueError:
        print("[PASS] bpm 越界拒绝")


if __name__ == "__main__":
    test_roundtrip()
    test_crc_tamper()
    test_len_tamper()
    test_version()
    test_text()
    test_throttle()
    test_hr_range()
    print("\n全部通过 [OK]")