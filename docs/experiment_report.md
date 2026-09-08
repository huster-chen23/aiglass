# 基于 UDP 的 AR/VR 画面实时串流通信仿真

## 一、实验目的

本实验模拟 VR 渲染主机向 AR/VR 头显实时传输画面的过程，重点观察 UDP 在实时视频通信中的低延迟特点，以及丢包对画面质量的影响，并使用 TCP 进行对照。

## 二、系统设计

系统由服务端、网络和客户端组成。服务端使用 Pillow 或 mss 捕获屏幕，使用 OpenCV 将每帧压缩为 JPEG。由于一张 JPEG 图片可能超过 UDP 数据报安全大小，`protocol.py` 为每帧添加帧编号、分片总数、分片序号和时间戳，将其拆成多个 UDP 数据包。客户端收到数据后按帧编号和序号重组，调用 OpenCV 解码显示，并计算帧率和端到端时延。

TCP 模式使用 4 字节长度前缀解决 TCP 字节流的分帧问题。它保证数据可靠到达，但网络丢包时可能等待重传。

## 三、实验环境

- Windows 11
- Python 3.11.9
- OpenCV 4.13.0
- Pillow 屏幕捕获
- 帧率：20 fps
- JPEG 质量：60
- 屏幕缩放：0.5，接收画面约 960×540

## 四、真实运行结果

以下数据由真实屏幕捕获和实际 UDP/TCP 传输程序采集，运行时长约 5 秒。

| 实验 | 协议 | 条件 | 显示帧数 | 实际帧率 | 平均时延 | 现象 |
|---|---|---|---:|---:|---:|---|
| UDP 正常 | UDP | 丢包模拟 0% | 99 | 19.64 fps | 3.95 ms | 画面连续 |
| UDP 丢包 | UDP | 应用层随机丢包 50% | 48 | 9.56 fps | 4.02 ms | 约一半帧丢失、画面跳帧 |
| TCP 对照 | TCP | 无应用层丢包 | 98 | 19.51 fps | 未测 | 数据可靠、画面连续 |

TCP 本次程序未在帧中嵌入发送时间戳，因此客户端显示的 TCP 时延统计为 0；实际对比重点是可靠性和帧率。UDP 的时延由服务端时间戳和客户端接收时间计算。

## 五、图片和日志

- `real_udp_normal_received.jpg`：真实 UDP 正常接收画面
- `real_udp_loss_received.jpg`：真实 UDP 丢包实验接收画面
- `real_tcp_received.jpg`：真实 TCP 对照接收画面
- `real_udp_normal_client.log`：UDP 正常客户端数据
- `real_udp_loss_client.log`：UDP 丢包客户端数据
- `real_tcp_client.log`：TCP 客户端数据
- 对应的 `*_server.log`：服务端真实发送日志

## 六、实验结论

正常网络下，UDP 和 TCP 都能达到约 20 fps。模拟 50% 丢包后，UDP 显示帧率下降到约 9.56 fps，但接收端不会等待丢失帧的重传，仍能继续播放后续画面。TCP 通过重传保证数据完整性，但在丢包和高时延网络中可能出现队头阻塞和卡顿。AR/VR 画面更重视实时性，因此 UDP 更适合作为底层传输协议，并可在应用层增加关键帧、丢帧策略或前向纠错。

## 七、运行命令

```powershell
py -m pip install opencv-python numpy pillow
py server.py --source screen --protocol udp --port 9000 --fps 20 --quality 60 --scale 0.5
py client.py --protocol udp --host 127.0.0.1 --port 9000
```

无图形窗口时：

```powershell
py client.py --protocol udp --port 9000 --headless
```

TCP 对照：

```powershell
py server.py --source screen --protocol tcp --port 9001 --fps 20 --quality 60 --scale 0.5
py client.py --protocol tcp --host 127.0.0.1 --port 9001 --headless
```

Mininet 进阶实验需要 Linux/Ubuntu：

```bash
sudo python3 mininet_topology.py --delay 20ms --loss 5
```

## 八、系统局限与改进

当前实现采用整帧 JPEG，丢失任意一个分片会导致该帧丢弃；后续可以加入帧确认、选择性重传、关键帧和 FEC。TCP 时延测量还可以加入统一时间戳，以便和 UDP 做更完整的端到端延迟比较。
