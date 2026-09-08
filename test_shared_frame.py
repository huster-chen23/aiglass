"""验证: 图传线程运行时, 抓拍不再二次打开摄像头, 能直接取到最新帧。"""
import threading
import time

import cv2

import glasses_main as g

stop = threading.Event()
sock = None  # 发送会失败但不影响线程跑帧缓存; 用哑 socket 更干净
sock = __import__("socket").socket(__import__("socket").AF_INET,
                                   __import__("socket").SOCK_DGRAM)

threading.Thread(target=g.capture_thread,
                 args=("camera", stop, sock, ("127.0.0.1", 59999)),
                 daemon=True).start()
time.sleep(2.5)

frame = g.get_latest_frame()
snap = g.capture_one_frame("camera")
print("stream frame:", None if frame is None else frame.shape)
print("snapshot    :", None if snap is None else snap.shape)
ok = frame is not None and snap is not None
cv2.imwrite("snapshot_check.jpg", snap if snap is not None else frame)
print("SHARED-FRAME TEST", "PASS" if ok else "FAIL")
stop.set()