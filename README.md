# peripheral-battery

本机英菲克无线鼠标电量桥接服务 + [LiteMonitor](https://github.com/Diorser/LiteMonitor) 插件。

英菲克 2.4G 无线鼠标（KP 8K 等）不在系统层上报电量，但其官方驱动在本地 `ws://localhost:10085` 推送含电量的状态报文（协议逆向自 [hub.inphic.cn](https://hub.inphic.cn) 网页驱动）。本项目解析该报文并通过一个轻量本地 HTTP 服务暴露出来，供 LiteMonitor 或任何能拉 JSON 的工具显示。

A tiny local service that parses battery packets pushed by the official Inphic driver (protocol reverse-engineered from the Inphic HUB WEB page) and exposes them over local HTTP, plus a ready-to-use LiteMonitor plugin.

## 显示效果

```
鼠标 61%
```

- 每 60 秒自动刷新
- 电量 < 20% 变黄、< 10% 变红；充电时显示 ⚡

## 安装

### 方式一：安装包（推荐，无需 Python）

从 [Releases](https://github.com/PFanz/peripheral-battery/releases) 下载：

- `peripheral-battery-setup.exe` — 自解压安装包，双击即完成：安装服务到 `%LOCALAPPDATA%\peripheral-battery`、注册开机自启（HKCU Run）、自动探测 LiteMonitor 并部署插件
- `peripheral-battery-portable-win64.zip` — 绿色便携版，解压后运行 `install.bat` / 卸载运行 `uninstall.bat`

安装后打开 LiteMonitor → 插件设置 → 启用「鼠标电量」即可。

### 方式二：从源码运行

```bash
pip install websocket-client
python service/peripheral_battery_service.py
```

前提：安装 [英菲克 HUB WEB 驱动](https://hub.inphic.cn/)——电量数据来自其后台进程 `Inphic.exe`（安装后默认开机自启），请勿卸载。

验证：浏览器打开 <http://127.0.0.1:8712/battery>。

开机自启（源码方式）：把 `startup/peripheral_battery.vbs`（按注释改好两个路径）放入 `shell:startup` 文件夹。

### 3. 安装 LiteMonitor 插件

把 `plugins/MouseBattery.json` 复制到 LiteMonitor 的 `resources/plugins/` 目录，重启 LiteMonitor，在插件设置中启用「鼠标电量」。

## 接口与缓存

`GET http://127.0.0.1:8712/battery` 返回：

```json
{"ok": true, "level": 90, "status": "discharging", "age_seconds": 1.4,
 "source": "live", "stale": false}
```

- `source` — `live`（来自驱动的实时报文）或 `cache`（来自磁盘缓存）
- `stale` — 非实时值为 `true`，用于区分「旧值」与「当前值」
- `age_seconds` — 该电量数据距上次更新的秒数

每次拿到实时值都会写入 `battery_cache.json`（与程序同目录）。服务重启、驱动重启或鼠标刚唤醒时，先用缓存里的最后一次电量应答，避免插件显示横杠；缓存超过 7 天视为失效。

## 协议细节

见 [docs/protocol.md](docs/protocol.md)。

## 打包与发布（维护者）

构建在 GitHub Actions 上完成，本地无需 Python 或 7-Zip：

```bash
git tag v1.0.0
git push origin v1.0.0
```

推送 `v*` tag 后，`.github/workflows/release.yml` 会在 `windows-latest` 上依次产出并在同名 Release 中发布：

| 文件 | 说明 |
| --- | --- |
| `peripheral-battery-setup.exe` | 自解压安装包（7-Zip SFX + `packaging/config.txt`） |
| `peripheral-battery-portable-win64.zip` | 绿色便携包（解压后运行 `install.bat`） |
| `peripheral_battery_service.exe` | 仅服务本体（PyInstaller 单文件） |
| `SHA256SUMS.txt` | 上述三个文件的 SHA-256 |

在 Actions 页面手动触发（Run workflow）只产出 artifact，不创建 Release。安装包未做代码签名，首次运行会出现 SmartScreen 提示。

本地手工构建（备用，需 PyInstaller 与 7-Zip）：

```bat
pyinstaller --onefile --noconsole --name peripheral_battery_service service/peripheral_battery_service.py
7z a payload.7z peripheral_battery_service.exe MouseBattery.json install.bat uninstall.bat PORTABLE_README.txt
copy /b "C:\Program Files\7-Zip\7z.sfx" + packaging\config.txt + payload.7z peripheral-battery-setup.exe
```

`packaging/` 目录含 install.bat / uninstall.bat / PORTABLE_README.txt / config.txt。

## 致谢

- [LiteMonitor](https://github.com/Diorser/LiteMonitor) — 桌面监控栏

## License

MIT
