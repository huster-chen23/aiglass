"""
relay_server.py — 跨互联网 UDP 中继服务器（房间制）

部署在任意公网 VPS（Ubuntu/Windows 均可）。通信两端可以都在 NAT/家庭路由器
后面：因为客户端主动向服务器注册，NAT 映射由客户端发起打开，服务器按"房间"
把数据转发给同房间的所有观看端。

协议（应用数据与信令复用同一 UDP 端口，用前缀区分）:
  REG|{"room":"r1","role":"sender|viewer","name":".."}   注册/加入房间
  HBT|                                                    心跳（每8秒）
  ACK|{...}                                               服务器应答
  其他任何字节                                             房间数据 → 转发给同房间所有 viewer

用途:
  1) 远程演示: 眼镜端和显示端在任何网络下互通
  2) 一对多直播: 同一房间支持 N 个 viewer（万级规模的雏形）

用法: py relay_server.py [--port 9600]
注意: 服务器防火墙/云安全组需放行对应 UDP 端口
"""

import argparse
import json
import socket
import threading
import time

CLIENT_TTL = 30.0  # 超过该秒数无心跳视为掉线


class Relay:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = {}  # addr -> {"room","role","name","last"}

    def register(self, addr, info):
        with self.lock:
            self.clients[addr] = {
                "room": info.get("room", "default"),
                "role": info.get("role", "viewer"),
                "name": info.get("name", "anon"),
                "last": time.time(),
            }
            room = self.clients[addr]["room"]
            ns = sum(1 for c in self.clients.values()
                     if c["room"] == room and c["role"] == "sender")
            nv = sum(1 for c in self.clients.values()
                     if c["room"] == room and c["role"] == "viewer")
        return "ACK|" + json.dumps({"ok": True, "room": room,
                                    "senders": ns, "viewers": nv},
                                   ensure_ascii=False)

    def heartbeat(self, addr):
        with self.lock:
            if addr in self.clients:
                self.clients[addr]["last"] = time.time()

    def viewers_of(self, room, except_addr):
        with self.lock:
            return [a for a, c in self.clients.items()
                    if c["room"] == room and c["role"] == "viewer"
                    and a != except_addr]

    def role_room(self, addr):
        with self.lock:
            c = self.clients.get(addr)
            return (c["room"], c["role"]) if c else (None, None)

    def reap(self):
        with self.lock:
            now = time.time()
            for a in [a for a, c in self.clients.items()
                      if now - c["last"] > CLIENT_TTL]:
                print("[掉线]", a)
                del self.clients[a]

    def stats(self):
        with self.lock:
            rooms = {}
            for c in self.clients.values():
                r = rooms.setdefault(c["room"], {"senders": 0, "viewers": 0})
                r[c["role"] + "s"] += 1
            return rooms


def main(port):
    relay = Relay()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    print("中继服务器已启动, UDP 端口 %d（放行防火墙/安全组 UDP %d）" % (port, port))

    def reaper():
        while True:
            time.sleep(10)
            relay.reap()

    threading.Thread(target=reaper, daemon=True).start()

    pkts = 0
    last_report = time.time()
    while True:
        data, addr = sock.recvfrom(65535)
        pkts += 1
        now = time.time()
        if now - last_report >= 10:
            print("[状态] 收包 %d | 房间 %s" % (pkts, relay.stats() or "{}"))
            pkts = 0
            last_report = now

        if data.startswith(b"REG|"):
            try:
                info = json.loads(data[4:].decode("utf-8"))
            except Exception:
                continue
            sock.sendto(relay.register(addr, info).encode("utf-8"), addr)
            print("[注册]", addr, info)
        elif data.startswith(b"HBT|"):
            relay.heartbeat(addr)
        else:
            room, role = relay.role_room(addr)
            if room is None or role != "sender":
                continue  # 未注册或非发送端，忽略
            for v in relay.viewers_of(room, addr):
                sock.sendto(data, v)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="AI 眼镜 跨互联网中继服务器")
    ap.add_argument("--port", type=int, default=9600)
    main(ap.parse_args().port)