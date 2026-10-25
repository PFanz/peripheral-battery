# 协议笔记

本文记录两个电量数据源的报文格式，供二次开发参考。

## 1. 英菲克 2.4G 鼠标（逆向自 hub.inphic.cn 网页驱动）

英菲克网页驱动**不直接读硬件**，而是连接官方驱动 `Inphic.exe` 在 `ws://localhost:10085` 提供的 WebSocket 桥接服务。该服务**主动推送**（约每 2 秒一帧）十六进制文本状态报文：

```
例：82010393400142
```

| 帧长 | b[0] 连接方式 | 设备 ID | 校验字节 | 电池状态 | 电量 |
| --- | --- | --- | --- | --- | --- |
| 7 | 128–133 | b[3] | b[4] ∈ {0x40, 0x41} | b[5] | b[6] |
| 6 | 128–133 | b[2] | b[3] ∈ {0x40, 0x41} | b[4] | b[5] |

- 电池状态：`1` 放电中，`2` 满电，`3` 充电中
- 电量为 0–100 直读百分比
- 连接方式实测：129/132 = 无线，130/131/133 = 8K 有线

逆向方法：下载网页驱动的 JS bundle，从中提取 `batteryStatus` 相关的解析逻辑与 WebSocket 地址。

## 2. 飞智经典协议手柄（黑武士 2 Pro 等）

接收器处于厂商模式时以 `VID 0x04B4 / PID 0x2412` 枚举，协议位于 **interface #2**（MI_02）。

查询设备信息：

- **写**：12 字节 output report `[0x05, 0xEC, 0x00, ...]`（0xEC = GET_DEVICE_INFO）
- **读**：32 字节 input report，当 `p[15] == 0xEC` 时为设备信息响应：

| 字节 | 含义 |
| --- | --- |
| p[3] | 设备 ID（22/23 = 黑武士 2 Pro） |
| p[5:9] | MAC |
| p[9], p[10] | 固件版本 L/H |
| p[11] | **电池原始值**（电压 ADC 读数） |
| p[12] | CPU 类型（>0 = WCH） |
| p[13] | 连接类型（1 = 有线） |

电量换算（来自 flydigictl，常量名 `apex2MinBY`/`apex2MaxBY`）：

```go
clamp(battery, 98, 114)
percent = 100 * (battery - 98) / 16
```

**注意**：这是电池电压的线性映射，不是电量计。锂电在 ~4.1–4.2V 平台期（约前 1/3 放电过程）电压几乎不变，因此会长时间显示接近 100%。低电量段（电压明显跌落之后）数值才有较好的参考价值。

## 参考

- <https://github.com/pipe01/flydigictl>（`pkg/flydigi/protocol/dinput/dinput.go`、`pkg/flydigi/gamepad.go`）
- <https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_flydigi.c>
