"""
check_camera.py — 摄像头诊断：枚举索引 0-3、两种后端，逐一测试能否出画面。
用法: py check_camera.py
"""

import cv2

BACKENDS = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF)]

working = []
for index in range(4):
    for name, backend in BACKENDS:
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            print("index=%d %-5s : 打不开" % (index, name))
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            print("index=%d %-5s : [可用] (%dx%d)" % (index, name, w, h))
            working.append((index, name))
        else:
            print("index=%d %-5s : 打开但抓不到帧（可能被占用或是虚拟设备）"
                  % (index, name))
        cap.release()

print("\n结论:")
if working:
    for index, name in working:
        print("  可用: index=%d 后端=%s" % (index, name))
    print("  运行眼镜端时可指定: py glasses_main.py --cam-index %d"
          % working[0][0])
else:
    print("  没有可用摄像头。可能原因:")
    print("  1) 电脑没有摄像头（台式机常见）")
    print("  2) 摄像头被其他程序占用（会议软件/相机应用）")
    print("  3) Windows 设置 > 隐私和安全性 > 相机 未允许桌面应用访问")
    print("  目前可直接用屏幕捕获模式: py glasses_main.py --source screen")