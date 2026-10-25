# -*- coding: utf-8 -*-
"""
peripheral-battery: local battery bridge for wireless peripherals.

Currently supported devices:
  1. Inphic 2.4G wireless mice (e.g. Inphic KP 8K)
     - connects to the official Inphic driver bridge (ws://localhost:10085,
       installed with the Inphic HUB WEB driver) and parses pushed
       device-status packets. Protocol reverse-engineered from
       hub.inphic.cn.
     - /battery -> {"device_id":147,"connection":130,"level":66,
                    "status":"discharging","age_seconds":3}
  2. Flydigi classic-protocol gamepads via 2.4G dongle (e.g. Vader 2 Pro)
     - polls the dongle vendor HID interface (VID 0x04B4 / PID 0x2412,
       interface #2) with the GET_DEVICE_INFO (0x05/0xEC) command every
       60s. Protocol documented by flydigictl and SDL's flydigi driver.
       NOTE: the reported value is a battery-voltage byte, so the
       percentage is a linear estimate that reads ~100% during most of
       the high-voltage plateau of a Li-ion cell. Trust low readings.
     - /gamepad -> {"ok":true,"device_id":22,"level":100,"raw":114,
                    "age_seconds":32.1}

Packet protocol (Inphic, hex strings pushed over the WS bridge):
  e.g. "82010393400142"
  - length 7: b[0]=connection(128..133), b[1]=1, b[3]=deviceId,
              b[4] must be 0x40/0x41, b[5]=battery status, b[6]=battery level
  - length 6: b[0]=connection(128..133), b[1]=1, b[2]=deviceId,
              b[3] must be 0x40/0x41, b[4]=battery status, b[5]=battery level
  Battery status: 1 = discharging, 2 = full, 3 = charging

HTTP API (both endpoints, plus "/" returning everything):
  GET http://127.0.0.1:8712/battery
  GET http://127.0.0.1:8712/gamepad

Requires: pip install pywinusb websocket-client
"""

import ctypes
import faulthandler
import json
import os
import sys
import threading
import time
import traceback
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pywinusb.hid as hid
import websocket

WS_URL = "ws://localhost:10085"
HTTP_HOST, HTTP_PORT = "127.0.0.1", 8712
LOG_FILE = __file__.rsplit(".", 1)[0] + ".log"

# Flydigi classic protocol (black warrior 2 Pro / Vader 2 Pro family)
GAMEPAD_VID, GAMEPAD_PID = 0x04B4, 0x2412  # dongle in DInput/vendor mode
GAMEPAD_BATT_MIN, GAMEPAD_BATT_MAX = 98, 114  # voltage-byte calibration (flydigictl)

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
    "gamepad": {"ok": False, "device_id": None, "level": None,
                "raw": None, "updated": None},
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


# ---------------- Flydigi gamepad (Vader 2 Pro family) ----------------

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_RW = 3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p),
                ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]


_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.CreateEventW.restype = wintypes.HANDLE
_k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED)]
_k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(_OVERLAPPED)]
_k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(_OVERLAPPED),
                                     ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
_k32.CancelIo.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def _gamepad_open():
    devs = hid.HidDeviceFilter(vendor_id=GAMEPAD_VID, product_id=GAMEPAD_PID).get_devices()
    path = next((d.device_path for d in devs if "&mi_02" in d.device_path.lower()), None)
    if path is None:
        return None
    h = _k32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW,
                         None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if h in (None, 0, 0xFFFFFFFFFFFFFFFF):
        return None
    return h


def _overlapped_xfer(fn, h, buf, timeout_ms):
    got = wintypes.DWORD(0)
    ov = _OVERLAPPED()
    ov.hEvent = _k32.CreateEventW(None, True, False, None)
    ok = fn(h, buf, len(buf), ctypes.byref(got), ctypes.byref(ov))
    if not ok and ctypes.get_last_error() == 997:  # ERROR_IO_PENDING
        if _k32.WaitForSingleObject(ov.hEvent, timeout_ms) != 0:
            _k32.CancelIo(h)
            return None
        if not _k32.GetOverlappedResult(h, ctypes.byref(ov), ctypes.byref(got), False):
            return None
    elif not ok:
        return None
    return bytes(buf[:got.value])


def gamepad_poll_once():
    """One GET_DEVICE_INFO (0x05/0xEC) round-trip on the dongle vendor interface."""
    h = _gamepad_open()
    if h is None:
        with lock:
            state["gamepad"] = {"ok": False, "device_id": None, "level": None,
                                "raw": None, "updated": None}
        return
    try:
        t0 = time.time()
        while time.time() - t0 < 0.3:  # drain the input stream briefly
            if not _overlapped_xfer(_k32.ReadFile, h, (ctypes.c_ubyte * 64)(), 100):
                break

        wbuf = (ctypes.c_ubyte * 64)()
        wbuf[0], wbuf[1] = 0x05, 0xEC  # report id 5, GET_DEVICE_INFO
        if not _overlapped_xfer(_k32.WriteFile, h, wbuf, 1000):
            raise OSError("write failed")

        deadline = time.time() + 3
        while time.time() < deadline:
            data = _overlapped_xfer(_k32.ReadFile, h, (ctypes.c_ubyte * 64)(), 1000)
            if not data:
                continue
            if len(data) >= 16 and data[15] == 0xEC:
                raw = data[11]
                raw_c = max(GAMEPAD_BATT_MIN, min(GAMEPAD_BATT_MAX, raw))
                pct = round(100 * (raw_c - GAMEPAD_BATT_MIN) / (GAMEPAD_BATT_MAX - GAMEPAD_BATT_MIN))
                with lock:
                    state["gamepad"] = {"ok": True, "device_id": data[3], "level": pct,
                                        "raw": raw, "updated": time.time()}
                log(f"gamepad info: deviceID={data[3]} battery_raw={raw} (~{pct}%)")
                return
        log("gamepad info: no response")
        with lock:
            state["gamepad"] = {"ok": False, "device_id": None, "level": None,
                                "raw": None, "updated": None}
    finally:
        _k32.CloseHandle(h)


def gamepad_thread():
    while True:
        try:
            gamepad_poll_once()
        except Exception as e:
            log(f"gamepad poll error: {e}")
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/battery", "/gamepad", "/"):
            self.send_error(404)
            return
        with lock:
            snap = dict(state)
            gp = dict(snap["gamepad"])
        gp_age = None if gp["updated"] is None else round(time.time() - gp["updated"], 1)
        gamepad = {
            "ok": gp["ok"],
            "device_id": gp["device_id"],
            "level": gp["level"],
            "raw": gp["raw"],
            "age_seconds": gp_age,
        }
        if self.path == "/gamepad":
            body = json.dumps(gamepad, ensure_ascii=False).encode("utf-8")
        else:
            age = None if snap["updated"] is None else round(time.time() - snap["updated"], 1)
            body = json.dumps({
                "ok": snap["level"] is not None,
                "device_id": snap["device_id"],
                "connection": snap.get("connection_text"),
                "level": snap["level"],
                "status": snap["status_text"],
                "age_seconds": age,
                "gamepad": gamepad,
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
    threading.Thread(target=gamepad_thread, daemon=True, name="gamepad").start()
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
