import socket
import json
import time

A = ("127.0.0.1", 9600)


def reg(sock, role, name):
    sock.sendto(b"REG|" + json.dumps(
        {"room": "demo", "role": role, "name": name}).encode(), A)
    data, _ = sock.recvfrom(4096)
    return json.loads(data[4:].decode())


v = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
v.bind(("0.0.0.0", 0))
v.settimeout(5)
print("viewer ACK:", reg(v, "viewer", "test-viewer"))

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 0))
s.settimeout(5)
print("sender ACK:", reg(s, "sender", "test-glasses"))
for i in range(3):
    s.sendto(("frame-%d" % i).encode(), A)
    time.sleep(0.1)

got = []
try:
    while len(got) < 3:
        d, _ = v.recvfrom(65535)
        got.append(d.decode())
except socket.timeout:
    pass
print("viewer received:", got)
print("RELAY TEST", "PASS" if len(got) == 3 else "FAIL")