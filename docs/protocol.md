# 协议笔记：英菲克 2.4G 鼠标

英菲克网页驱动（hub.inphic.cn）**不直接读硬件**，而是连接官方驱动 `Inphic.exe` 在 `ws://localhost:10085` 提供的 WebSocket 桥接服务。该服务**主动推送**（约每 2 秒一帧）十六进制文本状态报文：

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
- 设备 ID 示例：147 = IN10 系列（KP 8K）

逆向方法：下载网页驱动的 JS bundle，从中提取 `batteryStatus` 相关的解析逻辑与 WebSocket 地址。

## 本地 HTTP 接口

服务把解析结果缓存到磁盘（`battery_cache.json`，与可执行文件同目录），启动时先加载，避免开机时序导致前端拿到空值。

`GET http://127.0.0.1:8712/battery`

```json
{
  "ok": true,
  "device_id": 147,
  "connection": "wired-8k",
  "level": 90,
  "status": "discharging",
  "age_seconds": 2.0,
  "source": "live",
  "stale": false
}
```

| 字段 | 说明 |
| --- | --- |
| `level` | 电量百分比（0–100） |
| `status` | `discharging` / `charging` / `full` |
| `age_seconds` | 距该读数产生的秒数（缓存值会明显偏大） |
| `source` | `live` 实时数据 / `cache` 上次已知值 |
| `stale` | `source != "live"` 时为 `true`，表示读数是旧的 |

缓存写入策略：数值变化时立即落盘，否则最多每 60 秒写一次；超过 7 天的缓存不再加载。

调试用环境变量：`PB_HTTP_PORT`（默认 8712）、`PB_WS_URL`（默认 `ws://localhost:10085`）。
