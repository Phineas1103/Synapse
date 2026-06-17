# -*- coding: utf-8 -*-
"""Synapse — 配置管理"""

import os
import sys
import json
import hashlib
from pathlib import Path

# ── 路径 ──
if getattr(sys, 'frozen', False):
    # PyInstaller打包后：exe在 dist\manju\manju.exe
    APP_DIR = os.path.dirname(sys.executable)       # dist\manju\
    _INTERNAL = os.path.join(APP_DIR, "_internal")  # dist\manju\_internal\
    # 源码根目录 = APP_DIR往上两级 = D:\Phineas\Synapse\
    # dist\manju\ -> dist\ -> D:\Phineas\Synapse\
    _maybe_source_root = os.path.dirname(os.path.dirname(APP_DIR))
    if os.path.exists(os.path.join(_maybe_source_root, "api_server.py")):
        SOURCE_ROOT = _maybe_source_root
    else:
        SOURCE_ROOT = APP_DIR
else:
    SOURCE_ROOT = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = SOURCE_ROOT
    _INTERNAL = APP_DIR

# ── FFmpeg ──
def _first_existing_path(candidates, fallback):
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return fallback


FFMPEG_PATH = _first_existing_path([
    os.path.join(_INTERNAL, "tools", "ffmpeg.exe"),
    os.path.join(APP_DIR, "tools", "ffmpeg.exe"),
    os.path.join(SOURCE_ROOT, "tools", "ffmpeg.exe"),
    r"D:\Backup\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe",
], "ffmpeg")
FFPROBE_PATH = _first_existing_path([
    os.path.join(_INTERNAL, "tools", "ffprobe.exe"),
    os.path.join(APP_DIR, "tools", "ffprobe.exe"),
    os.path.join(SOURCE_ROOT, "tools", "ffprobe.exe"),
    r"D:\Backup\Downloads\ffmpeg-7.1.1-essentials_build\ffmpeg-7.1.1-essentials_build\bin\ffprobe.exe",
], "ffprobe")
# 项目数据和用户配置始终在源码目录（防止 --noconfirm 构建清掉）
PROJECTS_DIR = os.path.join(SOURCE_ROOT, "projects")
TEMPLATES_DIR = os.path.join(_INTERNAL, "prompt_templates")
CONFIG_PATH = os.path.join(SOURCE_ROOT, "user_config.json")

# ── 默认配置 ──
DEFAULT_CONFIG = {
    "llm": {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o",
    },
    "image": {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-image-2",
    },
    "video": {
        "provider": "grok",
        "base_url": "https://api.x.ai/v1",
        "api_key": "",
        "model": "grok-2-vision",
    },
    "project": {
        "clip_duration": 10,
        "art_style": "anime",
        "language": "zh",
    },
}

# ── LLM 预设提供商 ──
LLM_PRESETS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "mimo": {
        "name": "mimo",
        "base_url": "https://api.volcengine.com/v1",
        "models": ["mimo-v2.5-pro"],
    },
    "custom": {
        "name": "自定义",
        "base_url": "",
        "models": [],
    },
}

# ── 图片模型预设 ──
IMAGE_PRESETS = {
    "openai": {
        "name": "GPT-image-2",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-image-2", "dall-e-3"],
    },
    "flux": {
        "name": "Flux Pro",
        "base_url": "https://api.replicate.com/v1",
        "models": ["flux-1.1-pro", "flux-schnell"],
    },
    "volcengine": {
        "name": "可灵文生图",
        "base_url": "https://visual.volcengineapi.com",
        "models": ["kling-image"],
    },
}

# ── 视频模型预设 ──
VIDEO_PRESETS = {
    "grok": {
        "name": "Grok",
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-2-vision"],
    },
    "kling": {
        "name": "可灵AI",
        "base_url": "https://api.klingai.com",
        "models": ["kling-v1-5", "kling-v1"],
    },
    "runway": {
        "name": "Runway Gen-3",
        "base_url": "https://api.runwayml.com/v1",
        "models": ["gen3a_turbo"],
    },
}


def _ensure_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def load_config():
    """加载用户配置"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = json.loads(json.dumps(DEFAULT_CONFIG))
            for section in merged:
                if section in saved and isinstance(saved[section], dict):
                    merged[section].update(saved[section])
            return merged
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config):
    """保存用户配置"""
    _ensure_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())


def test_api_connection(provider_type, base_url, api_key, model):
    """测试API连接是否可用 — 使用 http.client 直连绕过 PyInstaller 环境问题"""
    import http.client
    import ssl
    import urllib.parse

    if not api_key:
        return {"success": False, "message": "API Key 未填写"}

    def _do_test(full_url, headers):
        try:
            parsed = urllib.parse.urlparse(full_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            path = parsed.path
            use_ssl = parsed.scheme == "https"

            if use_ssl:
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection(host, port, timeout=10, context=ctx)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=10)
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            status = resp.status
            resp.read()
            conn.close()

            if status == 200:
                return {"success": True, "message": "连接成功"}
            elif status == 401:
                return {"success": False, "message": "API Key 无效"}
            else:
                return {"success": False, "message": f"HTTP {status}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    if provider_type in ("llm", "image", "video"):
        url = f"{base_url.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        return _do_test(url, headers)
    return {"success": False, "message": "未知提供商类型"}


def get_presets():
    """返回所有预设配置"""
    return {
        "llm": LLM_PRESETS,
        "image": IMAGE_PRESETS,
        "video": VIDEO_PRESETS,
    }
