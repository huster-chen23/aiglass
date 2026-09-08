"""
ui_tools.py — 安卓 UI 自动化小工具（基于 adb + uiautomator）

用法：
  py ui_tools.py dump                    打印当前界面所有文本控件及坐标
  py ui_tools.py tap <x> <y>             点击坐标
  py ui_tools.py taptext <关键词>        点击包含关键词的文本控件
  py ui_tools.py back                    返回键
"""

import os
import re
import subprocess
import sys
import time

ADB = os.path.join(os.environ["LOCALAPPDATA"], "Programs",
                   "platform-tools", "platform-tools", "adb.exe")


def sh(*args, timeout=20):
    return subprocess.run([ADB, *args], capture_output=True,
                          text=True, timeout=timeout).stdout


def dump_xml():
    sh("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    time.sleep(0.5)
    sh("pull", "/sdcard/ui.xml", "ui.xml")
    with open("ui.xml", encoding="utf-8") as f:
        return f.read()


def find_nodes(xml, keyword=None):
    nodes = []
    for m in re.finditer(r"<node[^>]*/?>", xml):
        tag = m.group(0)
        tm = re.search(r'text="([^"]*)"', tag)
        dm = re.search(r'content-desc="([^"]*)"', tag)
        bm = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', tag)
        if not bm:
            continue
        text = tm.group(1) if tm else ""
        desc = dm.group(1) if dm else ""
        x1, y1, x2, y2 = map(int, bm.groups())
        label = text or desc
        if keyword and keyword not in (label or ""):
            continue
        nodes.append((label, (x1 + x2) // 2, (y1 + y2) // 2))
    return nodes


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        xml = dump_xml()
        for label, x, y in find_nodes(xml):
            print("(%4d,%4d)  %s" % (x, y, label[:60]))
    elif cmd == "tap":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        sh("shell", "input", "tap", str(x), str(y))
        print("tapped", x, y)
    elif cmd == "taptext":
        xml = dump_xml()
        keyword = sys.argv[2]
        hits = find_nodes(xml, keyword)
        if not hits:
            print("未找到包含", keyword)
            sys.exit(1)
        label, x, y = hits[0]
        sh("shell", "input", "tap", str(x), str(y))
        print("tapped [%s] at %d,%d" % (label[:40], x, y))
    elif cmd == "back":
        sh("shell", "input", "keyevent", "4")
        print("back")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()