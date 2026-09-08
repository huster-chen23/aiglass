import asyncio, sys
sys.path.insert(0, "versions/v1.1_watch")
from bleak import BleakScanner

async def main():
    for rnd in range(6):
        found = await BleakScanner.discover(timeout=10, return_adv=True)
        hits = []
        for d, adv in found.values():
            name = (d.name or "").lower()
            if "gt5" in name or "gt 5" in name or "huawei" in name:
                hits.append((d.address, d.name, adv.rssi))
        print("round %d: %d 台设备, 命中 %d" % (rnd+1, len(found), len(hits)), flush=True)
        for addr, name, rssi in hits:
            print("  FOUND -> %s  %s  RSSI %d" % (addr, name, rssi), flush=True)
            return
        await asyncio.sleep(1)
    print("NOT FOUND: 请确认手机蓝牙已关，且手表屏幕点亮")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
asyncio.run(main())

