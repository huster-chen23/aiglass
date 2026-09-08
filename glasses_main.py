"""
glasses_main.py — 眼镜端主程序（软件仿真版，支持本机直连与跨互联网中继）

后台线程：摄像头/屏幕捕获 -> JPEG -> UDP 分片 -> 发往显示端或中继服务器
主线程交互：
    v        = 抓拍一帧 -> GLM 视觉 API 识别 -> 语音播报 + 发送字幕
    任意问题  = 带问题的视觉问答
    q / quit = 退出

直连模式（同一局域网/本机）:
    py glasses_main.py
远程模式（经公网中继，任何网络可达）:
    py glasses_main.py --relay 服务器IP:9600 --room demo
"""

import argparse
import json
import socket
import threading
import time

import cv2
import numpy as np

import brain_api
import config
import protocol

CAM_INDEX = 0
CAMERA_FALLBACK = False  # 摄像头不可用而切换屏幕捕获时置 True

# 图传线程持续更新的最新一帧；按键抓拍直接取它，避免二次打开摄像头
_latest = {"frame": None}
_latest_lock = threading.Lock()


def _store_latest(frame):
    with _latest_lock:
        _latest["frame"] = frame.copy()


def get_latest_frame():
    with _latest_lock:
        f = _latest["frame"]
        return f.copy() if f is not None else None


def open_camera(index=CAM_INDEX):
    """多个索引 x 多种后端逐一尝试，必须读到首帧才算成功。"""
    candidates = []
    for idx in [index, 0, 1, 2]:
        if idx not in [c[0] for c in candidates]:
            candidates.append((idx, "DSHOW", cv2.CAP_DSHOW))
            candidates.append((idx, "MSMF", cv2.CAP_MSMF))
            candidates.append((idx, "AUTO", None))
    for idx, name, backend in candidates:
        cap = (cv2.VideoCapture(idx) if backend is None
               else cv2.VideoCapture(idx, backend))
        if not cap.isOpened():
            cap.release()
            continue
        # 预热：有些摄像头前几帧拿不到，多读几次
        for _ in range(5):
            ok, frame = cap.read()
            if ok and frame is not None:
                print("[摄像头] 已通过 %s 后端打开 (index=%d)" % (name, idx))
                return cap
            time.sleep(0.1)
        cap.release()
    return None


