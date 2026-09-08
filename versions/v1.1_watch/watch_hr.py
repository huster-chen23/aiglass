"""
watch_hr.py — v1.1 手表遥测主程序
把华为 GT5 的心率/电量经 GTP/1.0 编解码后显示到控制台面板。

模式：
  --sim                模拟心率源（无需手表，验证 GTP 全链路）
  --address XX:XX:..   直连手表（先运行 ble_scan.py 找地址）
  --seconds N          sim 模式运行秒数（默认一直运行）

示例：
  py watch_hr.py --sim
  py watch_hr.py --address XX:XX:XX:XX:XX:XX
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gtp  # noqa: E402

HR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"   # 心率测量
BATT_UUID = "00002a19-0000-1000-8000-00805f9b34fb"  # 电池电量


class Panel:
    """简易控制台面板。"""

    def __init__(self):
        self.lines = []
        self.stats = {"frames": 0, "crc_err": 0, "throttled": 0}

    def update(self, hr=None, batt=None):
        self.lines.clear()
        if hr is not None:
            mark = " !!" if hr >= 150 or (0 < hr <= 45) else ""
            self.lines.append("心率: %3d bpm%s" % (hr, mark))
        if batt is not None:
            self.lines.append("电量: %3d %%" % batt)
        self.lines.append("GTP 帧: %d | CRC错: %d | 节流跳过: %d"
                           % (self.stats["frames"], self.stats["crc_err"],
                              self.stats["throttled"]))
        print("\n".join(self.lines))


def sim_loop(seconds, min_delta=2, max_interval=5.0):
    """模拟手表：生成带噪声的心率 + 固定电量，走完整 GTP 编解码管线。"""
    import math
    import random

    panel = Panel()
    throttle = gtp.DeltaThrottle(min_delta=min_delta,
                                 max_interval=max_interval)
    batt_throttle = gtp.DeltaThrottle(min_delta=1, max_interval=30)
    deadline = time.time() + (seconds or 1e9)
    t = 0.0
    batt = 84
    while time.time() < deadline:
        t = int(t + 1)
        # 模拟：慢跑心率 100~150，随机抖动
        hr = int(120 + 30 * math.sin(t / 12) + random.randint(-3, 3))
        if random.random() < 0.02:
            hr = min(178, hr + 25)  # 偶发冲刺

        if throttle.should_send(hr):
            frame = gtp.encode_hr(hr, seq=t & 0xF)
            try:
                bpm = gtp.decode_hr(frame)
                panel.stats["frames"] += 1
                panel.update(hr=bpm, batt=batt)
            except gtp.GTPError as e:
                panel.stats["crc_err"] += 1
                print("[GTPError]", e)
        else:
            panel.stats["throttled"] += 1
            panel.update(hr=hr)  # 显示真值，但标注未发送
            print("\r(节流) 真实心率 %d —— 变化未达阈值，不发包" % hr)

        if t % 30 == 0:
            batt = max(10, batt - 1)
            if batt_throttle.should_send(batt):
                frame = gtp.encode_batt(batt)
                d = gtp.unpack(frame)
                panel.stats["frames"] += 1
                panel.update(hr=hr, batt=d["payload"][0])
        time.sleep(1.0)
    print("\nSIM 结束。统计:", panel.stats)


def watch_loop(address, min_delta=2, max_interval=5.0):
    """真实模式：bleak 连接手表，订阅标准心率/电池服务。"""
    import asyncio

    async def run():
        from bleak import BleakClient

        panel = Panel()
        throttle = gtp.DeltaThrottle(min_delta=min_delta,
                                     max_interval=max_interval)
        stop = asyncio.Event()

        def on_hr(_char, data: bytearray):
            flags = data[0]
            bpm = (int.from_bytes(data[1:3], "little") if flags & 1
                   else data[1])
            frame = gtp.encode_hr(bpm)
            try:
                gtp.unpack(frame)
                panel.stats["frames"] += 1
            except gtp.GTPError:
                panel.stats["crc_err"] += 1
            panel.update(hr=bpm)

        def on_batt(_char, data: bytearray):
            panel.update(batt=data[0])

        async with BleakClient(address, timeout=15) as client:
            print("已连接:", address)
            await client.start_notify(HR_UUID, on_hr)
            try:
                batt = await client.read_gatt_char(BATT_UUID)
                panel.update(batt=batt[0])
                await client.start_notify(BATT_UUID, on_batt)
            except Exception as e:
                print("[电量] 不可用:", e)
            print("订阅完成，实时显示中（Ctrl+C 断开）")
            await stop.wait()

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n已断开。")


def main():
    ap = argparse.ArgumentParser(description="v1.1 手表遥测（GTP/1.0）")
    ap.add_argument("--sim", action="store_true", help="模拟模式（无需手表）")
    ap.add_argument("--address", help="手表 MAC 地址（真实模式）")
    ap.add_argument("--seconds", type=float, default=None,
                    help="sim 模式运行秒数")
    ap.add_argument("--min-delta", type=int, default=2,
                    help="心率增量阈值（变化小于此值不发包）")
    ap.add_argument("--max-interval", type=float, default=5.0,
                    help="静默期兜底发送间隔（秒）")
    args = ap.parse_args()

    print("GTP/1.0 | 帧头 %d B | 最大载荷 %d B"
          % (gtp.HEADER.size, gtp.MAX_PAYLOAD))
    if args.sim:
        sim_loop(args.seconds, args.min_delta, args.max_interval)
    elif args.address:
        watch_loop(args.address, args.min_delta, args.max_interval)
    else:
        ap.print_help()
        print("\n提示：手表在充电？先用 --sim 验证整条 GTP 管线。")


if __name__ == "__main__":
    main()