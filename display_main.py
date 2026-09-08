"""
display_main.py — 接收端（模拟眼镜显示屏）

直连模式: UDP 图传窗口实时显示第一视角；AI 结果字幕叠加在画面上。按 q 退出。
中继模式: 注册到公网中继服务器加入房间，远程观看任意网络下眼镜端的第一视角。

用法:
    py display_main.py                          （本机/局域网直连）
    py display_main.py --relay 服务器IP:9600 --room demo   （跨互联网）
"""

import argparse
import json
import socket
import threading
import time

import cv2
import numpy as np

import config
import protocol

FRAME_TIMEOUT = 0.5

latest_result = ["AI 待命：在眼镜端按 v 或输入问题"]
result_lock = threading.Lock()

DIRECT_STREAM_PORT = config.STREAM_PORT
DIRECT_RESULT_PORT = config.RESULT_PORT


def push_result(text):
    with result_lock:
        latest_result.insert(0, "[AI] " + text)
        del latest_result[3:]


def overlay(img, hud):
    with result_lock:
        lines = list(latest_result)
    y = img.shape[0] - 12 - 26 * (len(lines) - 1)
    for i, line in enumerate(lines):
        y_i = y + i * 26
        cv2.putText(img, line[:60], (10, y_i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(img, line[:60], (10, y_i),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (90, 255, 90), 1)
    cv2.putText(img, hud, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 0), 3)
    cv2.putText(img, hud, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1)


class Stats:
    def __init__(self):
        self.n = 0
        self.t0 = time.time()
        self.delay = 0.0

    def add(self, latency_ms):
        self.n += 1
        self.delay += latency_ms

    def hud(self):
        el = time.time() - self.t0
        fps = self.n / el if el else 0
        return "fps %.1f | latency %d ms" % (fps, self.delay / max(self.n, 1))


def handle_frame_bytes(data, ts_ms, stats):
    """解码一帧 JPEG 并叠加字幕/HUD，返回图像或 None。"""
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    stats.add(int(time.time() * 1000) - ts_ms)
    overlay(img, stats.hud())
    return img


def run_direct(stop_event):
    """直连模式：两个端口分别收图传与字幕。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", DIRECT_STREAM_PORT))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)

    rsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rsock.bind(("", DIRECT_RESULT_PORT))

    def result_listener():
        while not stop_event.is_set():
            data, _ = rsock.recvfrom(65535)
            try:
                msg = json.loads(data.decode("utf-8"))
            except Exception:
                continue
            if msg.get("type") == "ai_result":
                push_result(msg.get("text", ""))

    threading.Thread(target=result_listener, daemon=True).start()

    frames = {}
    stats = Stats()
    print("接收端[直连] 已启动（图传 %d / 字幕 %d），按 q 退出"
          % (DIRECT_STREAM_PORT, DIRECT_RESULT_PORT))

    while not stop_event.is_set():
        datagram, _ = sock.recvfrom(protocol.MAX_DATAGRAM)
        parsed = protocol.defragment(datagram)
        if parsed is None:
            continue
        frame_id, total, seq, _, ts_ms, payload = parsed
        entry = frames.setdefault(frame_id, {"total": total, "chunks": {},
                                             "ts": ts_ms,
                                             "first": time.time()})
        entry["chunks"][seq] = payload
        if len(entry["chunks"]) == entry["total"]:
            data = b"".join(entry["chunks"][i] for i in range(total))
            img = handle_frame_bytes(data, entry["ts"], stats)
            del frames[frame_id]
            if img is not None:
                cv2.imshow("AI Glasses Display (q to quit)", img)
        expired = [k for k, v in frames.items()
                   if time.time() - v["first"] > FRAME_TIMEOUT]
        for k in expired:
            del frames[k]
        if cv2.waitKey(1) & 0xFF == ord("q"):
            stop_event.set()


def run_relay(relay_addr, room, name, stop_event):
    """中继模式：注册 viewer，单 socket 接收帧与字幕。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 0))
    reg = json.dumps({"room": room, "role": "viewer", "name": name},
                     ensure_ascii=False).encode("utf-8")
    for i in range(3):
        sock.sendto(b"REG|" + reg, relay_addr)
        sock.settimeout(2)
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            print("[中继] 第 %d 次注册无响应 ..." % (i + 1))
            continue
        if data.startswith(b"ACK|"):
            ack = json.loads(data[4:].decode("utf-8"))
            print("[中继] 注册成功 房间=%s 发送端=%d 观看端=%d"
                  % (ack.get("room"), ack.get("senders"), ack.get("viewers")))
            break
    else:
        raise SystemExit("无法连接中继服务器 %s" % (relay_addr,))
    sock.settimeout(None)

    def heartbeat():
        while not stop_event.is_set():
            sock.sendto(b"HBT|", relay_addr)
            time.sleep(8)

    threading.Thread(target=heartbeat, daemon=True).start()

    frames = {}
    stats = Stats()
    print("接收端[中继] 已加入房间 %s，按 q 退出" % room)

    while not stop_event.is_set():
        data, _ = sock.recvfrom(protocol.MAX_DATAGRAM)
        if data.startswith((b"REG|", b"HBT|", b"ACK|")):
            continue
        try:
            msg = json.loads(data.decode("utf-8"))
            if isinstance(msg, dict) and msg.get("type") == "ai_result":
                push_result(msg.get("text", ""))
                continue
        except Exception:
            pass
        parsed = protocol.defragment(data)
        if parsed is None:
            continue
        frame_id, total, seq, _, ts_ms, payload = parsed
        entry = frames.setdefault(frame_id, {"total": total, "chunks": {},
                                             "ts": ts_ms,
                                             "first": time.time()})
        entry["chunks"][seq] = payload
        if len(entry["chunks"]) == entry["total"]:
            raw = b"".join(entry["chunks"][i] for i in range(total))
            img = handle_frame_bytes(raw, entry["ts"], stats)
            del frames[frame_id]
            if img is not None:
                cv2.imshow("AI Glasses Display - room %s (q to quit)" % room,
                           img)
        expired = [k for k, v in frames.items()
                   if time.time() - v["first"] > FRAME_TIMEOUT]
        for k in expired:
            del frames[k]
        if cv2.waitKey(1) & 0xFF == ord("q"):
            stop_event.set()


def main():
    ap = argparse.ArgumentParser(description="AI 眼镜接收端（模拟显示屏）")
    ap.add_argument("--relay", default="",
                    help="中继服务器 IP:端口（跨互联网模式，留空=本机直连）")
    ap.add_argument("--room", default="glasses-demo", help="房间号")
    ap.add_argument("--name", default="viewer", help="本端名称")
    args = ap.parse_args()

    stop_event = threading.Event()
    if args.relay:
        host, _, port = args.relay.rpartition(":")
        relay_addr = (host, int(port or 9600))
        run_relay(relay_addr, args.room, args.name, stop_event)
    else:
        run_direct(stop_event)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()