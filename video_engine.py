# -*- coding: utf-8 -*-
"""漫剧工坊 — 视频模型适配层（Grok为主，支持可灵/Runway）"""

import os
import json
import base64
import time
import http.client
import ssl
import socket
import random
import re as _re

_LOG_PREFIX = "[video_engine]"

def _log(msg):
    print(f"{_LOG_PREFIX} {msg}", flush=True)


def _parse_url(url):
    """解析URL为 (host, port, path, use_ssl)"""
    from urllib.parse import urlparse
    p = urlparse(url)
    use_ssl = p.scheme == "https"
    host = p.hostname
    port = p.port or (443 if use_ssl else 80)
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    return host, port, path, use_ssl


def _make_conn(host, port, use_ssl, timeout=120):
    """创建http.client连接"""
    ctx = ssl.create_default_context()
    if use_ssl:
        return http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
    return http.client.HTTPConnection(host, port, timeout=timeout)


def _upload_image(config, file_path):
    """上传图片到 toapis.com /v1/uploads/images，返回URL"""
    if not os.path.exists(file_path):
        raise RuntimeError(f"文件不存在: {file_path}")

    api_key = config["api_key"]
    base = config["base_url"].rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"

    host, port, _, use_ssl = _parse_url(base + "/uploads/images")

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    boundary = f"----WebKitFormBoundary{int(time.time()*1000)}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }

    _log(f"上传图片: {filename} ({len(file_data)} bytes)")

    conn = _make_conn(host, port, use_ssl, timeout=60)
    try:
        conn.request("POST", "/v1/uploads/images", body=body, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")

        if resp.status != 200:
            raise RuntimeError(f"上传失败 HTTP {resp.status}: {resp_data[:200]}")

        result = json.loads(resp_data)
        if result.get("success") and result.get("data", {}).get("url"):
            url = result["data"]["url"]
            _log(f"上传成功: {url}")
            return url
        raise RuntimeError(f"上传响应异常: {resp_data[:300]}")
    finally:
        conn.close()


def submit_video(config, prompt, image_paths, duration=10, resolution="1080p"):
    """
    提交视频生成任务（异步）。
    config: dict with base_url, api_key, model
    prompt: str B轨完整提示词（英文）
    image_paths: list[str] 图片本地路径列表（最多3张：首帧/参考图/尾帧）
    duration: int 视频秒数 (6/10/15/20/25/30)
    返回: task_id (str)
    """
    provider = config.get("provider", "grok")

    # 兼容旧调用方式：如果传了单个字符串，转为列表
    if isinstance(image_paths, str):
        image_paths = [image_paths] if image_paths else []

    if provider == "grok":
        return _submit_grok(config, prompt, image_paths, duration)
    elif provider == "kling":
        return _submit_kling(config, prompt, image_paths[0] if image_paths else "", duration, resolution)
    elif provider == "runway":
        return _submit_runway(config, prompt, image_paths[0] if image_paths else "", duration)
    else:
        return _submit_grok(config, prompt, image_paths, duration)


def poll_video(config, task_id):
    """
    轮询视频生成状态。
    返回: dict {status: str, video_url: str, error: str}
    """
    provider = config.get("provider", "grok")

    if provider == "grok":
        return _poll_grok(config, task_id)
    elif provider == "kling":
        return _poll_kling(config, task_id)
    elif provider == "runway":
        return _poll_runway(config, task_id)
    else:
        return _poll_grok(config, task_id)


def download_video(url, save_path):
    """下载视频到本地（支持重定向）"""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    host, port, path, use_ssl = _parse_url(url)
    conn = _make_conn(host, port, use_ssl, timeout=120)
    try:
        conn.request("GET", path, headers={"User-Agent": "NovelToDrama/1.0"})
        resp = conn.getresponse()

        if resp.status in (301, 302, 307, 308):
            redirect_url = resp.getheader("Location")
            if redirect_url:
                conn.close()
                return download_video(redirect_url, save_path)

        if resp.status == 200:
            with open(save_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
            return save_path
        else:
            error_body = resp.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"视频下载失败 HTTP {resp.status}: {error_body}")
    finally:
        conn.close()


# ── Grok 实现（正确API: /v1/videos/generations + 上传 + 轮询）──

_grok_tasks = {}  # task_id -> {"status": ..., "video_url": ..., "config": ...}


def _submit_grok(config, prompt, image_paths, duration=10):
    """
    Grok 视频生成 — POST /v1/videos/generations
    images数组最多3个URL：首帧 + 参考图/尾帧
    所有图片先通过 /v1/uploads/images 上传获取URL
    """
    # 1. 上传图片获取URL
    image_urls = []
    for img_path in image_paths[:3]:  # 最多3张
        if img_path and os.path.exists(img_path):
            try:
                url = _upload_image(config, img_path)
                image_urls.append(url)
            except Exception as e:
                _log(f"上传图片失败({os.path.basename(img_path)}): {e}")

    if not image_urls:
        raise RuntimeError("无可用图片，无法生成视频")

    # 2. prompt 已由 _build_b_track_prompt 构建好 IMAGE REFERENCE 说明，直接使用
    full_prompt = prompt

    # 3. POST /v1/videos/generations
    base = config["base_url"].rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"

    api_url = f"{base}/videos/generations"
    host, port, path, use_ssl = _parse_url(api_url)

    allowed_seconds = (6, 10, 15)
    try:
        duration_value = int(duration)
    except Exception:
        duration_value = 10
    seconds = min(allowed_seconds, key=lambda x: abs(x - duration_value))

    body = {
        "model": config.get("model", "grok-video-3"),
        "prompt": full_prompt,
        "images": image_urls[:3],  # max 3
        "seconds": str(seconds),
        "aspect_ratio": "16:9",
    }

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    _log(f"提交Grok视频: model={body['model']} images={len(image_urls)} duration={duration}s prompt_len={len(full_prompt)}")

    # 重试3次
    last_err = None
    for attempt in range(3):
        conn = None
        try:
            conn = _make_conn(host, port, use_ssl, timeout=120)
            conn.request("POST", path, body=data, headers=headers)
            resp = conn.getresponse()
            resp_data = resp.read().decode("utf-8")

            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {resp_data[:300]}")

            result = json.loads(resp_data)
            task_id = result.get("id") or result.get("task_id") or f"grok_{int(time.time()*1000)}"
            status = result.get("status", "queued").lower()

            _log(f"任务提交成功: id={task_id} status={status}")

            _grok_tasks[task_id] = {
                "status": "processing" if status in ("queued", "pending", "processing", "running") else status,
                "config": config,
                "video_url": "",
                "error": "",
            }

            # 如果同步返回了结果
            if status in ("completed", "succeeded", "success", "done"):
                video_url = _extract_video_url(result)
                if video_url:
                    _grok_tasks[task_id]["status"] = "completed"
                    _grok_tasks[task_id]["video_url"] = video_url

            return task_id

        except (http.client.HTTPException, socket.error, TimeoutError, ConnectionError, OSError) as e:
            last_err = str(e)
            _log(f"提交失败(尝试{attempt+1}/3): {last_err}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
        except RuntimeError as e:
            last_err = str(e)
            _log(f"提交失败(尝试{attempt+1}/3): {last_err}")
            if attempt < 2 and ("upstream" in last_err.lower() or "JSON" in last_err):
                time.sleep(5 * (attempt + 1))
                continue
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    raise RuntimeError(f"视频提交失败(3次重试): {last_err}")


def _poll_grok(config, task_id):
    """
    单次查询Grok视频任务状态 — GET /v1/videos/generations/{task_id}
    非阻塞：只查一次，立即返回。
    内存字典仅作缓存，不作为唯一判定依据。
    """
    # 1. 已有终态 → 直接返回缓存
    cached = _grok_tasks.get(task_id)
    if cached and cached.get("status") in ("completed", "failed"):
        return cached

    # 2. 构建查询参数（内存里没有 config 就用传入的）
    cfg = (cached or {}).get("config", config)
    base = cfg["base_url"].rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"

    api_url = f"{base}/videos/generations/{task_id}"
    host, port, path, use_ssl = _parse_url(api_url)

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    # 3. 单次 HTTP 查询，超时 10 秒
    conn = None
    try:
        conn = _make_conn(host, port, use_ssl, timeout=10)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")

        if resp.status == 200:
            # 诊断日志：记录toapis原始回复，方便排查格式问题
            _log(f"Grok poll原始响应 [{task_id}]: {resp_data[:300]}")
            try:
                result = json.loads(resp_data)
            except (json.JSONDecodeError, ValueError) as je:
                _log(f"【警报】Grok poll JSON解析失败 [{task_id}]: {je}, 原始: {resp_data[:200]}")
                _grok_tasks[task_id] = {"status": "processing", "config": cfg, "video_url": ""}
                return _grok_tasks[task_id]
            # 兼容 status 是数字或非字符串的情况
            raw_status = result.get("status", "")
            if not isinstance(raw_status, str):
                raw_status = str(raw_status)
            status = raw_status.lower()
            if not status and "task" in result:
                task_sub = result.get("task", {})
                if isinstance(task_sub, dict):
                    raw_status = task_sub.get("status", "")
                    if not isinstance(raw_status, str):
                        raw_status = str(raw_status)
                    status = raw_status.lower()

            # 终态：completed
            if status in ("completed", "succeeded", "success", "done", "finished", "available", "ready"):
                video_url = _extract_video_url(result)
                if video_url:
                    _grok_tasks[task_id] = {"status": "completed", "video_url": video_url, "config": cfg}
                    _log(f"Grok查询 completed: {task_id} -> {video_url[:80]}")
                    return _grok_tasks[task_id]
                # 尝试从子字段提取
                for sub_key in ("output", "result"):
                    sub = result.get(sub_key)
                    if isinstance(sub, dict):
                        video_url = _extract_video_url(sub)
                        if video_url:
                            _grok_tasks[task_id] = {"status": "completed", "video_url": video_url, "config": cfg}
                            _log(f"Grok查询 completed(从{sub_key}提取): {task_id}")
                            return _grok_tasks[task_id]
                # completed但无URL → 打印原始响应，保持processing等下一轮（不标failed，防误重试）
                _log(f"【警报】Grok返回completed但URL解析失败！原始响应: {resp_data[:500]}")
                _grok_tasks[task_id] = {"status": "processing", "config": cfg, "video_url": ""}
                return _grok_tasks[task_id]

            # 终态：failed
            if status in ("failed", "error", "cancelled", "canceled"):
                err_msg = ""
                if isinstance(result.get("error"), dict):
                    err_msg = result["error"].get("message", "")
                elif result.get("error"):
                    err_msg = str(result["error"])
                _grok_tasks[task_id] = {"status": "failed", "error": err_msg or status, "config": cfg}
                _log(f"Grok查询 failed: {task_id} -> {_grok_tasks[task_id]['error']}")
                return _grok_tasks[task_id]

            # 仍在处理中
            _grok_tasks[task_id] = {"status": "processing", "config": cfg, "video_url": ""}
            return _grok_tasks[task_id]

        elif resp.status == 404:
            # 只有明确 404 才判定任务不存在
            _grok_tasks[task_id] = {"status": "failed", "error": "任务在远端不存在(404)", "config": cfg}
            return _grok_tasks[task_id]
        else:
            # 502/503 等网关错误 → 保持 processing，等下一轮 poll
            _log(f"Grok查询 HTTP {resp.status}: {task_id}")
            if not cached:
                _grok_tasks[task_id] = {"status": "processing", "config": cfg, "video_url": ""}
            return _grok_tasks.get(task_id, {"status": "processing"})

    except (http.client.HTTPException, socket.error, TimeoutError, ConnectionError, OSError) as e:
        # 网络异常 → 绝不标记 failed，保持 processing 等下一轮
        _log(f"Grok查询网络异常: {task_id} -> {e}")
        if not cached:
            _grok_tasks[task_id] = {"status": "processing", "config": cfg, "video_url": ""}
        return _grok_tasks.get(task_id, {"status": "processing"})
    except Exception as e:
        # 兜底：任何未预料的异常都保持 processing，不让它逃逸到 _poll_one
        _log(f"【警报】Grok查询未知异常 [{task_id}]: {type(e).__name__}: {e}")
        if not cached:
            _grok_tasks[task_id] = {"status": "processing", "config": cfg, "video_url": ""}
        return _grok_tasks.get(task_id, {"status": "processing"})
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _extract_video_url(result):
    """从响应中提取视频URL"""
    # 直接字段
    for key in ("video_url", "url", "output_url"):
        val = result.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val

    # data嵌套（兼容多种API返回格式）
    for outer_key in ("result", "data", "output"):
        outer = result.get(outer_key)
        if not outer:
            continue
        # data可能是dict或list
        candidates = [outer] if isinstance(outer, dict) else []
        # toapis格式: result.data = [{"url": "...", "format": "mp4"}]
        if isinstance(outer, list) and outer:
            candidates.append(outer[0] if isinstance(outer[0], dict) else {})
        # 也检查 result.result.data 子嵌套
        if isinstance(outer, dict) and isinstance(outer.get("data"), list) and outer["data"]:
            candidates.append(outer["data"][0] if isinstance(outer["data"][0], dict) else {})
        if isinstance(outer, dict) and isinstance(outer.get("data"), dict):
            candidates.append(outer["data"])
        for data in candidates:
            if isinstance(data, dict):
                for key in ("video_url", "url", "output_url"):
                    val = data.get(key)
                    if isinstance(val, str) and val.startswith("http"):
                        return val
                # videos数组
                for arr_key in ("videos", "data"):
                    arr = data.get(arr_key, [])
                    if isinstance(arr, list) and arr:
                        v = arr[0]
                        if isinstance(v, dict) and v.get("url"):
                            return v["url"]
                        elif isinstance(v, str) and v.startswith("http"):
                            return v

    return None


# ── 可灵 AI 实现 ──

_kling_tasks = {}

def _submit_kling(config, prompt, scene_image_path, duration=10, resolution="1080p"):
    url = f"{config['base_url'].rstrip('/')}/v1/videos/generations"
    host, port, path, use_ssl = _parse_url(url)

    body = {
        "model": config["model"],
        "prompt": prompt,
        "image": "",
        "duration": duration,
        "aspect_ratio": "16:9",
    }

    if scene_image_path and os.path.exists(scene_image_path):
        with open(scene_image_path, "rb") as f:
            body["image"] = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    conn = _make_conn(host, port, use_ssl, timeout=60)
    try:
        conn.request("POST", path, body=data, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp_data[:200]}")
        result = json.loads(resp_data)
        task_id = result.get("data", {}).get("task_id", f"kling_{int(time.time()*1000)}")
        _kling_tasks[task_id] = {"status": "processing", "config": config}
        return task_id
    finally:
        conn.close()


def _poll_kling(config, task_id):
    task_info = _kling_tasks.get(task_id)
    if not task_info:
        return {"status": "failed", "error": "任务不存在"}
    if task_info["status"] in ("completed", "failed"):
        return task_info

    cfg = task_info.get("config", config)
    url = f"{cfg['base_url'].rstrip('/')}/v1/videos/generations/{task_id}"
    host, port, path, use_ssl = _parse_url(url)

    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    conn = _make_conn(host, port, use_ssl, timeout=30)
    try:
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")
        if resp.status != 200:
            return {"status": "processing", "error": f"HTTP {resp.status}"}
        result = json.loads(resp_data)
        status = result.get("data", {}).get("task_status", "processing")
        if status == "succeed":
            video_url = result["data"].get("task_result", {}).get("videos", [{}])[0].get("url", "")
            _kling_tasks[task_id] = {"status": "completed", "video_url": video_url}
        elif status == "failed":
            _kling_tasks[task_id] = {"status": "failed", "error": "可灵生成失败"}
        return _kling_tasks[task_id]
    except Exception as e:
        return {"status": "processing", "error": str(e)}
    finally:
        conn.close()


# ── Runway 实现 ──

_runway_tasks = {}

def _submit_runway(config, prompt, scene_image_path, duration=10):
    url = f"{config['base_url'].rstrip('/')}/image_to_video"
    host, port, path, use_ssl = _parse_url(url)

    body = {
        "model": config["model"],
        "promptText": prompt,
        "duration": duration,
        "ratio": "16:9",
    }

    if scene_image_path and os.path.exists(scene_image_path):
        with open(scene_image_path, "rb") as f:
            body["promptImage"] = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    conn = _make_conn(host, port, use_ssl, timeout=60)
    try:
        conn.request("POST", path, body=data, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}: {resp_data[:200]}")
        result = json.loads(resp_data)
        task_id = result.get("id", f"runway_{int(time.time()*1000)}")
        _runway_tasks[task_id] = {"status": "processing", "config": config}
        return task_id
    finally:
        conn.close()


def _poll_runway(config, task_id):
    task_info = _runway_tasks.get(task_id)
    if not task_info:
        return {"status": "failed", "error": "任务不存在"}
    if task_info["status"] in ("completed", "failed"):
        return task_info

    cfg = task_info.get("config", config)
    url = f"{cfg['base_url'].rstrip('/')}/tasks/{task_id}"
    host, port, path, use_ssl = _parse_url(url)

    headers = {"Authorization": f"Bearer {cfg['api_key']}"}

    conn = _make_conn(host, port, use_ssl, timeout=30)
    try:
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")
        if resp.status != 200:
            return {"status": "processing", "error": f"HTTP {resp.status}"}
        result = json.loads(resp_data)
        status = result.get("status", "processing")
        if status == "SUCCEEDED":
            video_url = result.get("output", [None])[0]
            _runway_tasks[task_id] = {"status": "completed", "video_url": video_url or ""}
        elif status == "FAILED":
            _runway_tasks[task_id] = {"status": "failed", "error": "Runway 生成失败"}
        return _runway_tasks[task_id]
    except Exception as e:
        return {"status": "processing", "error": str(e)}
    finally:
        conn.close()
