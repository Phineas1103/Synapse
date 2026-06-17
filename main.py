# -*- coding: utf-8 -*-
"""Synapse - PyWebView entry point with license check"""

import sys
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(APP_DIR, "synapse.log")

# Add APP_DIR to PATH so bundled ffmpeg.exe is found
_env_path = os.environ.get('PATH', '')
if APP_DIR not in _env_path:
    os.environ['PATH'] = APP_DIR + os.pathsep + _env_path

class _NullStream:
    def write(self, *a, **kw): pass
    def flush(self): pass
    def isatty(self): return False
    def fileno(self): return -1
    def read(self, *a, **kw): return ""
    def readline(self, *a, **kw): return ""
    def readable(self): return True
    def writable(self): return False

if sys.stdin is None:
    sys.stdin = _NullStream()
if sys.stdout is None:
    sys.stdout = open(LOG_FILE, "a", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(LOG_FILE, "a", encoding="utf-8")

if sys.platform == "win32":
    import subprocess as _sp
    try:
        _si = _sp.STARTUPINFO()
        _si.dwFlags |= _sp.STARTF_USESHOWWINDOW
        _si.wShowWindow = 0
        _orig_Popen = _sp.Popen
        class _HiddenPopen(_orig_Popen):
            def __init__(self, *args, **kwargs):
                if "startupinfo" not in kwargs and "creationflags" not in kwargs:
                    kwargs["startupinfo"] = _si
                    kwargs["creationflags"] = 0x08000000
                super().__init__(*args, **kwargs)
        _sp.Popen = _HiddenPopen
    except Exception:
        pass

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import logging
import socket
import time
import threading
import ctypes
import ctypes.wintypes

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
log = logging.getLogger("synapse")

# Win32 constants
_user32 = ctypes.windll.user32
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 0x0002
SW_RESTORE = 9


def show_error(title, msg):
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x10)
    except Exception:
        pass
    log.error(f"{title}: {msg}")

