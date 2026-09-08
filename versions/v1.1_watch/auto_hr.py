"""
auto_hr.py — v1.1 自动化链路：手表 → GB → 电脑
流程：启动 GB → 点同步(抓最新) → 菜单 → 数据管理 → 导出数据 → adb 拉取 → 解析心率
用法：
  py auto_hr.py            # 单次执行
  py auto_hr.py --loop 30  # 每 30 秒循环执行
"""

import argparse
import os
import sqlite3
import subprocess
import sys
import time

ADB = os.path.join(os.environ["LOCALAPPDATA"], "Programs",
                   "platform-tools", "platform-tools", "adb.exe")
PKG = "nodomain.freeyourgadget.gadgetbridge"
REMOTE_DIR = ("/storage/emulated/0/Android/data/"
              + PKG + "/files")
GB_MAIN = PKG + "/.activities.ControlCenters2"

# 校准好的点击坐标（屏幕 1220x2700）
TAP_SYNC = (424, 1118)
TAP_MENU = (92, 225)
TAP_DATAMGMT = (299, 1002)
TAP_EXPORT = (354, 2065)


def adb(*args, timeout=15):
    return subprocess.run([ADB, *args], capture_output=True, timeout=timeout)


def tap(x, y):
    adb("shell", "input", "tap", str(x), str(y))


def screenshot(tag):
    adb("shell", "screencap", "-p", "/sdcard/scr_%s.png" % tag)
    adb("pull", "/sdcard/scr_%s.png" % tag, "scr_%s.png" % tag)


def latest_db_local():
    """拉取导出目录里最新的 Gadgetbridge 数据库。"""
    out = subprocess.run([ADB, "shell", "ls", "-t", REMOTE_DIR],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        name = line.strip().split()[-1] if line.strip() else ""
        if name == "Gadgetbridge" or name.startswith("Gadgetbridge"):
            remote = REMOTE_DIR + "/" + name
            local = os.path.join("gb_data", name)
            os.makedirs("gb_data", exist_ok=True)
            adb("pull", remote, local)
            return local
    return None


def parse_hr(db_path):
    """解析 GB 数据库中的心率样本（标准表 HEART_RATE_SAMPLE）。"""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    result = {"tables": tables, "hr": []}
    for table, tcol, vcol in (
            ("HEART_RATE_SAMPLE", "TIMESTAMP", "HR_VALUE"),
            ("HUAWEI_ACTIVITY_SAMPLE", "TIMESTAMP", "HEART_RATE")):
        if table not in tables:
            continue
        try:
            rows = cur.execute(
                "SELECT %s, %s FROM %s WHERE CAST(%s AS INTEGER) > 0 "
                "ORDER BY %s DESC LIMIT 10" % (tcol, vcol, table, vcol, tcol)
            ).fetchall()
            if rows:
                result["hr"].append({"table": table, "rows": rows})
        except sqlite3.OperationalError as e:
            result["hr"].append({"table": table, "error": str(e)})
    con.close()
    return result


def fmt_ts(ts):
    """GB 时间戳秒/毫秒兼容。"""
    if ts > 10 ** 11:
        ts /= 1000
    return time.strftime("%m-%d %H:%M:%S", time.localtime(ts))


def one_cycle():
    # 1. 确保 GB 在前台
    adb("shell", "monkey", "-p", PKG, "-c",
        "android.intent.category.LAUNCHER", "1")
    time.sleep(2)
    # 2. 点同步（从手表抓最新数据）
    tap(*TAP_SYNC)
    time.sleep(8)
    # 3. 菜单 → 数据管理
    tap(*TAP_MENU)
    time.sleep(1.5)
    tap(*TAP_DATAMGMT)
    time.sleep(1.5)
    # 4. 点导出数据
    tap(*TAP_EXPORT)
    time.sleep(3)
    # 5. 拉取并解析
    local = latest_db_local()
    if local is None:
        print("[!] 导出目录中未找到数据库文件")
        return None
    print("[+] 数据库已拉取:", local)
    data = parse_hr(local)
    for entry in data["hr"]:
        if "error" in entry:
            print("[!] 表 %s: %s" % (entry["table"], entry["error"]))
        else:
            print("[HR] 表 %s 最新样本:" % entry["table"])
            for ts, hr in entry["rows"][:5]:
                print("    %s -> %s bpm" % (fmt_ts(ts), hr))
    return data


def main():
    ap = argparse.ArgumentParser(description="v1.1 自动化心率链路")
    ap.add_argument("--loop", type=float, default=0,
                    help="循环间隔秒数（0=单次执行）")
    args = ap.parse_args()

    if args.loop <= 0:
        one_cycle()
        return
    while True:
        try:
            one_cycle()
        except Exception as e:
            print("[错误]", e)
        time.sleep(args.loop)


if __name__ == "__main__":
    main()