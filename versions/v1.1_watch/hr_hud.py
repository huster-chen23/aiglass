"""
hr_hud.py — v1.1 心率 HUD（sim 源 + GTP/1.0 + AR 风格面板）

模拟华为 GT5：GTP/1.0 真实帧编码 → 解码 → HUD 心率面板（数值/趋势/告警/协议统计）。
摄像头作为眼镜视野背景；无摄像头时自动切换模拟背景。

按键：h 开/关心率测量模拟 · n 模拟冲刺(180bpm) · s 截图 · q 退出

用法：
  py hr_hud.py               # 摄像头背景
  py hr_hud.py --source none # 纯面板（无摄像头）
  py hr_hud.py --selftest    # 自检：渲染一帧存图后退出
"""

import argparse
import math
import os
import random
import sys
import threading
import time

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))          # versions/v1.1_watch
_ROOT = os.path.dirname(os.path.dirname(_HERE))             # ai_glasses_solo
sys.path.insert(0, _HERE)
sys.path.insert(0, _ROOT)   # 项目根目录（brain_api/config 所在）
import gtp  # noqa: E402
import json as _json
import re as _re

try:
    import brain_api
    import config as _cfg
    HAS_AI = bool(_cfg.API_KEY) and "填入" not in _cfg.API_KEY
except Exception:
    brain_api = None
    HAS_AI = False

CYAN = (255, 210, 60)     # 钛金
GOLD = (80, 200, 255)
RED = (60, 60, 230)
GREEN = (90, 220, 120)
GREY = (160, 160, 160)
WHITE = (255, 255, 255)
DARKBG = (25, 25, 25)
FONT = cv2.FONT_HERSHEY_SIMPLEX

STATE = {"boost": False}

LOCK = threading.Lock()
ST = {"bpm": 0, "batt": 84, "frames": 0, "crc": 0, "skip": 0,
      "tx_bpm": None, "trend": [], "last_tx": 0.0, "measuring": True,
      "frame": None, "hr_visible": True}


def put(key, value):
    with LOCK:
        ST[key] = value


def get(key):
    with LOCK:
        v = ST[key]
        return v.copy() if hasattr(v, "copy") else v


def sim_thread(stop):
    """模拟 GT5：心率按慢跑曲线波动，经 GTP 编码/解码（增量节流）。"""
    bpm = 96.0
    batt = 84
    seq = 0
    t = 0
    throttle = gtp.DeltaThrottle(min_delta=2, max_interval=5.0)
    batt_th = gtp.DeltaThrottle(min_delta=1, max_interval=25)
    while not stop.is_set():
        t += 1
        if STATE.get("boost"):
            bpm = min(185, bpm + 6)          # 冲刺：快速拉升
        else:
            # 平稳随机跳动：小步随机游走 + 向基准 96 缓慢回归
            bpm += random.choice([-2, -1, 0, 1, 2]) + (96.0 - bpm) * 0.05
            bpm = max(62, min(148, bpm))

        if throttle.should_send(bpm):
            seq += 1
            frame = gtp.encode_hr(int(round(bpm)), seq=seq & 0xF)
            try:
                d = gtp.unpack(frame)
                put("bpm", d["payload"][0])
                put("frames", ST["frames"] + 1)
                put("tx_bpm", d["payload"][0])
            except gtp.GTPError:
                put("crc", ST["crc"] + 1)
        else:
            put("skip", ST["skip"] + 1)

        if t % 20 == 0:
            batt = max(5, batt - 1)
        if batt_th.should_send(batt, time.time()):
            frame = gtp.encode_batt(batt)
            try:
                gtp.unpack(frame)
                put("batt", batt)
            except gtp.GTPError:
                pass

        with LOCK:
            tr = ST["trend"]
            tr.append(ST["bpm"])
            del tr[:-40]
        time.sleep(1.0)


