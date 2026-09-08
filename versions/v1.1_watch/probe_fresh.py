"""
probe_fresh.py — 持续监听 15 秒收集匿名强信号设备，发现后立即用设备对象连接
（避免 RPA 地址轮换导致的“按地址找不到”问题），逐个检查是否暴露心率服务 0x180D。
"""

import asyncio
import sys

from bleak import BleakScanner, BleakClient

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"


async def main():
    cands = {}  # address -> device

    def cb(d, adv):
        if not d.name and adv.rssi > -75:
            cands[d.address] = d

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    print("持续监听 15 秒 ...")
    await asyncio.sleep(15)
    await scanner.stop()
    print("候选 %d 台，立即尝试连接最强的 3 台：" % len(cands))

    ok_any = False
    for d in list(cands.values())[:3]:
        print("\n[连接]", d.address, d.name)
        try:
            async with BleakClient(d, timeout=8) as client:
                svcs = client.services
                has_hr = HR_SERVICE in [x.uuid for x in svcs]
                print("  已连接 | 服务数 %d | 心率服务: %s"
                      % (len(svcs), "有 ★★" if has_hr else "无"))
                if has_hr:
                    ok_any = True
                    print("  [确认] 这就是手表！地址 %s" % d.address)
        except Exception as e:
            print("  连接失败:", e)

    print("\n结论:", "发现手表 RPA，可进入心率订阅" if ok_any
          else "匿名设备均非手表/无法连接 —— 华为配对广播为私有格式")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())