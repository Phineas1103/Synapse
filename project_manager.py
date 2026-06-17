# -*- coding: utf-8 -*-
"""Synapse — 项目管理（保存/加载/列表）"""

import os
import json
import time
import shutil
from config import PROJECTS_DIR
import re
import http.client
import ssl
import urllib.parse


def _project_root():
    return os.path.abspath(PROJECTS_DIR)


def _safe_project_dir(project_id):
    if not re.fullmatch(r"proj_\d+", str(project_id or "")):
        raise ValueError(f"Invalid project id: {project_id}")
    project_dir = os.path.abspath(os.path.join(PROJECTS_DIR, project_id))
    root = _project_root()
    if os.path.commonpath([root, project_dir]) != root:
        raise ValueError(f"Invalid project path: {project_id}")
    return project_dir


def is_project_file(path):
    if not path:
        return False
    try:
        root = _project_root()
        target = os.path.abspath(path)
        return os.path.commonpath([root, target]) == root and os.path.isfile(target)
    except Exception:
        return False


def _parse_url_for_pm(url):
    """解析URL为 (host, port, path, use_ssl)"""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return host, port, path, parsed.scheme == "https"


def _http_download(url, save_path, timeout=30):
    """通过http.client下载URL内容并保存（绕过PyInstaller urllib问题）"""
    host, port, path, use_ssl = _parse_url_for_pm(url)
    if use_ssl:
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", url if path == url else path, headers={"User-Agent": "NovelToDrama/1.0"})
        resp = conn.getresponse()
        # 跟进重定向
        if resp.status in (301, 302, 307, 308):
            redirect = resp.getheader("Location")
            if redirect:
                conn.close()
                return _http_download(redirect, save_path, timeout)
        if resp.status == 200:
            with open(save_path, "wb") as f:
                f.write(resp.read())
        else:
            raise RuntimeError(f"下载失败 HTTP {resp.status}")
    finally:
        conn.close()


def _http_download_chunked(url, save_path, timeout=120):
    """分块下载大文件（视频等）"""
    host, port, path, use_ssl = _parse_url_for_pm(url)
    if use_ssl:
        ctx = ssl.create_default_context()
        conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        conn.request("GET", path, headers={"User-Agent": "NovelToDrama/1.0"})
        resp = conn.getresponse()
        if resp.status in (301, 302, 307, 308):
            redirect = resp.getheader("Location")
            if redirect:
                conn.close()
                return _http_download_chunked(redirect, save_path, timeout)
        if resp.status == 200:
            with open(save_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
        else:
            raise RuntimeError(f"下载失败 HTTP {resp.status}")
    finally:
        conn.close()




def _safe_filename(name):
    """Replace characters that are illegal in Windows filenames."""
    safe = re.sub(r'[\\/:*?"<>|（）()]', '_', name)
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe if safe else 'unnamed'


def create_project(name, settings):
    """
    创建新项目。
    返回: project_id (str)
    """
    project_id = f"proj_{int(time.time() * 1000)}"
    project_dir = _safe_project_dir(project_id)

    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(os.path.join(project_dir, "characters"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "chapters"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "storyboards"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "frames"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "videos"), exist_ok=True)
    os.makedirs(os.path.join(project_dir, "output"), exist_ok=True)

    project = {
        "id": project_id,
        "name": name,
        "created_at": time.time(),
        "updated_at": time.time(),
        "current_step": 2,
        "settings": settings,
        "outline": None,
        "characters": [],
        "chapters": {},
        "storyboards": {},
        "frames": {},
        "videos": {},
        "subtitles": [],
        "chat_history": [],
    }

    _save_project(project_dir, project)
    return project_id


def load_project(project_id):
    """加载项目数据"""
    project_dir = _safe_project_dir(project_id)
    project_file = os.path.join(project_dir, "project.json")

    if not os.path.exists(project_file):
        raise FileNotFoundError(f"项目不存在: {project_id}")

    with open(project_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(project_id, data):
    """保存项目数据"""
    project_dir = _safe_project_dir(project_id)
    data["updated_at"] = time.time()
    _save_project(project_dir, data)


def list_projects():
    """列出所有项目"""
    projects = []
    if not os.path.exists(PROJECTS_DIR):
        return projects

    for name in os.listdir(PROJECTS_DIR):
        if "backup" in name.lower():
            continue
        project_dir = os.path.join(PROJECTS_DIR, name)
        project_file = os.path.join(project_dir, "project.json")
        if os.path.isfile(project_file):
            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                projects.append({
                    "id": data["id"],
                    "name": data["name"],
                    "created_at": data["created_at"],
                    "updated_at": data["updated_at"],
                    "current_step": data.get("current_step", 1),
                    "settings": data.get("settings", {}),
                })
            except Exception:
                continue

    projects.sort(key=lambda x: x["updated_at"], reverse=True)
    return projects


def delete_project(project_id):
    """删除项目"""
    project_dir = _safe_project_dir(project_id)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)


def update_project_step(project_id, step):
    """更新项目当前步骤"""
    project = load_project(project_id)
    project["current_step"] = step
    save_project(project_id, project)


def get_project_path(project_id, subdir=None):
    """获取项目目录路径"""
    base = _safe_project_dir(project_id)
    if subdir:
        path = os.path.abspath(os.path.join(base, subdir))
        if os.path.commonpath([base, path]) != base:
            raise ValueError(f"Invalid project subdir: {subdir}")
        return path
    return base


def save_character_image(project_id, character_name, image_data):
    """
    保存角色定妆照。
    image_data: base64 字符串 或 文件URL
    """
    import base64

    char_dir = get_project_path(project_id, "characters")
    os.makedirs(char_dir, exist_ok=True)
    safe_name = _safe_filename(character_name)
    save_path = os.path.join(char_dir, f"{safe_name}.png")

    if image_data.startswith("http"):
        _http_download(image_data, save_path)
    elif image_data.startswith("data:"):
        _, b64 = image_data.split(",", 1)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))
    else:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(image_data))

    return save_path


