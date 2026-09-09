"""
hr_hud_full.py — v1.1 完全体：钢铁侠式 AR 视界 + GTP 心率 + GLM 双 AI 通道

一个窗口融合全部能力：
  · YOLO 物体检测（四角框 + 标签，自动降级 Haar 人脸）
  · J.A.R.V.I.S. 左侧系统面板（含实时心率行）
  · GTP/1.0 心率遥测（模拟 GT5，增量节流真实编码）
  · GLM 双通道：n 键视觉识别场景 / 控制台自然语言开关界面
  · 语音确认（pyttsx3）· 准星 · 扫描线 · 高心率告警

按键：d 开关检测  n GLM识别场景  s 截图  q 退出
控制台：自然语言控制界面（"关闭心率显示"等）；"识别一下" = GLM 看场景

用法：
  py hr_hud_full.py               # 摄像头
  py hr_hud_full.py --source none # 合成背景
  py hr_hud_full.py --selftest    # 自检存图退出
"""

import argparse
import json as _json
import math
import os
import random
import re as _re
import sys
import threading
import time

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))          # versions/v1.1_watch
ROOT = os.path.dirname(os.path.dirname(_HERE))              # ai_glasses_solo
sys.path.insert(0, _HERE)
sys.path.insert(0, ROOT)   # 项目根目录（brain_api/config 所在）
import gtp  # noqa: E402

try:
    import brain_api
    import config as _cfg
    HAS_AI = bool(_cfg.API_KEY) and "填入" not in _cfg.API_KEY
except Exception:
    brain_api = None
    HAS_AI = False

