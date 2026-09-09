"""
test_api.py — GLM API 连通性自检

1. 纯文本对话测试（验证 Key 有效）
2. 视觉测试（生成一张测试图，验证 glm-4v-flash 可用）

用法: py test_api.py
"""

import base64
import sys

import cv2
import numpy as np

import brain_api
import config


def main():
    if "填入" in config.API_KEY:
        print("请先在 config.py 填入 API Key")
        sys.exit(1)
    print("Key: %s...%s" % (config.API_KEY[:6], config.API_KEY[-4:]))

    print("\n[1/2] 文本对话测试（主力 %s，无资源包自动回退 %s）..."
          % (config.TEXT_MODEL, config.TEXT_FALLBACK))
    try:
        resp = brain_api.chat_complete(
            [{"role": "user", "content": "回复两个字：正常"}])
        print("回答:", resp.choices[0].message.content.strip())
    except Exception as e:
        print("文本测试失败:", e)
        sys.exit(1)

    print("\n[2/2] 视觉模型测试 (%s) ..." % config.VISION_MODEL)
    img = np.full((240, 320, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (80, 60), (240, 180), (0, 220, 80), -1)
    cv2.putText(img, "TEST 123", (70, 130),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
    try:
        answer = brain_api.ask_vision(img, "图中是什么颜色和文字？用一句中文回答")
        print("回答:", answer)
    except Exception as e:
        print("视觉测试失败:", e)
        sys.exit(1)

    print("\n全部通过！API 就绪。")


if __name__ == "__main__":
    main()