def save_frame_image(project_id, chapter_index, clip_index, image_data):
    """保存分镜图"""
    import base64

    frame_dir = get_project_path(project_id, os.path.join("frames", f"ch{chapter_index:03d}"))
    os.makedirs(frame_dir, exist_ok=True)
    save_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")

    if image_data.startswith("http"):
        _http_download(image_data, save_path)
    elif image_data.startswith("data:"):
        _, b64 = image_data.split(",", 1)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))
    else:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(image_data))

    return save_path


def save_tail_frame_image(project_id, chapter_index, clip_index, image_data):
    """保存尾帧图（与参考图同目录，文件名加 _tail 后缀）"""
    import base64

    frame_dir = get_project_path(project_id, os.path.join("frames", f"ch{chapter_index:03d}"))
    os.makedirs(frame_dir, exist_ok=True)
    save_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")

    if image_data.startswith("http"):
        _http_download(image_data, save_path)
    elif image_data.startswith("data:"):
        _, b64 = image_data.split(",", 1)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))
    else:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(image_data))

    return save_path


def save_video_file(project_id, chapter_index, clip_index, video_data_or_url):
    """保存视频文件"""
    import base64

    video_dir = get_project_path(project_id, os.path.join("videos", f"ch{chapter_index:03d}"))
    os.makedirs(video_dir, exist_ok=True)
    save_path = os.path.join(video_dir, f"clip_{clip_index:03d}.mp4")

    if video_data_or_url.startswith("http"):
        _http_download_chunked(video_data_or_url, save_path, timeout=120)
    elif video_data_or_url.startswith("data:"):
        _, b64 = video_data_or_url.split(",", 1)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))
    else:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(video_data_or_url))

    return save_path


def export_project(project_id, export_path, resolution, fps, codec, bitrate):
    """导出最终成品（合成已编码完成，直接复制文件）"""
    import shutil

    project = load_project(project_id)
    output_dir = get_project_path(project_id, "output")

    # 优先找完整拼接视频，其次找单集视频
    final_video = os.path.join(output_dir, "complete_final.mp4")
    if not os.path.exists(final_video):
        import glob
        finals = sorted(glob.glob(os.path.join(output_dir, "ch*_final.mp4")))
        if not finals:
            finals = sorted(glob.glob(os.path.join(output_dir, "ch*_concat.mp4")))
        if finals:
            final_video = finals[-1]
    if not os.path.exists(final_video):
        raise FileNotFoundError("未找到已合成的视频，请先完成后期合成")

    # 确保目标目录存在
    export_dir = os.path.dirname(export_path)
    if export_dir and not os.path.exists(export_dir):
        os.makedirs(export_dir, exist_ok=True)

    # 合成已完成编码，直接复制文件
    shutil.copy2(final_video, export_path)
    return export_path


# ── 内部函数 ──


def _save_project(project_dir, data):
    project_file = os.path.join(project_dir, "project.json")
    temp_file = project_file + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_file, project_file)
