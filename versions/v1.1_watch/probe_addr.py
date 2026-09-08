"""
probe_addr.py — 定向监听已知手表地址是否发出任何广播（含不可连接包）。
若捕获到广播，立即尝试按设备对象连接并订阅心率。
"""

import asyncio
import sys

from bleak import BleakScanner, BleakClient

TARGET = "5C:D8:9E:6A:F0:16"
HR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


async def main():
    seen = asyncio.Event()
    device_holder = {}

    def cb(d, adv):
        if d.address.upper() == TARGET:
            device_holder["dev"] = d
            if not seen.is_set():
                seen.set()
                print("[捕获] 手表广播出现！名称=%r RSSI=%d"
                      % (d.name, adv.rssi))

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    print("定向监听 %s 共 30 秒 ..." % TARGET)
    try:
        await asyncio.wait_for(seen.wait(), timeout=30)
    except asyncio.TimeoutError:
        await scanner.stop()
        print("30 秒内未见到任何广播 —— 手表绑定手机后完全隐身，实锤。")
        return
    # 看到广播：持续监听再收 5 秒多包，然后停扫描保持设备对象
    await asyncio.sleep(5)
    await scanner.stop()
    dev = device_holder["dev"]
    print("尝试按设备对象直接连接并订阅心率 ...")
    try:
        async with BleakClient(dev, timeout=10) as client:
            print("已连接！订阅心率（若手表测量未激活可能无推送，Ctrl+C 退出）")
            await client.start_notify(
                HR_UUID,
                lambda _c, d: print("心率:", d.hex(), "->",
                                    (d[1] if not d[0] & 1 else
                                     int.from_bytes(d[1:3], "little")), "bpm"))
            while client.is_connected:
                await asyncio.sleep(1)
    except Exception as e:
        print("连接失败:", e)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())