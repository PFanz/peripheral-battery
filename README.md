# peripheral-battery

本机外设电量桥接服务 + [LiteMonitor](https://github.com/Diorser/LiteMonitor) 插件。

通过一个轻量本地 HTTP 服务，把**没有系统级电量上报**的无线外设（目前支持英菲克 2.4G 鼠标、飞智经典协议手柄）的电量读出来，供 LiteMonitor 或任何能拉 JSON 的工具显示。

A tiny local HTTP service that exposes battery levels of wireless peripherals that Windows itself cannot see (Inphic 2.4G mice, Flydigi classic-protocol gamepads), plus ready-to-use LiteMonitor plugins.

## 显示效果

```
鼠标 61%    手柄 100%
```

- 每 60 秒自动刷新
- 电量 < 20% 变黄、< 10% 变红；鼠标充电时显示 ⚡

## 支持的设备

| 设备 | 数据来源 | 精度 |
| --- | --- | --- |
| 英菲克 2.4G 无线鼠标（KP 8K 等，VID 1D57） | 英菲克官方驱动的本地 WebSocket 桥接（逆向自 hub.inphic.cn） | 直读百分比，准确 |
| 飞智经典协议手柄（黑武士 2 Pro 等，接收器 VID 04B4/PID 2412） | 接收器厂商 HID 接口，GET_DEVICE_INFO (0xEC) 命令 | 电压估算值，满电附近偏乐观，低电量段可靠 |

> 飞智手柄需将接收器置于厂商模式（DInput 枚举）。注意：协议上报的是电池电压原始值（98–114），按线性映射换算百分比，锂电池高压平台期会长时间显示 ~100%——把它当低电量预警用最合适。

## 安装

### 1. 运行服务

```bash
pip install pywinusb websocket-client
python service/peripheral_battery_service.py
```

- 英菲克鼠标：需安装 [英菲克 HUB WEB 驱动](https://hub.inphic.cn/)（其后台 `Inphic.exe` 提供电量数据）
- 飞智手柄：无需任何官方软件，直连接收器

验证：浏览器打开 <http://127.0.0.1:8712/battery> 与 <http://127.0.0.1:8712/gamepad>。

开机自启：把 `startup/peripheral_battery.vbs`（或自行创建的静默启动脚本）放入 `shell:startup` 文件夹。

### 2. 安装 LiteMonitor 插件

把 `plugins/` 下的两个 JSON 复制到 LiteMonitor 的 `resources/plugins/` 目录，重启 LiteMonitor，在插件设置中启用「鼠标电量」和「手柄电量」。

## 协议细节

见 [docs/protocol.md](docs/protocol.md)。

## 致谢

- [flydigictl](https://github.com/pipe01/flydigictl) — 飞智经典协议的完整逆向参考
- [SDL flydigi 驱动](https://github.com/libsdl-org/SDL/blob/main/src/joystick/hidapi/SDL_hidapi_flydigi.c) — 飞智 V2 协议官方实现
- [LiteMonitor](https://github.com/Diorser/LiteMonitor) — 桌面监控栏

## License

MIT