def kill_port_process(port):
    try:
        result = __import__("subprocess").run(
            ["cmd.exe", "/c", f"netstat -ano | findstr :{port} | findstr LISTENING"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split("\n"):
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0:
                    __import__("subprocess").run(
                        ["cmd.exe", "/c", f"taskkill /F /PID {pid}"],
                        capture_output=True, timeout=10
                    )
        time.sleep(1)
    except Exception as e:
        log.warning(f"kill_port_process: {e}")

def wait_for_server(host, port, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect((host, port))
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.3)
    return False

def _find_hwnd_by_title(title_substr):
    """Find a visible window whose title contains the given substring."""
    hwnds = []

    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _enum_cb(hwnd, _):
        if _user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, buf, 256)
            if title_substr.lower() in buf.value.lower():
                hwnds.append(hwnd)
                return False
        return True

    _user32.EnumWindows(_enum_cb, 0)
    return hwnds[0] if hwnds else None

class Api:
    """PyWebView JS API - window controls for frameless mode."""
    def __init__(self):
        self._window = None
        self._hwnd = None

    def set_window(self, w):
        self._window = w

    def _ensure_hwnd(self):
        """Find and cache the window HWND."""
        if not self._hwnd:
            self._hwnd = _find_hwnd_by_title("Synapse")
            if not self._hwnd:
                self._hwnd = _find_hwnd_by_title("manju")
        return self._hwnd

    def minimize(self):
        hwnd = self._ensure_hwnd()
        if hwnd:
            _user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE

    def maximize(self):
        """Always maximize — window is fixed at fullscreen, no toggle."""
        hwnd = self._ensure_hwnd()
        if hwnd:
            _user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE

    def close(self):
        hwnd = self._ensure_hwnd()
        if hwnd:
            _user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        elif self._window:
            self._window.destroy()

    def start_move(self):
        """No-op — window is fixed and cannot be dragged."""
        return False

    def is_maximized(self):
        """Check if window is currently maximized."""
        hwnd = self._ensure_hwnd()
        if hwnd:
            return bool(_user32.IsZoomed(hwnd))
        return False

    def open_external_window(self, url):
        """Open a URL in a new pywebview window."""
        import webview
        def _open():
            try:
                webview.create_window(
                    'API中转站',
                    url,
                    width=1200,
                    height=800,
                    resizable=True,
                )
            except Exception as e:
                log.warning(f'open_external_window: {e}')
        threading.Thread(target=_open, daemon=True).start()


    def browse_folder(self, initial_dir=""):
        """Open a native folder picker dialog via pywebview."""
        import webview
        result = self._window.create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=initial_dir or '',
            allow_multiple=False
        )
        if result and len(result) > 0:
            return result[0]
        return ""

    def save_file_dialog(self, initial_dir="", initial_file="", file_types=None):
        """Open a native save file dialog via pywebview."""
        import webview
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=initial_dir or '',
            save_filename=initial_file or '漫剧成品.mp4',
            file_types=file_types or ('MP4视频 (*.mp4)', '所有文件 (*.*)')
        )
        if result and len(result) > 0:
            return result[0]
        return ""

    def export_poster_to_path(self, source_path, default_name="poster.png"):
        """弹出保存对话框，将海报图片复制到用户选择的路径。"""
        import shutil
        import webview
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name,
            file_types=('PNG图片 (*.png)', 'JPEG图片 (*.jpg)', '所有文件 (*.*)')
        )
        if not result or len(result) == 0:
            return {"success": False, "cancelled": True}
        dest_path = result[0]
        try:
            shutil.copy2(source_path, dest_path)
            return {"success": True, "path": dest_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def export_video_to_path(self, source_path, default_name="video.mp4"):
        """弹出保存对话框，将视频文件复制到用户选择的路径。"""
        import shutil
        import webview
        result = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=default_name,
            file_types=('MP4视频 (*.mp4)', '所有文件 (*.*)')
        )
        if not result or len(result) == 0:
            return {"success": False, "cancelled": True}
        dest_path = result[0]
        try:
            shutil.copy2(source_path, dest_path)
            return {"success": True, "path": dest_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # === License API (JS-Python bridge) ===
    def verify_license(self):
        """验证许可证状态，返回 {valid, message, expires_at, remaining_days}"""
        try:
            from license_client import verify, get_license_info, load_cache
            ok, msg = verify()
            info = get_license_info() or {}
            remaining = None
            if info.get("expires_at"):
                try:
                    from datetime import datetime
                    exp = datetime.fromisoformat(info["expires_at"])
                    remaining = max(0, (exp - datetime.now()).days)
                except:
                    pass
            return {
                "valid": ok,
                "message": msg,
                "expires_at": info.get("expires_at"),
                "remaining_days": remaining
            }
        except ImportError:
            return {"valid": True, "message": "无许可证模块", "expires_at": None, "remaining_days": None}
        except Exception as e:
            log.error(f"verify_license error: {e}")
            return {"valid": False, "message": str(e), "expires_at": None, "remaining_days": None}

    def activate_license(self, license_key):
        """激活卡密，返回 {success, message, expires_at}"""
        try:
            from license_client import activate
            ok, msg = activate(license_key)
            if ok:
                from license_client import get_license_info
                info = get_license_info() or {}
                return {"success": True, "message": msg, "expires_at": info.get("expires_at")}
            return {"success": False, "message": msg, "expires_at": None}
        except Exception as e:
            log.error(f"activate_license error: {e}")
            return {"success": False, "message": str(e), "expires_at": None}


def main():
    try:
        kill_port_process(18090)
    except Exception:
        pass

    # 直接启动主应用，激活流程在主窗口内通过JS-Python桥接完成
    start_main_app()


def start_main_app():
    """启动主应用"""
    from api_server import create_app
    app = create_app()

    import uvicorn

    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=18090, log_level="warning")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    if not wait_for_server("127.0.0.1", 18090, timeout=30):
        show_error("Synapse", "Server startup timeout on port 18090")
        sys.exit(1)

    import webview

    api = Api()

    window = webview.create_window(
        title="Synapse",
        url="http://127.0.0.1:18090",
        width=1280,
        height=800,
        min_size=(1024, 700),
        resizable=True,
        text_select=True,
        frameless=True,
        easy_drag=False,
        js_api=api,
    )

    api.set_window(window)

    # Set window icon after window loads
    def set_icon():
        time.sleep(1)  # wait for window to be ready
        try:
            icon_path = os.path.join(os.path.dirname(sys.executable), 'icon.ico')
            if not os.path.exists(icon_path):
                icon_path = os.path.join(APP_DIR, 'icon.ico')
            if os.path.exists(icon_path):
                hicon = _user32.LoadImageW(
                    0, icon_path, 1, 256, 256, 0x00000010  # IMAGE_ICON, LR_LOADFROMFILE
                )
                if hicon:
                    hwnd = api._ensure_hwnd()
                    if hwnd:
                        _user32.SendMessageW(hwnd, 0x80, 0, hicon)  # ICON_SMALL
                        _user32.SendMessageW(hwnd, 0x80, 1, hicon)  # ICON_BIG
                        log.warning(f'[icon] Set from {icon_path}')
                    else:
                        log.warning('[icon] Could not find HWND')
        except Exception as e:
            log.warning(f'[icon] Failed: {e}')

    window.events.loaded += lambda: threading.Thread(target=set_icon, daemon=True).start()

    # Start maximized for desktop use, while still allowing resize/restore.
    def _auto_maximize():
        time.sleep(0.5)
        hwnd = api._ensure_hwnd()
        if hwnd:
            _user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
    window.events.loaded += lambda: threading.Thread(target=_auto_maximize, daemon=True).start()

    # Periodic license verification (every 3 hours)
    def _periodic_license_check():
        VERIFY_INTERVAL = 3 * 3600  # 3 hours in seconds
        time.sleep(60)  # initial delay: wait 1 min after startup before first check
        while True:
            try:
                from license_client import verify
                ok, msg = verify()
                if not ok:
                    log.warning(f'[license] Periodic check FAILED: {msg}')
                    try:
                        import webview as _wv
                        safe_msg = msg.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
                        js_code = f"if(typeof lockLicenseScreen==='function')lockLicenseScreen('{safe_msg}');"
                        _wv.windows[0].evaluate_js(js_code)
                    except Exception as e:
                        log.error(f'[license] evaluate_js failed: {e}')
                else:
                    log.warning(f'[license] Periodic check OK')
            except Exception as e:
                log.error(f'[license] Periodic check error: {e}')
            time.sleep(VERIFY_INTERVAL)

    threading.Thread(target=_periodic_license_check, daemon=True).start()

    # Force EdgeChromium (WebView2) backend
    try:
        webview.start(gui='edgechromium', debug=False)
    except Exception as e:
        log.warning(f"EdgeChromium failed: {e}, trying default")
        webview.start(debug=False)

if __name__ == "__main__":
    main()
