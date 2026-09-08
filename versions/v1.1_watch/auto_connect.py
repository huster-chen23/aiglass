"""
auto_connect.py — 抢连模式
连续扫描，一旦发现 GT5 广播立即连接并订阅心率（与手机抢连接窗口用）。
连上后手表与我们保持连接；心率实时打印。Ctrl+C 退出。
"""

import asyncio
import sys
import time

from bleak import BleakScanner, BleakClient

HR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATT_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
KEYWORDS = ("gt5", "gt 5", "huawei")


def parse_hr(data: bytearray) -> int:
    """按蓝牙心率测量规范解析（0x2A37）。"""
    if not data:
        return 0
    flags = data[0]
    return (int.from_bytes(data[1:3], "little") if flags & 1 else data[1])


def is_target(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in KEYWORDS)


async def run(seconds=None):
    stop = time.time() + (seconds or 1e9)
    attempts = 0
    while time.time() < stop:
        attempts += 1
        print("[扫描 %d] 寻找 GT5 广播 ..." % attempts, flush=True)
        found = await BleakScanner.discover(timeout=5, return_adv=True)
        hit = next(((d, adv) for d, adv in found.values()
                    if is_target(d.name)), None)
        if hit is None:
            continue
        d, adv = hit
        print("[命中] %s  %s  RSSI %d  → 立即连接 ..." % (d.name, d.address,
                                                          adv.rssi))
        try:
            async with BleakClient(d, timeout=12) as client:
                print("[成功] 已连接！手表现在属于电脑端，心率实时显示中")
                print("=" * 46)

                # 服务探查：看手表到底暴露了什么
                for svc in client.services:
                    print("[服务]", svc.uuid, svc.description or "")
                    for ch in svc.characteristics:
                        props = ",".join(ch.properties)
                        print("    特征", ch.uuid, "(%s)" % props)

                # 主动读一次心率（很多手表返回最近一次测量值）
                try:
                    v = await client.read_gatt_char(HR_UUID)
                    print("[读取] 心率特征原始值:", v.hex(), "→", parse_hr(v), "bpm")
                except Exception as e:
                    print("[读取] 心率特征不可读:", e)

                def on_raw(tag):
                    def _cb(_c, data: bytearray):
                        print("[%s] raw: %s" % (tag, data.hex()))
                    return _cb

                await client.start_notify(HR_UUID, on_hr)
                await client.start_notify(BATT_UUID, on_batt)
                # 探查：华为私有通道 + 未知服务是否推数据
                try:
                    await client.start_notify("00004a02-0000-1000-8000-00805f9b34fb",
                                              on_raw("4A02"))
                except Exception:
                    pass
                try:
                    await client.start_notify("c551c36a-0377-4a29-9657-74ffb655a188",
                                              on_raw("C551"))
                except Exception:
                    pass

                # 操作引导倒计时
                print(">>> 请在手表上：忽略配对弹窗 → 打开“心率”App → 停留在测量界面")
                hints = ["现在：看一眼手表心率数字是否出现（30s）",
                         "现在：保持心率界面（30s）",
                         "现在：走动几下 看数值变化（30s）",
                         "现在：保持心率界面（30s）",
                         "最后 60s 持续接收中 ..."]
                for hint in hints:
                    if not client.is_connected or time.time() > stop:
                        break
                    print("[引导]", hint)
                    await asyncio.sleep(30)
                while client.is_connected and time.time() < stop:
                    await asyncio.sleep(1)
                print("[断开] 连接结束")
                return
        except Exception as e:
            print("[失败] %s —— 继续扫描重试 ..." % e)
            await asyncio.sleep(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    import argparse
    ap = argparse.ArgumentParser(description="GT5 抢连模式")
    ap.add_argument("--seconds", type=float, default=None,
                    help="总运行秒数（默认一直运行，Ctrl+C 退出）")
    a = ap.parse_args()
    try:
        asyncio.run(run(a.seconds))
    except KeyboardInterrupt:
        print("\n退出")
