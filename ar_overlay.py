"""
ar_overlay.py — AR 信息叠加（钢铁侠式 HUD）

持续检测画面中的物体，用四角框 + 信息标签叠加显示，附左侧系统面板。
检测器自动降级：YOLOv8（如安装 ultralytics）→ Haar 人脸（OpenCV 内置离线）。

交互：
  d = 开/关检测      n = 让 GLM 识别当前场景（贾维斯模式）
  s = 截图保存       q = 退出

用法：
  py ar_overlay.py                 # 摄像头
  py ar_overlay.py --source screen # 屏幕
"""

import argparse
import threading
import time
from collections import deque

import cv2
import numpy as np

import config

# ---------- 共享状态 ----------
STATE = {
    "frame": None,          # 最新帧（BGR）
    "dets": [],             # [(x,y,w,h,label,conf)]
    "det_on": True,
    "det_ms": 0.0,
    "fps": 0.0,
    "glm": "J.A.R.V.I.S. 待命：按 N 识别当前场景",
    "lock": threading.Lock(),
}


def put(key, value):
    with STATE["lock"]:
        STATE[key] = value


def get(key):
    with STATE["lock"]:
        v = STATE[key]
        return v.copy() if hasattr(v, "copy") else v


# ---------- 摄像头（与 glasses_main 相同的健壮打开逻辑） ----------
def open_camera(index=0):
    for name, backend in (("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)):
        cap = cv2.VideoCapture(index, backend)
        if cap.isOpened():
            for _ in range(5):
                ok, frame = cap.read()
                if ok and frame is not None:
                    print("[摄像头] %s 后端 index=%d" % (name, index))
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
            print("[警告] 摄像头不可用，切换屏幕捕获")
            use_screen = True
    try:
        import mss
        sct = mss.mss()
        mon = sct.monitors[1]
        have_mss = True
    except ImportError:
        have_mss = False

    times = deque(maxlen=15)
    while not stop.is_set():
        t0 = time.time()
        if use_screen:
            if have_mss:
                shot = sct.grab(mon)
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
        put("frame", frame)
        times.append(t0)
        if len(times) >= 2:
            put("fps", (len(times) - 1) / (times[-1] - times[0]))
        dt = time.time() - t0
        if dt < 1 / 30:
            time.sleep(1 / 30 - dt)
    if cap is not None:
        cap.release()


# ---------- 检测器（自动降级） ----------
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
            label = res.names[int(b.cls[0])]
            out.append((x1, y1, x2 - x1, y2 - y1, label, float(b.conf[0])))
        return out


class HaarDet:
    name = "Haar 人脸（内置离线）"

    def __init__(self):
        base = cv2.data.haarcascades
        self.face = cv2.CascadeClassifier(
            base + "haarcascade_frontalface_default.xml")

    def detect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out = []
        for (x, y, w, h) in self.face.detectMultiScale(
                gray, scaleFactor=1.15, minNeighbors=5, minSize=(60, 60)):
            out.append((x, y, w, h, "Face", 1.0))
        return out


def make_detector():
    try:
        det = YoloDet()
        print("[检测器] YOLOv8n（80 类物体）")
        return det
    except Exception as e:
        print("[检测器] YOLO 不可用（%s），使用 Haar 人脸" % e.__class__.__name__)
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


# ---------- HUD 绘制 ----------
CYAN = (255, 210, 60)      # BGR 钛金色
GOLD = (60, 200, 255)
RED = (60, 60, 230)


def corner_box(img, x, y, w, h, color=CYAN, t=2, ratio=0.3):
    """钢铁侠式四角括号框。"""
    L = max(8, int(min(w, h) * ratio))
    for (cx, cy, dx, dy) in ((x, y, 1, 1), (x + w, y, -1, 1),
                             (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(img, (cx, cy), (cx + dx * L, cy), color, t)
        cv2.line(img, (cx, cy), (cx, cy + dy * L), color, t)


def chip(img, x, y, text, color=CYAN):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 1)
    y = max(24, y)
    cv2.rectangle(img, (x, y - th - 10), (x + tw + 12, y + 4), (25, 25, 25),
                  -1)
    cv2.rectangle(img, (x, y - th - 10), (x + tw + 12, y + 4), color, 1)
    cv2.putText(img, text, (x + 6, y), cv2.FONT_HERSHEY_SIMPLEX, 0.52,
                color, 1, cv2.LINE_AA)


def panel(img, x, y, w, lines, color=CYAN):
    h = 18 * len(lines) + 16
    roi = img[y:y + h, x:x + w]
    if roi.size:
        dark = (roi * 0.35).astype(np.uint8)
        img[y:y + h, x:x + w] = dark
    cv2.rectangle(img, (x, y), (x + w, y + h), color, 1)
    for i, line in enumerate(lines):
        cv2.putText(img, line, (x + 8, y + 22 + i * 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, color, 1, cv2.LINE_AA)


def draw_hud(img, dets, fps, det_ms, det_name, det_on, glm_text):
    h, w = img.shape[:2]
    for (x, y, bw, bh, label, conf) in dets:
        corner_box(img, x, y, bw, bh)
        chip(img, x, y - 6, "%s %.0f%%" % (label, conf * 100))
    # 准星
    cx, cy = w // 2, h // 2
    cv2.line(img, (cx - 14, cy), (cx - 4, cy), CYAN, 1)
    cv2.line(img, (cx + 4, cy), (cx + 14, cy), CYAN, 1)
    cv2.line(img, (cx, cy - 14), (cx, cy - 4), CYAN, 1)
    cv2.line(img, (cx, cy + 4), (cx, cy + 14), CYAN, 1)
    # 左侧系统面板
    now = time.strftime("%H:%M:%S")
    panel(img, 12, 12, 240, [
        "J.A.R.V.I.S. ONLINE" if det_on else "DETECTOR PAUSED",
        "TIME   %s" % now,
        "FPS    %.1f" % fps,
        "DET    %d ms (%s)" % (det_ms, det_name.split()[0]),
        "TARGET %d" % len(dets),
        "MODE   AR OVERLAY",
    ])
    # 底部 GLM 回答
    cv2.rectangle(img, (12, h - 52), (w - 12, h - 12), (25, 25, 25), -1)
    cv2.rectangle(img, (12, h - 52), (w - 12, h - 12), CYAN, 1)
    cv2.putText(img, "GLM: %s" % glm_text[:70], (20, h - 26),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (90, 255, 255), 1,
                cv2.LINE_AA)
    # 扫描线
    sy = int((time.time() * 90) % h)
    overlay = img.copy()
    cv2.line(overlay, (0, sy), (w, sy), CYAN, 1)
    cv2.addWeighted(overlay, 0.35, img, 0.65, 0, img)


# ---------- 主程序 ----------
def glm_ask_async(frame, question):
    def run():
        try:
            import brain_api
            answer = brain_api.ask_vision(frame, question)
        except Exception as e:
            answer = "GLM 离线：%s" % e
        put("glm", answer)
        try:
            import brain_api
            brain_api.speak(answer)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description="AR 信息叠加 HUD")
    ap.add_argument("--source", choices=["camera", "screen"],
                    default="camera")
    ap.add_argument("--selftest", action="store_true",
                    help="跑一帧检测并存图后退出")
    args = ap.parse_args()
    source = "screen" if args.source == "screen" else "camera"

    stop = threading.Event()
    threading.Thread(target=capture_thread, args=(source, stop),
                     daemon=True).start()

    # 等第一帧
    for _ in range(50):
        if get("frame") is not None:
            break
        time.sleep(0.1)
    det = make_detector()
    threading.Thread(target=detect_thread, args=(det, stop),
                     daemon=True).start()
    print("AR HUD 已启动：d=开关检测 n=GLM识别 s=截图 q=退出")

    if args.selftest:
        print("等待检测线程首次出框（模型预热需数秒）...")
        deadline = time.time() + 30
        while time.time() < deadline and get("det_ms") == 0:
            time.sleep(0.2)
        time.sleep(0.5)
        frame = get("frame").copy()
        dets = get("dets")
        draw_hud(frame, dets, get("fps"), get("det_ms"), det.name,
                 get("det_on"), "SELFTEST: detection preview")
        cv2.imwrite("ar_hud_preview.jpg", frame)
        print("saved ar_hud_preview.jpg, targets:", len(dets))
        stop.set()
        return

    fps = 0.0
    t0 = time.time()
    n = 0
    while True:
        frame = get("frame")
        if frame is None:
            if cv2.waitKey(50) & 0xFF == ord("q"):
                break
            continue
        img = frame.copy()
        draw_hud(img, get("dets"), get("fps"), get("det_ms"), det.name,
                 get("det_on"), get("glm"))
        cv2.imshow("AR Overlay (q quit / d detect / n GLM / s shot)", img)
        n += 1
        if time.time() - t0 >= 1:
            fps = n / (time.time() - t0)
            put("fps", fps)
            n = 0
            t0 = time.time()
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord("d"):
            put("det_on", not get("det_on"))
        if key == ord("s"):
            fn = time.strftime("ar_shot_%H%M%S.jpg")
            cv2.imwrite(fn, img)
            print("截图", fn)
        if key == ord("n"):
            f = get("frame")
            if f is not None:
                glm_ask_async(f.copy(),
                              "像钢铁侠的贾维斯一样，用简短中文列出你看到的物体和场景")
    stop.set()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()