def open_camera():
    for name, backend in (("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)):
        cap = cv2.VideoCapture(0, backend)
        if cap.isOpened():
            for _ in range(5):
                ok, frame = cap.read()
                if ok and frame is not None:
                    print("[摄像头] %s" % name)
                    return cap
                time.sleep(0.1)
        cap.release()
    print("[提示] 摄像头不可用，使用合成背景")
    return None


def camera_thread(stop, cap):
    while not stop.is_set():
        if cap is None:
            time.sleep(0.2)
            continue
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        frame = cv2.resize(frame, (640, 480))
        put("frame", frame)
    if cap is not None:
        cap.release()
    return None


def camera_thread(stop, cap):
    while not stop.is_set():
        if cap is None:
            time.sleep(0.2)
            continue
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue
        frame = cv2.resize(frame, (640, 480))
        with LOCK:
            ST["frame"] = frame
    if cap is not None:
        cap.release()


def trend_arrow(tr):
    if len(tr) < 3 or tr[-1] == 0:
        return "-", WHITE
    prev = next((v for v in reversed(tr[:-1]) if v > 0), tr[-1])
    diff = tr[-1] - prev
    if diff >= 2:
        return "UP", (80, 170, 255)
    if diff <= -2:
        return "DOWN", (200, 170, 80)
    return "STABLE", WHITE


def draw_hud(img):
    bpm = get("bpm")
    batt = get("batt")
    frames = get("frames")
    crc = get("crc")
    skip = get("skip")
    tx = get("tx_bpm")
    tr = list(get("trend"))
    measuring = get("measuring") and bpm > 0
    h, w = img.shape[:2]
    now = time.strftime("%H:%M:%S")

    # ---- 左上：手表 GTP 面板 ----
    panel = [
        "WATCH GT5  GTP/1.0",
        "TIME   %s" % now,
        "BATT   %d %%" % batt,
        "GTP TX %d frames" % frames,
        "CRC ERR %d" % crc,
        "SKIP   %d" % skip,
        "LASTTX %s bpm" % ("--" if tx is None else tx),
    ]
    ph = 20 * len(panel) + 14
    roi = img[10:10 + ph, 10:10 + 250]
    if roi.size:
        img[10:10 + ph, 10:10 + 250] = (roi * 0.4).astype(np.uint8)
    cv2.rectangle(img, (10, 10), (260, 10 + ph), CYAN, 1)
    for i, line in enumerate(panel):
        cv2.putText(img, line, (18, 30 + i * 20), FONT, 0.5, CYAN, 1,
                    cv2.LINE_AA)

    # ---- 右上：大号心率 + 趋势（可被 AI 关闭） ----
    hr_visible = get("hr_visible")
    measuring = measuring and bpm > 0 and hr_visible
    if hr_visible:
        hr_color = RED if (measuring and bpm >= 150) else \
            (GREEN if measuring else GREY)
        cv2.putText(img, "HR", (w - 210, 60), FONT, 0.8, CYAN, 1,
                    cv2.LINE_AA)
        if measuring:
            cv2.putText(img, str(bpm), (w - 215, 130), FONT, 2.2, hr_color,
                        4, cv2.LINE_AA)
            cv2.putText(img, "bpm", (w - 90, 130), FONT, 0.9, hr_color, 2,
                        cv2.LINE_AA)
            ar, ac = trend_arrow(tr)
            cv2.putText(img, ar, (w - 150, 165), FONT, 0.7, ac, 2,
                        cv2.LINE_AA)
        else:
            cv2.putText(img, "--", (w - 150, 120), FONT, 2.0, GREY, 3,
                        cv2.LINE_AA)
            cv2.putText(img, "NO SIGNAL", (w - 220, 160), FONT, 0.6, GREY,
                        1, cv2.LINE_AA)
    else:
        cv2.putText(img, "HR PANEL OFF", (w - 260, 60), FONT, 0.6, GREY,
                    1, cv2.LINE_AA)

    # ---- 告警横幅 ----
    if measuring and bpm >= 150:
        cv2.rectangle(img, (0, h - 130), (w, h - 90), RED, -1)
        cv2.putText(img, "! HEART RATE HIGH - %d BPM" % bpm,
                    (20, h - 100), FONT, 0.9, WHITE, 2, cv2.LINE_AA)

    # ---- 准星 + 扫描线 ----
    cx, cy = w // 2, h // 2
    cv2.line(img, (cx - 14, cy), (cx - 4, cy), CYAN, 1)
    cv2.line(img, (cx + 4, cy), (cx + 14, cy), CYAN, 1)
    cv2.line(img, (cx, cy - 14), (cx, cy - 4), CYAN, 1)
    cv2.line(img, (cx, cy + 4), (cx, cy + 14), CYAN, 1)
    sy = int((time.time() * 90) % h)
    ov = img.copy()
    cv2.line(ov, (0, sy), (w, sy), CYAN, 1)
    cv2.addWeighted(ov, 0.3, img, 0.7, 0, img)
    return img


def synthetic_frame():
    img = np.zeros((480, 640, 3), np.uint8)
    for yy in range(480):
        img[yy, :] = (int(18 + 20 * yy / 480), int(24 + 28 * yy / 480),
                      int(40 + 44 * yy / 480))
    cv2.putText(img, "NO CAMERA - SYNTHETIC VIEW", (110, 60), FONT, 0.7,
                (200, 200, 200), 1, cv2.LINE_AA)
    cv2.rectangle(img, (430, 300), (560, 420), (70, 140, 70), -1)
    cv2.putText(img, "OBSTACLE", (432, 290), FONT, 0.5, (120, 220, 120), 1,
                cv2.LINE_AA)
    return img


INTENT_PROMPT = ("你是智能眼镜显示控制器。只输出一个 JSON 对象，禁止输出任何其他文字："
                 '{"action":"hide","target":"hr"} 表示关闭心率显示，'
                 '{"action":"show","target":"hr"} 表示打开心率显示。'
                 "用户指令：")


def ai_toggle(text):
    """自然语言 → 开/关指令。GLM 意图识别优先，失败时本地关键词兜底。"""
    text = text.strip()
    action = None
    if HAS_AI and text:
        try:
            resp = brain_api.get_client().chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user",
                           "content": INTENT_PROMPT + text}])
            raw = resp.choices[0].message.content.strip()
            m = _re.search(r"\{.*\}", raw, _re.S)
            if m:
                action = _json.loads(m.group(0)).get("action")
        except Exception as e:
            print("[AI] 调用失败，本地规则兜底:", e)
    if action not in ("show", "hide"):
        if any(k in text for k in ("关", "隐藏", "收起")):
            action = "hide"
        elif any(k in text for k in ("开", "显示", "亮")):
            action = "show"
    return action


