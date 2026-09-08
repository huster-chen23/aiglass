import argparse
import os
import socket
import struct
import time

import cv2
import numpy as np

import protocol


def receive_exact(sock, size):
    data = b""
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            return None
        data += part
    return data


def save_image(data, path):
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    cv2.imwrite(path, image)
    return image


def main(args):
    os.makedirs(args.output, exist_ok=True)
    image_path = os.path.join(args.output, args.name + "_received.jpg")
    start = time.time()
    received_packets = 0
    displayed = 0
    lost = 0
    delays = []

    if args.protocol == "tcp":
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((args.host, args.port))
        sock.settimeout(None)
        while time.time() - start < args.seconds:
            header = receive_exact(sock, 4)
            if header is None:
                break
            length = struct.unpack("!I", header)[0]
            data = receive_exact(sock, length)
            if data is None:
                break
            if save_image(data, image_path) is not None:
                displayed += 1
        sock.close()
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", args.port))
        sock.settimeout(1)
        frames = {}
        while time.time() - start < args.seconds:
            try:
                datagram, _ = sock.recvfrom(protocol.MAX_DATAGRAM)
            except socket.timeout:
                continue
            parsed = protocol.defragment(datagram)
            if parsed is None:
                continue
            frame_id, total, seq, _, timestamp, payload = parsed
            received_packets += 1
            if args.loss > 0 and np.random.random() < args.loss:
                continue
            entry = frames.setdefault(frame_id, [total, {}, timestamp, time.time()])
            entry[1][seq] = payload
            if len(entry[1]) == total:
                data = b"".join(entry[1][i] for i in range(total))
                if save_image(data, image_path) is not None:
                    displayed += 1
                    delays.append(int(time.time() * 1000) - entry[2])
                del frames[frame_id]
            expired = [key for key, value in frames.items() if time.time() - value[3] > 0.5]
            for key in expired:
                del frames[key]
                lost += 1
        sock.close()

    elapsed = max(time.time() - start, 0.001)
    average_delay = sum(delays) / len(delays) if delays else 0
    print("场景: %s" % args.name)
    print("协议: %s" % args.protocol.upper())
    print("采集时长: %.1f 秒" % elapsed)
    print("显示帧数: %d" % displayed)
    print("显示帧率: %.2f fps" % (displayed / elapsed))
    print("收到UDP数据包: %d" % received_packets)
    print("平均端到端时延: %.2f ms" % average_delay)
    print("超时丢帧: %d" % lost)
    print("接收画面: %s" % os.path.abspath(image_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["udp", "tcp"], required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--seconds", type=float, default=6)
    parser.add_argument("--loss", type=float, default=0)
    parser.add_argument("--output", default=".")
    parser.add_argument("--name", required=True)
    main(parser.parse_args())
