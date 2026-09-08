'''
config.py — 全局配置（公开仓库安全版）
真实 API Key 放在 config_local.py（已被 .gitignore 忽略，不会上传）
或设置环境变量 ZHIPU_API_KEY
'''
import os

# 优先级：环境变量 ZHIPU_API_KEY > config_local.py > 留空
API_KEY = os.environ.get("ZHIPU_API_KEY", "")

try:
    from config_local import API_KEY as _LOCAL_KEY  # noqa: F401
    API_KEY = API_KEY or _LOCAL_KEY
except ImportError:
    pass

# 视觉对话模型（glm-4v-flash 免费）
VISION_MODEL = "glm-4v-flash"

# UDP 图传参数（与课程实验一致）
PC_IP = "127.0.0.1"
STREAM_PORT = 9500   # 图传端口（眼镜 -> 显示屏）
RESULT_PORT = 9501   # AI 结果字幕端口（眼镜 -> 显示屏）
FPS = 15
JPEG_QUALITY = 55
CAPTURE_SCALE = 0.5

# 语音
TTS_RATE = 180       # 语速（词/分）