def confirm_speak(text):
    try:
        if brain_api is not None:
            brain_api.speak(text)
    except Exception:
        pass


def input_thread(stop):
    """控制台自然语言指令线程：交给 GLM 做意图识别。"""
    for line in sys.stdin:
        cmd = line.strip()
        if not cmd:
            continue
        if cmd.lower() in ("q", "quit", "exit"):
            stop.set()
            break
        action = ai_toggle(cmd)
        if action == "hide":
            put("hr_visible", False)
            print("[执行] 心率面板已关闭")
            confirm_speak("心率面板已关闭")
        elif action == "show":
            put("hr_visible", True)
            print("[执行] 心率面板已开启")
            confirm_speak("心率面板已开启")
        else:
            print("[AI] 未识别指令，可用：打开/关闭心率显示")


def main():
    ap = argparse.ArgumentParser(description="v1.1 心率 HUD（sim + GTP）")
    ap.add_argument("--source", choices=["camera", "none"], default="camera")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    stop = threading.Event()
    cap = None
    if args.source == "camera":
        cap = open_camera()
        if cap is None:
            print("[提示] 无摄像头，使用合成背景")
    if cap is not None:
        threading.Thread(target=camera_thread, args=(stop, cap),
                         daemon=True).start()
    threading.Thread(target=sim_thread, args=(stop,), daemon=True).start()
    if not args.selftest:
        threading.Thread(target=input_thread, args=(stop,),
                         daemon=True).start()
    print("HR HUD 已启动：h=模拟测量开关 n=模拟冲刺 s=截图 q=退出")
    print("控制台输入自然语言可控制显示（如：关闭心率显示）")

    if args.selftest:
        deadline = time.time() + 10
        while time.time() < deadline and get("frames") < 2:
            time.sleep(0.2)
        time.sleep(0.6)
        img = get("frame")
        if img is None:
            img = synthetic_frame()
        else:
            img = img.copy()
        draw_hud(img)
        cv2.imwrite("hr_hud_preview.jpg", img)
        print("saved hr_hud_preview.jpg | GTP frames:", get("frames"))
        stop.set()
        return

    while not stop.is_set():
        frame = get("frame")
        if frame is None:
            frame = synthetic_frame()
        img = draw_hud(frame)
        cv2.imshow("v1.1 HR HUD (q quit / h meas / n boost / s shot)", img)
        key = cv2.waitKey(200) & 0xFF
        if key == ord("q"):
            break
        if key == ord("h"):
            put("measuring", not get("measuring"))
        if key == ord("n"):
            put("boost", not get("boost"))
        if key == ord("s"):
            fn = time.strftime("hr_shot_%H%M%S.jpg")
            cv2.imwrite(fn, img)
            print("截图", fn)
    stop.set()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()

