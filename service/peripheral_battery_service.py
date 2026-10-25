# -*- coding: utf-8 -*-
"""
peripheral-battery: local battery bridge for the Inphic 2.4G wireless mouse.

Connects to the Inphic driver bridge (ws://localhost:10085, installed with
the Inphic HUB WEB driver), parses pushed device-status packets, and exposes
the battery level over a tiny local HTTP API for LiteMonitor.

Packet protocol (reverse-engineered from hub.inphic.cn web driver):
  Status messages arrive as hex strings, e.g. "82010393400142"
  - length 7: b[0]=connection(128..133), b[1]=1, b[3]=deviceId,
              b[4] must be 0x40/0x41, b[5]=battery status, b[6]=battery level
  - length 6: b[0]=connection(128..133), b[1]=1, b[2]=deviceId,
              b[3] must be 0x40/0x41, b[4]=battery status, b[5]=battery level
  Battery status: 1 = discharging, 2 = full, 3 = charging

HTTP API:
  GET http://127.0.0.1:8712/battery
  -> {"ok":true,"device_id":147,"connection":"wired-8k","level":66,
      "status":"discharging","age_seconds":3}

Requires: pip install websocket-client
"""

import faulthandler
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websocket

WS_URL = "ws://localhost:10085"
HTTP_HOST = "127.0.0.1"
HTTP_PORT = int(os.environ.get("PB_HTTP_PORT", "8712"))  # override for tests
if getattr(sys, "frozen", False):
    # PyInstaller: put the log next to the real exe, not the temp extraction dir
    _APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(_APP_DIR, "peripheral_battery_service.log")

# Capture hard crashes (C-level) and uncaught exceptions to the log file.
_fault_stream = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
faulthandler.enable(_fault_stream)


def _sys_hook(tp, val, tb):
    log("UNCAUGHT EXCEPTION:\n" + "".join(traceback.format_exception(tp, val, tb)))


sys.excepthook = _sys_hook


def _thread_hook(args):
    log(f"THREAD CRASH [{args.thread.name}]:\n"
        + "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


threading.excepthook = _thread_hook

lock = threading.Lock()
state = {
    "device_id": None,
    "connection": None,
    "level": None,
    "status": None,
    "status_text": None,
    "updated": None,
}

STATUS_TEXT = {1: "discharging", 2: "full", 3: "charging"}
CONNECTION_TEXT = {128: "wired", 129: "wireless", 130: "wired-8k",
                   131: "wired-8k", 132: "wireless", 133: "wired-8k"}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def parse_message(raw):
    """Parse a hex-string status packet, update global state."""
    try:
        b = bytes.fromhex(raw.strip())
    except ValueError:
        return
    dev = stat = level = None
    if len(b) == 7 and 128 <= b[0] <= 133 and b[1] == 1 and b[4] in (0x40, 0x41):
        dev, stat, level = b[3], b[5], b[6]
        conn = b[0]
    elif len(b) == 6 and 128 <= b[0] <= 133 and b[1] == 1 and b[3] in (0x40, 0x41):
        dev, stat, level = b[2], b[4], b[5]
        conn = b[0]
    else:
        return
    if not (0 <= level <= 100):
        return
    with lock:
        state.update({
            "device_id": dev,
            "connection": conn,
            "connection_text": CONNECTION_TEXT.get(conn, str(conn)),
            "level": level,
            "status": stat,
            "status_text": STATUS_TEXT.get(stat, str(stat)),
            "updated": time.time(),
        })
    log(f"packet {raw!r} -> device={dev} conn={conn} status={stat} level={level}%")


def on_message(ws, raw):
    try:
        parse_message(raw)
    except Exception as e:  # never let one bad packet kill the loop
        log(f"parse error: {e}")


def on_open(ws):
    log("ws connected")


def on_close(ws, code, reason):
    log(f"ws closed: {code} {reason}")


def heartbeat():
    """Log a line every 120s so a silent death has a timestamp boundary."""
    while True:
        time.sleep(120)
        with lock:
            lvl = state["level"]
        log(f"heartbeat alive, last level={lvl}")


def on_error(ws, err):
    log(f"ws error: {err}")


def ws_thread():
    while True:
        try:
            ws = websocket.WebSocketApp(
                WS_URL,
                on_message=on_message,
                on_error=on_error,
                on_open=on_open,
                on_close=on_close,
            )
            ws.run_forever(reconnect=5, ping_interval=20, ping_timeout=10)
        except Exception as e:
            log(f"ws crashed: {e}")
        log("ws reconnecting in 5s")
        time.sleep(5)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/battery", "/"):
            self.send_error(404)
            return
        with lock:
            snap = dict(state)
        age = None if snap["updated"] is None else round(time.time() - snap["updated"], 1)
        body = json.dumps({
            "ok": snap["level"] is not None,
            "device_id": snap["device_id"],
            "connection": snap.get("connection_text"),
            "level": snap["level"],
            "status": snap["status_text"],
            "age_seconds": age,
        }, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # keep quiet


if __name__ == "__main__":
    log(f"service starting (pid={os.getpid()})")
    threading.Thread(target=ws_thread, daemon=True, name="ws").start()
    threading.Thread(target=heartbeat, daemon=True, name="hb").start()
    server = None
    for attempt in range(30):
        try:
            server = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), Handler)
            break
        except OSError as e:
            log(f"bind attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    if server is None:
        log("FATAL: could not bind HTTP port, exiting")
        raise SystemExit(1)
    log(f"HTTP listening on {HTTP_HOST}:{HTTP_PORT}")
    try:
        server.serve_forever()
    except Exception as e:
        log(f"server error: {e}")
    finally:
        log("service stopped")
