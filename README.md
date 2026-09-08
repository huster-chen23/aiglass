# 单人 AI 眼镜 · 软件仿真版（GLM API 接入）

在你的电脑上用纯软件方式模拟 AI 眼镜闭环，AI 能力通过智谱 GLM API 接入。

## 架构（对应真实硬件的软件替身）

```
[眼镜端 glasses_main.py]                    [接收端 display_main.py]
 摄像头/屏幕捕获 ──UDP图传(protocol)──>  窗口实时显示第一视角
 空格/回车=镜腿按键                                ↑
      ↓                                     UDP JSON 结果
 抓拍帧 → GLM-4V-Flash API → 结果文本 ──────────┘（画面叠加字幕）
      ↓
 pyttsx3 本地语音播报（=骨传导耳机）
```

## 快速开始

1. 安装依赖：

```powershell
py -m pip install opencv-python numpy zhipuai pyttsx3
```

2. 把你的智谱 API Key 填入 `config.py`（或设置环境变量 `ZHIPU_API_KEY`）。
   Key 获取：https://open.bigmodel.cn → 控制台 → API Key。`glm-4v-flash` 视觉模型免费。

3. 测试 API 连通：

```powershell
py test_api.py
```

4. 窗口 1 启动接收端（=眼镜显示屏）：

```powershell
py display_main.py
```

5. 窗口 2 启动眼镜端（=眼镜本体）：

```powershell
py glasses_main.py
```

- 画面会实时出现在接收端窗口（UDP 图传，复用课程实践的 protocol.py）
- 在眼镜端窗口按 `v`：抓拍一帧 → GLM 视觉 API 识别 → 语音播报 + 接收端字幕
- 在眼镜端终端输入问题后回车：带问题的视觉问答
- 按 `q` 退出

## 远程模式：跨互联网通信

默认是本机直连。要跨互联网（两边在任何网络下），需要一个公网中继：

**方式一：云服务器部署中继（推荐，任意云主机均可）**

```bash
# 在 VPS 上（放行 UDP 9600 端口）
py relay_server.py --port 9600
```

```powershell
# 眼镜端（任何网络）
py glasses_main.py --relay VPS公网IP:9600 --room demo
# 显示端（任何网络，可多台同时观看=直播模式）
py display_main.py --relay VPS公网IP:9600 --room demo
```

原理：两端都主动向中继注册（NAT 映射由客户端发起打开），中继按房间把发送端的数据转发给同房间所有观看端——所以**两边都在家庭路由器/NAT 后面也能通**。

**方式二：内网穿透（无服务器时临时用）**：frp / 花生壳把本机 9500/9501 映射到公网，眼镜端 `--relay 公网地址` 即可。

## 规模化：从 1 对 1 到万级 AR/VR 用户

当前中继是单进程转发，验证协议可行。支撑成千上万用户需要三级演进（答辩重点）：

| 阶段 | 架构 | 容量 | 关键技术 |
|---|---|---|---|
| v1 现在 | 单中继、房间制、1 发 N 收 | 单机数百观看端 | UDP 房间注册/心跳/转发 |
| v2 百级 | 多中继 + 房间调度服务 | 数千 | Redis 房间路由、负载均衡、按房间分配中继节点 |
| v3 万级 | 树形分发（SFU 思路）+ 边缘节点 | 数万~十万 | 观看端也可下沉为二级转发节点；WebRTC/QUIC 标准化；边缘 CDN 就近接入 |

带宽账本（答辩常问）：单路 20fps × 50KB ≈ 8Mbps；1000 个观看端直连单服务器 = 8Gbps 出口——**单机不可能**，所以万级用户的答案必须是"房间化 + 树形分发 + 边缘就近"，这正是直播平台和 WebRTC SFU 的做法。

## 文件说明

| 文件 | 作用 | 对应真实硬件 |
|---|---|---|
| `protocol.py` | UDP 分片协议（课程实践复用） | WiFi 传输 |
| `relay_server.py` | 跨互联网房间制中继服务器（部署到公网 VPS） | 边缘转发节点 |
| `glasses_main.py` | 眼镜端主程序：捕获+图传+按键+AI（支持直连/中继） | 眼镜本体 |
| `display_main.py` | 接收端：显示第一视角+AI 字幕（支持直连/中继，可多端观看） | 眼镜显示屏 |
| `brain_api.py` | GLM 视觉问答 + 本地 TTS 播报 | 端侧 AI 芯片 + 耳机 |
| `config.py` | API Key 与参数配置 | — |
| `test_api.py` | API 连通性自检 | — |

## 硬件迁移路径（阶段二）

软件闭环稳定后，按映射逐个替换，协议不动：

| 软件替身 | 换成 |
|---|---|
| PC 摄像头 | 手机/树莓派 USB 摄像头 |
| OpenCV 窗口 | 单目 OLED / 手机屏幕 |
| 键盘按键 | 镜腿物理按键 |
| PC 音箱 | 骨传导耳机 |

## AR 信息叠加模式（HUD）

```powershell
py ar_overlay.py                 # 摄像头 AR HUD
py ar_overlay.py --source screen # 屏幕模式
```

持续检测画面物体（YOLOv8n，自动降级 Haar 人脸），钢铁侠式四角框 + 标签 + 系统面板。
按键：`d` 开关检测 · `n` GLM 识别当前场景并语音播报 · `s` 截图 · `q` 退出。

## API Key 安全说明

真实 Key 放在 `config_local.py`（已被 .gitignore 忽略）或环境变量 `ZHIPU_API_KEY`，
`config.py` 只保留占位逻辑，可安全公开。