CYAN = (255, 210, 60)
GOLD = (80, 200, 255)
RED = (60, 60, 230)
GREEN = (90, 220, 120)
GREY = (160, 160, 160)
WHITE = (255, 255, 255)
ORANGE = (80, 170, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

LOCK = threading.Lock()
ST = {"frame": None, "dets": [], "det_on": True, "det_ms": 0.0, "det_name": "",
      "fps": 0.0, "bpm": 0, "batt": 84, "frames": 0, "crc": 0, "skip": 0,
      "trend": [], "hr_visible": True, "glm": "J.A.R.V.I.S. 待命：按 n 识别场景",
      "measuring": True}


def put(k, v):
    with LOCK:
        ST[k] = v


def get(k):
    with LOCK:
        v = ST[k]
        return v.copy() if hasattr(v, "copy") else v


# ---------- 摄像头 ----------
def open_camera(index=0):
    for name, backend in (("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            for _ in range(5):
                ok, frame = cap.read()
                if ok and frame is not None:
                    print("[摄像头] %s index=%d" % (name, index))
                    return cap
                time.sleep(0.1)
        cap.release()
    return None


def capture_thread(source, stop):
    cap = None
    use_screen = source == "screen"
    if not use_screen:
        cap = open_camera()
        if cap is None:
            print("[警告] 摄像头不可用，切换合成背景")
            use_screen = True
            put("synthetic", True)
    try:
        import mss
        sct = mss.mss()
        mon = sct.monitors[1]
        have_mss = True
    except ImportError:
        have_mss = False
    times = []
    put("synthetic", use_screen)
    while not stop.is_set():
        t0 = time.time()
        if use_screen:
            if have_mss:
                shot = sct.grab(sct.monitors[1])
                frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
            else:
                from PIL import ImageGrab
                frame = cv2.cvtColor(np.asarray(ImageGrab.grab()),
                                     cv2.COLOR_RGB2BGR)
        else:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue
        frame = cv2.resize(frame, (640, 480))
        put("frame", frame)
        times.append(t0)
        if len(times) >= 2:
            put("fps", (len(times) - 1) / (times[-1] - times[0]))
        dt = time.time() - t0
        if dt < 1 / 30:
            time.sleep(1 / 30 - dt)
    if cap is not None:
        cap.release()


def synthetic_frame():
    img = np.zeros((480, 640, 3), np.uint8)
    for yy in range(480):
        img[yy, :] = (int(18 + 20 * yy / 480), int(24 + 28 * yy / 480),
                      int(40 + 44 * yy / 480))
    cv2.putText(img, "NO CAMERA - SYNTHETIC VIEW", (130, 60), FONT, 0.7,
                (200, 200, 200), 1, cv2.LINE_AA)
    cv2.rectangle(img, (430, 300), (560, 420), (70, 140, 70), -1)
    cv2.putText(img, "OBSTACLE", (432, 290), FONT, 0.5, (120, 220, 120), 1,
                cv2.LINE_AA)
    return img


def get_view():
    f = get("frame")
    return f.copy() if f is not None else synthetic_frame()


# ---------- 检测器（YOLO → Haar 降级） ----------
class YoloDet:
    name = "YOLOv8n"

    def __init__(self):
        from ultralytics import YOLO
        self.model = YOLO("yolov8n.pt")

    def detect(self, frame):
        res = self.model(frame, verbose=False)[0]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0]]
            out.append((x1, y1, x2 - x1, y2 - y1,
                        res.names[int(b.cls[0])], float(b.conf[0])))
        return out


class HaarDet:
    name = "Haar 人脸（内置离线）"

    def __init__(self):
        base = cv2.data.haarcascades
        self.face = cv2.CascadeClassifier(
            base + "haarcascade_frontalface_default.xml")

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return [(x, y, w, h, "Face", 1.0)
                for (x, y, w, h) in self.face.detectMultiScale(
                    gray, scaleFactor=1.15, minNeighbors=5,
                    minSize=(60, 60))]


def make_detector():
    try:
        det = YoloDet()
        print("[检测器] YOLOv8n（80 类物体）")
        return det
    except Exception as e:
        print("[检测器] YOLO 不可用（%s），Haar 人脸兜底" % e.__class__.__name__)
        return HaarDet()


def detect_thread(det, stop):
    while not stop.is_set():
        if not get("det_on"):
            time.sleep(0.1)
            continue
        frame = get("frame")
        if frame is None:
            time.sleep(0.05)
            continue
        t0 = time.time()
        try:
            dets = det.detect(frame)
        except Exception:
            dets = []
        put("dets", dets)
        put("det_ms", (time.time() - t0) * 1000)
        time.sleep(0.01)


# ---------- GTP 心率模拟（模拟 GT5 遥测） ----------
def sim_thread(stop):
    bpm = 96.0
    batt = 84
    seq = 0
    t = 0
    throttle = gtp.DeltaThrottle(min_delta=2, max_interval=5.0)
    batt_th = gtp.DeltaThrottle(min_delta=1, max_interval=25)
    while not stop.is_set():
        t = int(t + 1)
        target = 118 + 26 * math.sin(t / 18.0)
        bpm += (target - bpm) * 0.25 + random.uniform(-2, 2)
        bpm = max(62, min(148, bpm))
        if throttle.should_send(bpm):
            seq += 1
            frame = gtp.encode_hr(int(round(bpm)), seq=seq & 0xF)
            try:
                d = gtp.unpack(frame)
                put("bpm", d["payload"][0])
                put("frames", get("frames") + 1)
            except gtp.GTPError:
                put("crc", get("crc") + 1)
        else:
            put("skip", get("skip") + 1)
        if t % 20 == 0:
            batt = max(5, batt - 1)
        time.sleep(1.0)


# ---------- GLM ----------
# 视觉意图关键词：命中则带画面问 GLM，否则走纯文字对话
VISION_KEYS = ("看到", "看见", "识别", "看看", "画面", "眼前", "前面",
               "周围", "这是", "什么", "读一下", "颜色", "多少", "写的是")


def has_vision_intent(text):
    return any(k in text for k in VISION_KEYS)


def glm_vision_async(frame, question):
    """带画面问答：当前帧 + 用户问题 → GLM 视觉 → 横幅 + 语音。"""
    def run():
        try:
            answer = brain_api.ask_vision(
                frame, "结合画面，用简短中文回答：" + question)
        except Exception as e:
            answer = "GLM 异常：%s（检查 API Key 与网络）" % e
        put("glm", "贾维斯: " + answer)
        print("[贾维斯]", answer)
        confirm_speak(answer)
        CHAT_HISTORY.append({"role": "assistant", "content": answer})
        del CHAT_HISTORY[:-8]
    threading.Thread(target=run, daemon=True).start()

CHAT_SYS = ("你是户外 AI 眼镜的语音助手贾维斯（J.A.R.V.I.S.）。"
            "回答简短实用，不超过 60 字，语气冷静专业。")
CHAT_HISTORY = []   # 多轮对话上下文（保留最近 8 条）


def glm_chat_async(text):
    """GLM 多轮对话：回答显示到 HUD 横幅 + 语音播报。"""
    def run():
        try:
            client = brain_api.get_client()
            msgs = ([{"role": "system", "content": CHAT_SYS}]
                    + CHAT_HISTORY[-8:]
                    + [{"role": "user", "content": text}])
            resp = client.chat.completions.create(
                model="glm-4-flash", messages=msgs)
            reply = resp.choices[0].message.content.strip()
            CHAT_HISTORY.append({"role": "user", "content": text})
            CHAT_HISTORY.append({"role": "assistant", "content": reply})
            del CHAT_HISTORY[:-8]
            put("glm", "贾维斯: " + reply)
            print("[贾维斯]", reply)
            confirm_speak(reply)
        except Exception as e:
            print("[GLM] 对话失败:", e)
            put("glm", "GLM 对话失败: %s" % e)
    threading.Thread(target=run, daemon=True).start()


def ai_toggle(text):
    text = text.strip()
    action = None
    if HAS_AI and text:
        try:
            resp = brain_api.get_client().chat.completions.create(
                model="glm-4-flash",
                messages=[{"role": "user", "content": INTENT_PROMPT + text}])
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


# ---------- HUD 绘制 ----------
def draw_hud(img, dets, det_name, det_ms, det_on):
    bpm = get("bpm")
    batt = get("batt")
    frames = get("frames")
    tr = list(get("trend"))
    hr_vis = get("hr_visible")
    measuring = get("measuring") and bpm > 0 and hr_vis
    h, w = img.shape[:2]
    now = time.strftime("%H:%M:%S")
    fps = get("fps")

    # 检测四角框 + 标签
    for (x, y, bw, bh, label, conf) in dets:
        corner_box(img, x, y, bw, bh)
        chip(img, x, y - 6, "%s %.0f%%" % (label, conf * 100))

    # 左侧 J.A.R.V.I.S. 面板
    lines = [
        "J.A.R.V.I.S. ONLINE" if det_on else "DETECTOR PAUSED",
        "TIME   %s" % now,
        "FPS    %.1f" % fps,
        "DET    %d ms (%s)" % (get("det_ms"), det_name.split()[0]),
        "TARGET %d" % len(dets),
        "HR     %d bpm" % bpm if bpm > 0 else "HR     --",
        "BATT   %d %%" % batt,
        "MODE   AR OVERLAY + GTP",
    ]
    panel(img, 12, 12, 245, lines)

    # 右上大号心率
    hr_color = RED if (measuring and bpm >= 150) else \
        (GREEN if measuring else GREY)
    if measuring:
        cv2.putText(img, str(bpm), (w - 215, 130), FONT, 2.2, hr_color, 4,
                    cv2.LINE_AA)
        cv2.putText(img, "bpm", (w - 90, 130), FONT, 0.9, hr_color, 2,
                    cv2.LINE_AA)
        ar, ac = trend_arrow(tr)
        cv2.putText(img, ar, (w - 150, 165), FONT, 0.7, ac, 2, cv2.LINE_AA)
    # 告警横幅
    if measuring and bpm >= 150:
        cv2.rectangle(img, (0, h - 130), (w, h - 90), RED, -1)
        cv2.putText(img, "! HEART RATE HIGH - %d BPM" % bpm, (20, h - 100),
                    FONT, 0.9, WHITE, 2, cv2.LINE_AA)
    # 底部 GLM 字幕横幅
    glm = get("glm")
    cv2.rectangle(img, (12, h - 52), (w - 12, h - 12), (25, 25, 25), -1)
    cv2.rectangle(img, (12, h - 52), (w - 12, h - 12), CYAN, 1)
    cv2.putText(img, "GLM: %s" % glm[:70], (20, h - 26), FONT, 0.55,
                (90, 255, 255), 1, cv2.LINE_AA)
    # 准星 + 扫描线
    cx, cy = w // 2, h // 2
    for (a, b, c, d) in ((cx - 14, cy, cx - 4, cy), (cx + 4, cy, cx + 14, cy),
                         (cx, cy - 14, cx, cy - 4), (cx, cy + 4, cx, cy + 14)):
        cv2.line(img, (a, b), (c, d), CYAN, 1)
    sy = int((time.time() * 90) % h)
    ov = img.copy()
    cv2.line(ov, (0, sy), (w, sy), CYAN, 1)
    cv2.addWeighted(ov, 0.3, img, 0.7, 0, img)


def corner_box(img, x, y, w, h, color=CYAN, t=2, ratio=0.3):
    L = max(8, int(min(w, h) * ratio))
    for (cx, cy, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1),
                             (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(img, (cx, cy), (cx + dx * L, cy), color, t)
        cv2.line(img, (cx, cy), (cx, cy + dy * L), color, t)


def chip(img, x, y, text, color=CYAN):
    (tw, th), _ = cv2.getTextSize(text, FONT, 0.52, 1)
    y = max(24, y)
    cv2.rectangle(img, (x, y - th - 10), (x + tw + 12, y + 4), (25, 25, 25),
                  -1)
    cv2.rectangle(img, (x, y - th - 10), (x + tw + 12, y + 4), color, 1)
    cv2.putText(img, text, (x + 6, y), FONT, 0.52, color, 1, cv2.LINE_AA)


def panel(img, x, y, w, lines, color=CYAN):
    h = 18 * len(lines) + 16
    roi = img[y:y + h, x:x + w]
    if roi.size:
        img[y:y + h, x:x + w] = (roi * 0.35).astype(np.uint8)
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 1)
    for i, line in enumerate(lines):
        cv2.putText(img, line, (x + 8, y + 22 + i * 18), FONT, 0.46,
                    color, 1, cv2.LINE_AA)


def trend_arrow(tr):
    vals = [v for v in tr if v > 0]
    if len(vals) < 2:
        return "-", WHITE
    diff = vals[-1] - vals[-2]
    if diff >= 2:
        return "UP", (80, 170, 255)
    if diff <= -2:
        return "DOWN", (200, 170, 80)
    return "STABLE", WHITE


# ---------- 主程序 ----------
def input_thread(stop):
    """控制台：智能路由（视觉问答 / 文字对话 / 界面控制）。"""
    chat_mode = False
    for line in sys.stdin:
        cmd = line.strip()
        if not cmd:
            continue
        low = cmd.lower()
        if low in ("q", "quit", "exit") and not chat_mode:
            stop.set()
            break
        # ---- 对话模式：视觉问题走画面，其余纯文字 ----
        if chat_mode:
            if low in ("exit", "退出"):
                chat_mode = False
                print("[已退出对话模式，回到指令模式]")
                continue
            f = get("frame")
            if has_vision_intent(cmd) and f is not None:
                glm_vision_async(f.copy(), cmd)
            else:
                glm_chat_async(cmd)
            continue
        # ---- 指令模式 ----
        if low in ("对话", "chat"):
            chat_mode = True
            print("[对话模式] 直接和贾维斯聊天；输入 退出 返回指令模式")
            continue
        if cmd in ("截图", "shot"):
            img = get_view()
            fn = time.strftime("full_shot_%H%M%S.jpg")
            cv2.imwrite(fn, img)
            print("截图", fn)
            continue
        action = ai_toggle(cmd)
        if action == "hide":
            put("hr_visible", False)
            print("[执行] 心率面板已关闭")
            confirm_speak("心率面板已关闭")
            continue
        if action == "show":
            put("hr_visible", True)
            print("[执行] 心率面板已开启")
            confirm_speak("心率面板已开启")
            continue
        # 视觉意图：带画面问 GLM（v1.0 的核心体验）
        f = get("frame")
        if f is not None and (has_vision_intent(cmd) or cmd.endswith("？")
                              or cmd.endswith("?")):
            glm_vision_async(f.copy(), cmd)
            print("[视觉] 结合画面回答中 ...")
        else:
            glm_chat_async(cmd)   # 其余 → 贾维斯文字对话


def main():
    ap = argparse.ArgumentParser(description="v1.1 完全体：AR 视界 + GTP 心率")
    ap.add_argument("--source", choices=["camera", "screen", "none"],
                    default="camera")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    source = "none" if args.source == "none" else args.source

    stop = threading.Event()
    if source == "none":
        def fill():
            while not stop.is_set():
                put("frame", synthetic_frame())
                time.sleep(0.2)
        threading.Thread(target=fill, daemon=True).start()
    else:
        threading.Thread(target=capture_thread, args=(source, stop),
                         daemon=True).start()

    # 等首帧
    for _ in range(50):
        if get("frame") is not None:
            break
        time.sleep(0.1)

    det = make_detector()
    threading.Thread(target=detect_thread, args=(det, stop),
                     daemon=True).start()
    threading.Thread(target=sim_thread, args=(stop,), daemon=True).start()
    if not args.selftest:
        threading.Thread(target=input_thread, args=(stop,),
                         daemon=True).start()
    print("v1.1 完全体已启动：d=开关检测 n=GLM识别场景 s=截图 q=退出")
    print("控制台：输入 对话 进入 GLM 聊天；或直接说 关闭心率显示 / 识别场景")

    if args.selftest:
        deadline = time.time() + 12
        while time.time() < deadline and get("det_ms") == 0:
            time.sleep(0.2)
        time.sleep(0.5)
        img = get_view()
        draw_hud(img, get("dets"), det.name, get("det_ms"), get("det_on"))
        cv2.imwrite("full_hud_preview.jpg", img)
        print("saved full_hud_preview.jpg | targets:", len(get("dets")),
              "| GTP frames:", get("frames"))
        stop.set()
        return

    while not stop.is_set():
        img = get_view()
        draw_hud(img, get("dets"), det.name, get("det_ms"), get("det_on"))
        cv2.imshow("v1.1 FULL HUD (q quit / d det / n glm / s shot)", img)
        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            stop.set()
            break
        if key == ord("d"):
            put("det_on", not get("det_on"))
        if key == ord("s"):
            fn = time.strftime("full_shot_%H%M%S.jpg")
            cv2.imwrite(fn, img)
            print("截图", fn)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()