"""
ble_scan.py — BLE 设备扫描（v1.1 第一步）
手表充满电后运行：找到 GT5 的 MAC 地址，再用于 watch_hr.py --address
"""

import asyncio
import sys

from bleak import BleakScanner


async def main():
    print("扫描附近的 BLE 设备（10 秒）...\n")
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    rows = [(d, adv.rssi) for d, adv in found.values()]
    rows.sort(key=lambda x: x[1], reverse=True)
    print("%-32s %-18s %s" % ("名称", "地址", "RSSI"))
    print("-" * 62)
    for d, rssi in rows:
        name = d.name or "(未知)"
        mark = "  ← 疑似手表" if "watch" in name.lower() or "gt" in name.lower() else ""
        print("%-32s %-18s %4d%s" % (name[:32], d.address, rssi, mark))
    print("\n共 %d 台。找到 GT5 后运行：" % len(rows))
    print("  py watch_hr.py --address 设备地址")

    # 顺便探测标准 GATT 服务（只看名称含 watch/gt 的第一台）
    target = next((d for d, _ in rows
                   if d.name and ("watch" in d.name.lower()
                                  or "gt" in d.name.lower())), None)
    if target:
        print("\n探测 %s 的服务列表（约 10 秒）..." % target.name)
        from bleak import BleakClient
        async with BleakClient(target.address, timeout=15) as client:
            for svc in client.services:
                print("  服务 %s" % svc.uuid)
                for ch in svc.characteristics:
                    props = ",".join(ch.properties)
                    print("    特征 %s (%s)" % (ch.uuid, props))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())