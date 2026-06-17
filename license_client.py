"""
Synapse License Client
硬件指纹采集 + 服务器通信 + 离线缓存
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import base64
import ctypes
import ctypes.wintypes
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# 服务器地址
LICENSE_SERVER = os.environ.get("SYNAPSE_LICENSE_SERVER", "https://124.221.179.140")
LEGACY_LICENSE_SERVER = "http://124.221.179.140"

# 离线缓存文件
APP_DATA_ROOT = os.environ.get(
    "LOCALAPPDATA",
    os.path.join(os.path.expanduser("~"), "AppData", "Local")
)
CACHE_DIR = os.path.join(APP_DATA_ROOT, "Synapse", ".state")
CACHE_FILE = os.path.join(CACHE_DIR, "state.dat")
LEGACY_CACHE_FILE = "license_cache.json"

# 离线有效天数
OFFLINE_DAYS = 7


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _license_servers():
    servers = [LICENSE_SERVER.rstrip("/")]
    if "SYNAPSE_LICENSE_SERVER" not in os.environ and servers[0] != LEGACY_LICENSE_SERVER:
        servers.append(LEGACY_LICENSE_SERVER)
    return servers


def _mask_license_key(key):
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _legacy_cache_files():
    candidates = [
        os.path.abspath(LEGACY_CACHE_FILE),
        os.path.join(_app_dir(), LEGACY_CACHE_FILE),
    ]
    result = []
    for path in candidates:
        path = os.path.abspath(path)
        if path not in result:
            result.append(path)
    return result


def _hide_path(path):
    if platform.system() != "Windows" or not os.path.exists(path):
        return
    attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
    if attrs == 0xFFFFFFFF:
        return
    ctypes.windll.kernel32.SetFileAttributesW(path, attrs | 0x02 | 0x04)


def _show_path_for_write(path):
    if platform.system() != "Windows" or not os.path.exists(path):
        return
    attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
    if attrs == 0xFFFFFFFF:
        return
    ctypes.windll.kernel32.SetFileAttributesW(path, attrs & ~0x07)


def _remove_file(path):
    try:
        if os.path.exists(path):
            _show_path_for_write(path)
            os.remove(path)
    except:
        pass


def _dpapi_protect(text):
    if not text or platform.system() != "Windows":
        return ""
    raw = text.encode("utf-8")
    buf = ctypes.create_string_buffer(raw)
    in_blob = _DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
    ):
        return ""
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(value):
    if not value or not value.startswith("dpapi:") or platform.system() != "Windows":
        return ""
    try:
        encrypted = base64.b64decode(value.split(":", 1)[1])
        buf = ctypes.create_string_buffer(encrypted)
        in_blob = _DATA_BLOB(len(encrypted), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out_blob = _DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return ""
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return raw.decode("utf-8")
    except:
        return ""
    finally:
        if "out_blob" in locals() and out_blob.pbData:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def get_hardware_fingerprint():
    """采集硬件指纹：CPU序列号+主板序列号+硬盘序列号+MAC地址"""
    parts = []
    
    try:
        # CPU序列号
        if platform.system() == "Windows":
            r = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if line and line != "ProcessorId":
                    parts.append(line)
                    break
        else:
            # Linux/Mac
            r = subprocess.run(
                ["cat", "/proc/cpuinfo"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.split("\n"):
                if "serial" in line.lower() or "cpu id" in line.lower():
                    parts.append(line.split(":")[-1].strip())
    except:
        parts.append("no_cpu")
    
    try:
        # 主板序列号
        if platform.system() == "Windows":
            r = subprocess.run(
                ["wmic", "baseboard", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if line and line != "SerialNumber":
                    parts.append(line)
                    break
        else:
            r = subprocess.run(
                ["cat", "/sys/class/dmi/id/board_serial"],
                capture_output=True, text=True, timeout=10
            )
            if r.stdout.strip():
                parts.append(r.stdout.strip())
    except:
        parts.append("no_board")
    
    try:
        # 硬盘序列号
        if platform.system() == "Windows":
            r = subprocess.run(
                ["wmic", "diskdrive", "get", "SerialNumber"],
                capture_output=True, text=True, timeout=10
            )
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if line and line != "SerialNumber":
                    parts.append(line)
                    break
        else:
            r = subprocess.run(
                ["lsblk", "-ndo", "SERIAL", "/dev/vda"],
                capture_output=True, text=True, timeout=10
            )
            if r.stdout.strip():
                parts.append(r.stdout.strip())
    except:
        parts.append("no_disk")
    
    try:
        # MAC地址
        import uuid
        mac = uuid.getnode()
        parts.append(":".join(f"{(mac >> i) & 0xff:02x}" for i in range(40, -1, -8)))
    except:
        parts.append("no_mac")
    
    # SHA256哈希
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def load_cache():
    """加载离线缓存"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                encrypted_payload = f.read().strip()
            payload = _dpapi_unprotect(encrypted_payload)
            if payload:
                return json.loads(payload)
    except:
        pass

    for legacy_file in _legacy_cache_files():
        if not os.path.exists(legacy_file):
            continue
        try:
            with open(legacy_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue
        encrypted_key = data.get("license_key_encrypted", "")
        if encrypted_key and not data.get("license_key"):
            data["license_key"] = _dpapi_unprotect(encrypted_key)
        try:
            save_cache(data)
            for old_file in _legacy_cache_files():
                _remove_file(old_file)
        except:
            pass
        return data

    return None


def save_cache(data):
    """保存离线缓存"""
    data = dict(data)
    license_key = data.get("license_key", "")
    if license_key:
        data["license_key_masked"] = _mask_license_key(license_key)
    data.pop("license_key_encrypted", None)

    os.makedirs(CACHE_DIR, exist_ok=True)
    _hide_path(CACHE_DIR)

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    encrypted_payload = _dpapi_protect(payload)
    if not encrypted_payload:
        raise RuntimeError("Failed to encrypt license cache")

    _show_path_for_write(CACHE_FILE)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(encrypted_payload)
    _hide_path(CACHE_FILE)


def api_request(endpoint, data=None, method="POST"):
    """发送HTTP请求到服务器"""
    headers = {"Content-Type": "application/json"}
    
    if data:
        body = json.dumps(data).encode("utf-8")
    else:
        body = None

    last_error = None
    for server in _license_servers():
        url = f"{server}{endpoint}"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            resp_body = e.read().decode("utf-8", errors="replace")
            try:
                resp_data = json.loads(resp_body)
                # FastAPI HTTPException返回{"detail": "..."}格式，标准化为{"success": False, "message": "..."}
                if "detail" in resp_data and "success" not in resp_data:
                    return {"success": False, "message": resp_data["detail"]}
                return resp_data
            except:
                return {"success": False, "message": f"HTTP {e.code}: {resp_body}"}
        except Exception as e:
            last_error = e
            continue
    return {"success": False, "message": str(last_error), "network_error": True}


def activate(license_key):
    """激活卡密"""
    fingerprint = get_hardware_fingerprint()
    
    result = api_request("/api/activate", {
        "license_key": license_key,
        "hardware_fingerprint": fingerprint
    })
    
    if result.get("success"):
        # 保存到本地缓存
        cache_data = {
            "license_key": license_key,
            "fingerprint": fingerprint,
            "expires_at": result.get("expires_at"),
            "activated_at": datetime.now().isoformat(),
            "last_verified": datetime.now().isoformat()
        }
        save_cache(cache_data)
        return True, result.get("message", "激活成功")
    else:
        return False, result.get("message", "激活失败")


def verify():
    """验证许可证（在线优先，离线兜底）"""
    fingerprint = get_hardware_fingerprint()
    
    # 先检查本地缓存
    cache = load_cache()
    if not cache:
        return False, "未激活，请先输入卡密"
    license_key = cache.get("license_key", "")
    if not license_key:
        return False, "缓存数据损坏，请重新激活"
    
    # 检查硬件指纹是否匹配
    if cache.get("fingerprint") != fingerprint:
        return False, "硬件信息不匹配，请重新激活"
    
    # 检查过期时间
    try:
        expires = datetime.fromisoformat(cache["expires_at"])
        if datetime.now() > expires:
            return False, "卡密已过期"
    except:
        return False, "缓存数据损坏，请重新激活"
    
    # 尝试在线验证
    result = api_request("/api/verify", {
        "license_key": license_key,
        "hardware_fingerprint": fingerprint
    })
    
    if result.get("success"):
        # 在线验证成功，更新缓存
        cache["last_verified"] = datetime.now().isoformat()
        if result.get("expires_at"):
            cache["expires_at"] = result["expires_at"]
        save_cache(cache)
        return True, "验证成功"
    
    # 服务器明确拒绝（非网络异常），直接失败
    if not result.get("network_error"):
        return False, result.get("message", "卡密无效或已禁用")
    
    # 网络异常，走离线兜底
    try:
        last_verified = datetime.fromisoformat(cache["last_verified"])
        offline_limit = last_verified + timedelta(days=OFFLINE_DAYS)
        
        if datetime.now() > offline_limit:
            return False, "离线超过7天，请联网验证"
        else:
            # 离线有效
            remaining = (offline_limit - datetime.now()).days
            return True, f"离线模式（剩余{remaining}天）"
    except:
        return False, "缓存数据损坏，请重新激活"


def get_license_info():
    """获取当前卡密信息"""
    cache = load_cache()
    if not cache:
        return None
    
    return {
        "license_key": _mask_license_key(cache.get("license_key", "")),
        "license_key_masked": _mask_license_key(cache.get("license_key", "")),
        "expires_at": cache.get("expires_at"),
        "last_verified": cache.get("last_verified"),
        "fingerprint": cache.get("fingerprint")
    }


def deactivate():
    """注销（清除本地缓存）"""
    _remove_file(CACHE_FILE)
    for legacy_file in _legacy_cache_files():
        _remove_file(legacy_file)
    return True, "已注销"


# 命令行测试
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  python license_client.py activate <卡密>")
        print("  python license_client.py verify")
        print("  python license_client.py info")
        print("  python license_client.py deactivate")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "activate":
        if len(sys.argv) < 3:
            print("错误: 请提供卡密")
            sys.exit(1)
        key = sys.argv[2]
        ok, msg = activate(key)
        print(f"{'成功' if ok else '失败'}: {msg}")
    
    elif cmd == "verify":
        ok, msg = verify()
        print(f"{'有效' if ok else '无效'}: {msg}")
    
    elif cmd == "info":
        info = get_license_info()
        if info:
            print(json.dumps(info, indent=2, ensure_ascii=False))
        else:
            print("未激活")
    
    elif cmd == "deactivate":
        ok, msg = deactivate()
        print(msg)
    
    else:
        print(f"未知命令: {cmd}")
