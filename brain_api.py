"""
brain_api.py — AI 大脑（GLM API 接入）+ 本地语音播报

视觉问答：抓拍帧 -> GLM-4V-Flash 多模态 API -> 结果文本
语音播报：pyttsx3 本地 TTS（Windows SAPI5，离线免费）
"""

import base64
import threading

import cv2

import config

_client = None
_speak_lock = threading.Lock()


def get_client():
    """懒加载智谱客户端；Key 未配置时给出明确提示。"""
    global _client
    if _client is None:
        if not config.API_KEY or "填入" in config.API_KEY:
            raise SystemExit("请先在 config.py 填入 API Key，或设置环境变量 ZHIPU_API_KEY")
        from zhipuai import ZhipuAI
        _client = ZhipuAI(api_key=config.API_KEY)
    return _client


def ask_vision(frame_bgr, question="用一句简短中文说明画面里有什么"):
    """把一帧 BGR 图发给 GLM 视觉模型，返回回答文本。"""
    ok, buf = cv2.imencode(".jpg", frame_bgr,
                           [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return "图像编码失败"
    b64 = base64.b64encode(buf.tobytes()).decode()
    resp = get_client().chat.completions.create(
        model=config.VISION_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + b64}},
                {"type": "text", "text": question},
            ],
        }],
    )
    return resp.choices[0].message.content.strip()


def speak(text):
    """本地 TTS 播报（后台线程，避免阻塞图传）。"""
    def _run():
        with _speak_lock:  # 防止多句话重叠
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty("rate", config.TTS_RATE)
                engine.say(text)
                engine.runAndWait()
                engine.stop()
            except Exception as e:
                print("[TTS 失败]", e)
    threading.Thread(target=_run, daemon=True).start()
