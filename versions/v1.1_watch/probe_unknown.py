"""
probe_unknown.py — 识别匿名 RPA 设备：连接信号最强的未知设备，检查是否暴露标准心率服务 0x180D。
手表保持在电脑附近、屏幕点亮、停在“请用运动健康配对”弹窗界面。
"""

import asyncio
import sys

from bleak import BleakScanner, BleakClient

HR_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"


async def main():
    print("扫描中（8 秒）...")
    found = await BleakScanner.discover(timeout=8, return_adv=True)
    # 无名称 + 信号强 = RPA 嫌疑设备
    cands = [(d, adv.rssi) for d, adv in found.values()
             if not d.name and adv.rssi > -75]
    cands.sort(key=lambda x: x[1], reverse=True)
    print("候选匿名设备 %d 台：" % len(cands))
    for d, rssi in cands[:6]:
        print("  %s  RSSI %d" % (d.address, rssi))

    for d, rssi in cands[:4]:
        print("\n[探测] %s (RSSI %d) ..." % (d.address, rssi))
        try:
            async with BleakClient(d, timeout=8) as client:
                svcs = client.services
                uuids = [s.uuid for s in svcs]
                has_hr = HR_SERVICE in uuids
                print("  服务数 %d | 心率服务 0x180D: %s"
                      % (len(svcs), "有 ★" if has_hr else "无"))
                for s in svcs:
                    print("    ", s.uuid, s.description or "")
                if has_hr:
                    print("\n[结论] %s 就是手表（RPA 地址）！后续用它连接订阅心率。"
                          % d.address)
        except Exception as e:
            print("  连接失败:", e)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())