def make_link(relay_addr, room, name, stop_event):
    """建立网络链路。

    直连模式: 返回 (sock, stream目的地址, result目的地址)
    中继模式: 单一 socket 先注册 sender 角色, 再周期心跳;
              图传与字幕都从同一 socket 发出（中继按源地址识别转发）。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    if relay_addr is None:
        return sock, (config.PC_IP, config.STREAM_PORT), \
               (config.PC_IP, config.RESULT_PORT)

    reg = json.dumps({"room": room, "role": "sender", "name": name},
                     ensure_ascii=False).encode("utf-8")
    for i in range(3):
        try:
            sock.sendto(b"REG|" + reg, relay_addr)
            sock.settimeout(2)
            data, _ = sock.recvfrom(65535)
            if data.startswith(b"ACK|"):
                ack = json.loads(data[4:].decode("utf-8"))
                print("[中继] 注册成功 房间=%s 发送端=%d 观看端=%d"
                      % (ack.get("room"), ack.get("senders"),
                         ack.get("viewers")))
                break
        except socket.timeout:
            print("[中继] 第 %d 次注册无响应 ..." % (i + 1))
    else:
        raise SystemExit("无法连接中继服务器 %s（检查IP端口/防火墙/安全组）"
                         % (relay_addr,))
    sock.settimeout(None)

    def heartbeat():
        while not stop_event.is_set():
            sock.sendto(b"HBT|", relay_addr)
            time.sleep(8)

    threading.Thread(target=heartbeat, daemon=True).start()
    return sock, relay_addr, relay_addr


def capture_thread(source, stop_event, sock, stream_dest):
    """后台图传线程：捕获 -> 压缩 -> UDP 分片发送。"""
    global CAMERA_FALLBACK
    cap = None
    grab_screen = source == "screen"
    if not grab_screen:
        cap = open_camera()
        if cap is None:
            print("[警告] 摄像头不可用（被占用或未授权），自动切换为屏幕捕获")
            print("[提示] 检查: 1) 关闭其他占用摄像头的程序  "
                  "2) Windows 设置-隐私-相机 允许桌面应用访问")
            grab_screen = True
            CAMERA_FALLBACK = True

    frame_id = 0
    period = 1.0 / config.FPS
    fail_count = 0

    try:
        import mss
        sct = mss.mss()
        mon = sct.monitors[1]
        have_mss = True
    except ImportError:
        have_mss = False

    while not stop_event.is_set():
        t0 = time.time()
        if grab_screen:
            if have_mss:
                shot = sct.grab(mon)
                frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
            else:
                from PIL import ImageGrab
                frame = cv2.cvtColor(np.asarray(
                    ImageGrab.grab()), cv2.COLOR_RGB2BGR)
        else:
            ok, frame = cap.read()
            if not ok:
                fail_count += 1
                if fail_count % 40 == 1:
                    print("[警告] 摄像头抓帧失败，重试中（%d 次）..." % fail_count)
                if fail_count >= 300:  # 约 15 秒，给摄像头充分预热时间
                    print("[错误] 摄像头持续失败，切换为屏幕捕获。"
                          "请检查是否被其他程序占用或隐私设置未放行")
                    cap.release()
                    grab_screen = True
                    CAMERA_FALLBACK = True
                if fail_count > 300:
                    pass  # 已切屏幕模式，走下方逻辑
                else:
                    time.sleep(0.05)
                    continue
            else:
                fail_count = 0
        if config.CAPTURE_SCALE != 1.0:
            frame = cv2.resize(frame, None, fx=config.CAPTURE_SCALE,
                               fy=config.CAPTURE_SCALE,
                               interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", frame,
                               [cv2.IMWRITE_JPEG_QUALITY, config.JPEG_QUALITY])
        if ok:
            _store_latest(frame)
            for d in protocol.fragment(frame_id, buf.tobytes(),
                                       int(time.time() * 1000)):
                sock.sendto(d, stream_dest)
            frame_id += 1
        dt = time.time() - t0
        if dt < period:
            time.sleep(period - dt)
    if cap is not None:
        cap.release()


def send_result_text(sock, result_dest, text):
    """把 AI 结果以 JSON 数据报发给显示端（或经中继转发），用作画面字幕。"""
    sock.sendto(json.dumps({"type": "ai_result", "text": text},
                           ensure_ascii=False).encode("utf-8"), result_dest)


def capture_one_frame(source):
    """抓拍一帧（BGR）：摄像头模式直接取图传线程缓存的最新帧（独占设备
    不允许开第二个 capture）；屏幕模式现场抓屏。"""
    if source != "screen" and not CAMERA_FALLBACK:
        frame = get_latest_frame()
        if frame is None:
            return None
    else:
        from PIL import ImageGrab
        frame = cv2.cvtColor(np.asarray(ImageGrab.grab()), cv2.COLOR_RGB2BGR)
    if config.CAPTURE_SCALE != 1.0:
        frame = cv2.resize(frame, None, fx=config.CAPTURE_SCALE,
                           fy=config.CAPTURE_SCALE)
    return frame


def main():
    ap = argparse.ArgumentParser(description="AI 眼镜端（软件仿真）")
    ap.add_argument("--source", choices=["camera", "screen"],
                    default="camera", help="画面来源")
    ap.add_argument("--relay", default="",
                    help="中继服务器 IP:端口（跨互联网模式，留空=本机直连）")
    ap.add_argument("--room", default="glasses-demo", help="房间号")
    ap.add_argument("--name", default="glasses", help="本端名称")
    ap.add_argument("--cam-index", type=int, default=0,
                    help="摄像头编号（不确定先跑 check_camera.py）")
    args = ap.parse_args()
    source = "screen" if args.source == "screen" else "camera"
    global CAM_INDEX
    CAM_INDEX = args.cam_index

    relay_addr = None
    if args.relay:
        host, _, port = args.relay.rpartition(":")
        relay_addr = (host, int(port or 9600))

    stop_event = threading.Event()
    sock, stream_dest, result_dest = make_link(
        relay_addr, args.room, args.name, stop_event)
    mode = "中继(%s)" % (args.relay,) if relay_addr else "直连(%s:%d)" % (
        config.PC_IP, config.STREAM_PORT)

    threading.Thread(target=capture_thread,
                     args=(source, stop_event, sock, stream_dest),
                     daemon=True).start()
    print("=" * 52)
    print("AI 眼镜端已启动 模式=%s 房间=%s" % (mode, args.room))
    print("  窗口内按 v : 抓拍识别（我看到了什么）")
    print("  终端输入问题回车 : 视觉问答")
    print("  输入 q 退出")
    print("=" * 52)

    while True:
        try:
            cmd = input("眼镜> ").strip()
        except EOFError:
            # 无标准输入（如后台运行）：保持图传，等待 Ctrl+C 或 stop 信号
            print("[提示] 无交互输入，持续图传中；按 Ctrl+C 退出")
            try:
                while not stop_event.is_set():
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            break
        if cmd.lower() in ("q", "quit", "exit"):
            stop_event.set()
            break
        if cmd == "v":
            question = "用一句简短中文说明画面里有什么"
        elif cmd:
            question = "结合画面回答，用简短中文：%s" % cmd
        else:
            continue
        frame = capture_one_frame(source)
        if frame is None:
            print("[错误] 抓帧失败")
            continue
        print("[AI] 正在识别 ...")
        try:
            answer = brain_api.ask_vision(frame, question)
        except Exception as e:
            answer = "API 调用失败: %s" % e
            print(answer)
            continue
        print("[AI 回答]", answer)
        brain_api.speak(answer)
        send_result_text(sock, result_dest, answer)

    stop_event.set()
    print("眼镜端已退出")


if __name__ == "__main__":
    main()