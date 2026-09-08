# v1.1 手表互联（华为 GT5 → GTP/1.0 → HUD）

## 文件

| 文件 | 说明 |
|---|---|
| `gtp.py` | GTP/1.0 协议：帧编解码、CRC-16/MODBUS、增量节流器 |
| `test_gtp.py` | 协议单元测试（直接运行，全绿说明协议实现正确） |
| `ble_scan.py` | BLE 扫描：找 GT5 地址 + 探测它的 GATT 服务列表 |
| `watch_hr.py` | 主程序：`--sim` 模拟模式 / `--address` 真实模式 |

## 运行顺序

```bash
# 1. 协议单测（不需要手表）
py test_gtp.py

# 2. 模拟模式：假心率走完整 GTP 管线（不需要手表）
py watch_hr.py --sim --seconds 30

# 3. 手表充好电后：扫描找地址
py ble_scan.py

# 4. 真实模式：心率实时显示
py watch_hr.py --address XX:XX:XX:XX:XX:XX
```

## GT5 注意事项

- 手表上开启"连续心率测量"（设置 → 健康监测）
- 与手机运动健康 App 保持连接时通常仍可被扫描；扫不到就先断开手机蓝牙再试
- Windows 蓝牙需支持 BLE（近 5 年的笔记本都支持）
- 步数/血氧在华为私有服务里，v1.1 不承诺（见版本规划文档"风险与降级预案"）

## 与 HUD 的打通（下一步）

`watch_hr.py` 解析出的 bpm 通过 `gtp.encode_hr()` 打包后，
后续由主程序订阅串口/管道，接到 `ar_overlay.py` 左侧面板的 `HR` 行——
面板改造放在真实模式验证通过之后。
