# -*- coding: utf-8 -*-
"""Synapse — 图片生成（中转站统一走 /v1/images/generations）
使用 http.client 直连，绕过 PyInstaller 环境下 urllib 的系统代理/SSL 问题
长连接复用 + 路径嗅探锁定 + 异步任务轮询
"""

import os
import json
import base64
import time
import http.client
import ssl
import urllib.parse
import random
import socket
import threading


# ── 全局限流器（令牌桶）：300次/分钟，每秒补充5个令牌 ──
class RateLimiter:
    """线程安全的令牌桶，控制HTTP请求频率"""

    def __init__(self, rate_per_minute=300):
        self._lock = threading.Lock()
        self._rate = rate_per_minute / 60.0  # 每秒令牌数
        self._capacity = rate_per_minute
        self._tokens = float(rate_per_minute)
        self._last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self):
        """获取一个令牌，无令牌时阻塞等待（线程安全）"""
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self._rate
            time.sleep(wait)


_rate_limiter = RateLimiter(300)


def _log(msg):
    print(f"[IMAGE] {msg}", flush=True)


def _parse_url(url):
    """解析URL，返回 (host, port, path, use_ssl)"""
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    use_ssl = parsed.scheme == "https"
    return host, port, path, use_ssl


def _ssl_context():
    """创建SSL上下文"""
    ctx = ssl.create_default_context()
    return ctx


def _make_conn(host, port, use_ssl, timeout=120):
    """创建http.client连接"""
    if use_ssl:
        return http.client.HTTPSConnection(host, port, timeout=timeout, context=_ssl_context())
    else:
        return http.client.HTTPConnection(host, port, timeout=timeout)


def _extract_image(data_dict):
    """
    自适应提取图片：兼容标准OpenAI的 data[0].url / b64_json，
    以及各种中转站常见的 output, result 变体
    """
    if not isinstance(data_dict, dict):
        return None

    # 标准 OpenAI /v1/images/generations 成功格式
    if "data" in data_dict and isinstance(data_dict["data"], list):
        for item in data_dict["data"]:
            if isinstance(item, dict):
                res = item.get("url") or item.get("b64_json")
                if res:
                    return res

    # toapis.com: result.data[0].url
    if "result" in data_dict and isinstance(data_dict["result"], dict):
        nested = data_dict["result"]
        if "data" in nested and isinstance(nested["data"], list):
            for item in nested["data"]:
                if isinstance(item, dict):
                    res = item.get("url") or item.get("b64_json")
                    if res:
                        return res

    # 中转站常见变体嵌套 (output / result)
    for key in ["output", "result"]:
        if key in data_dict:
            nested = data_dict[key]
            if isinstance(nested, dict):
                res = _extract_image(nested)
                if res:
                    return res
            elif isinstance(nested, list) and nested:
                if isinstance(nested[0], dict):
                    return nested[0].get("url") or nested[0].get("image")
                elif isinstance(nested[0], str):
                    return nested[0]

    # 平铺在根目录下的 url 字段
    return data_dict.get("url") or data_dict.get("image_url") or data_dict.get("image")


def _poll_task(base_url, api_key, task_id, max_wait=300, interval=3):
    """
    轮询异步任务直到完成。
    max_wait: 最大等待300秒（5分钟），网络问题不会空等太久
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    host, port, root_path, use_ssl = _parse_url(base_url)
    conn = _make_conn(host, port, use_ssl, timeout=120)

    # 路径嗅探：root_path已含 /v1，模板只写相对部分
    current_path_template = "/images/generations/{task_id}"
    path_locked = False

    t0 = time.time()
    attempt = 0

    # P1: 初始错峰，打散并发线程的首次请求时间
    time.sleep(random.uniform(0, 3))

    # 429指数退避计数器（用list封装实现闭包内可变）
    _429_count = [0]
    _net_error_count = [0]  # 连续网络错误计数器
    _MAX_NET_ERRORS = 10   # 连续10次网络错误触发熔断

    _log(f"开始轮询异步任务: {task_id}...")

    try:
        while time.time() - t0 < max_wait:
            attempt += 1
            elapsed = round(time.time() - t0, 1)

            # P1: 随机轮询间隔
            current_interval = random.uniform(interval, interval + 3)
            full_path = f"{root_path.rstrip('/')}{current_path_template.format(task_id=task_id)}"

            try:
                _rate_limiter.acquire()  # 令牌桶限流
                conn.request("GET", full_path, headers=headers)
                resp = conn.getresponse()
                resp_data = resp.read().decode("utf-8")
            except (http.client.HTTPException, socket.error, TimeoutError, ConnectionError, OSError) as e:
                _net_error_count[0] += 1
                _log(f"轮询#{attempt} 网络异常({e})，重建连接... (连续第{_net_error_count[0]}次)")
                if _net_error_count[0] >= _MAX_NET_ERRORS:
                    raise RuntimeError(f"连续{_MAX_NET_ERRORS}次网络异常，触发熔断: {e}")
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _make_conn(host, port, use_ssl, timeout=120)
                time.sleep(current_interval)
                continue

            # 路径嗅探：404/405 时切换一次并锁定
            if resp.status in (404, 405) and not path_locked:
                _log(f"路径探测: {current_path_template} -> {resp.status}，切换到 /tasks")
                current_path_template = "/tasks/{task_id}"
                path_locked = True
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _make_conn(host, port, use_ssl, timeout=120)
                continue

            if resp.status != 200:
                # 429 限流：指数退避（3s → 9s → 27s → 81s）
                if resp.status == 429:
                    backoff = 3 * (3 ** _429_count[0])  # 3^1, 3^2, 3^3, 3^4
                    _429_count[0] = min(_429_count[0] + 1, 4)
                    _log(f"轮询#{attempt} ({elapsed}s) 429限流，退避 {backoff}s")
                    time.sleep(backoff)
                else:
                    _log(f"轮询#{attempt} ({elapsed}s) 异常: HTTP {resp.status}")
                    time.sleep(current_interval)
                try:
                    conn.close()
                except Exception:
                    pass
                conn = _make_conn(host, port, use_ssl, timeout=120)
                continue

            # 非429正常响应，重置退避计数
            _429_count[0] = 0
            _net_error_count[0] = 0  # 网络正常，重置连续错误计数

            try:
                result = json.loads(resp_data)
            except json.JSONDecodeError:
                _log(f"轮询#{attempt} JSON解析失败，跳过")
                time.sleep(current_interval)
                continue

            status = result.get("status", "").lower()
            if not status and "task" in result and isinstance(result["task"], dict):
                status = result["task"].get("status", "").lower()

            _log(f"轮询#{attempt} ({elapsed}s) status={status}")

            # P0: 无条件先尝试提取图片
            img = _extract_image(result)
            if img and isinstance(img, str) and (img.startswith("http") or len(img) > 100):
                _log(f"轮询完成(共{elapsed}s)")
                return img

            # 已完成状态
            if status in ("completed", "succeeded", "success", "done", "finished", "available", "ready"):
                for sub_key in ("output", "result"):
                    sub = result.get(sub_key)
                    if isinstance(sub, dict):
                        img2 = _extract_image(sub)
                        if img2 and isinstance(img2, str) and (img2.startswith("http") or len(img2) > 100):
                            _log(f"轮询完成-从{sub_key}提取(共{elapsed}s)")
                            return img2
                raise RuntimeError(f"任务完成但无法提取合法图片: {resp_data[:300]}")

            if status in ("failed", "error", "cancelled", "canceled"):
                err_msg = ""
                if isinstance(result.get("error"), dict):
                    err_msg = result["error"].get("message", "")
                elif result.get("error"):
                    err_msg = str(result["error"])
                raise RuntimeError(f"任务失败: {err_msg or status}")

            # queued / in_progress / pending / processing / running — 继续轮询
            time.sleep(current_interval)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    raise RuntimeError(f"任务轮询超时({max_wait}s)，task_id={task_id}")


# ── 定妆照上传缓存（同一张图只上传一次） ──
_upload_cache = {}


def _upload_image(config, file_path):
    """
    上传本地图片到 toapis.com，返回可访问 URL。
    带内存缓存：同一路径只上传一次。
    """
    if file_path in _upload_cache:
        _log(f"上传缓存命中: {os.path.basename(file_path)}")
        return _upload_cache[file_path]

    base = config["base_url"].rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    upload_url = f"{base}/uploads/images"

    api_key = config["api_key"]
    host, port, path, use_ssl = _parse_url(upload_url)

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_data = f.read()

    boundary = f"----HermesBoundary{int(time.time() * 1000)}"

    # Multipart form body
    ext = os.path.splitext(filename)[1].lower()
    ct_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif"}
    ct = ct_map.get(ext, "image/png")

    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    parts.append(f"Content-Type: {ct}\r\n\r\n".encode())
    parts.append(file_data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }

    _log(f"上传定妆照: {filename} ({len(file_data)} bytes)")

    conn = _make_conn(host, port, use_ssl, timeout=60)
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")

        if resp.status != 200:
            raise RuntimeError(f"上传失败 HTTP {resp.status}: {resp_data[:200]}")

        result = json.loads(resp_data)
        if result.get("success") and result.get("data", {}).get("url"):
            url = result["data"]["url"]
            _upload_cache[file_path] = url
            _log(f"上传成功: {url}")
            return url
        raise RuntimeError(f"上传响应异常: {resp_data[:300]}")
    finally:
        conn.close()


def generate_image(config, prompt, reference_images=None, size="16:9", resolution="1K"):
    """
    生成图片（文生图 + 图生图）。
    config: dict with base_url, api_key, model
    prompt: str 或 dict（dict 时自动提取 image_prompt）
    reference_images: list of dict [{"name": "角色名", "path": "本地文件路径"}]
    size: 图片宽高比 (默认 "16:9")
    resolution: 图片分辨率 "2K" 或 "1K" (默认 "2K")
    返回: str (base64 编码的图片数据 或 文件URL)
    """
    # 如果 prompt 是 dict（a_track），提取 reference_prompt 或 image_prompt
    if isinstance(prompt, dict):
        prompt = prompt.get("reference_prompt", prompt.get("image_prompt", str(prompt)))

    # 上传定妆照 + 构建角色映射前缀
    ref_urls = []
    if reference_images:
        char_prefix_parts = []
        for ref in reference_images:
            name = ref.get("name", "角色")
            path = ref.get("path", "")
            if path and os.path.exists(path):
                try:
                    url = _upload_image(config, path)
                    ref_urls.append(url)
                    char_prefix_parts.append(
                        f"Reference Image {len(ref_urls)} is {name}"
                    )
                except Exception as e:
                    _log(f"上传定妆照失败({name}): {e}")

        if char_prefix_parts:
            mapping = ", ".join(char_prefix_parts)
            prompt = f"{mapping}. {prompt}"
            _log(f"角色参考图映射: {mapping}")

        # Anti-clothing-override: when reference images exist, tell the model
        # to rely on them for character appearance instead of text descriptions
        if ref_urls:
            prompt += (
                " IMPORTANT: Character appearance and clothing are defined by"
                " the reference images. Do NOT add or override any clothing,"
                " hairstyle, or appearance descriptions in the text prompt —"
                " rely entirely on the reference images for character visual identity."
            )

    base = config["base_url"].rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    url = f"{base}/images/generations"

    model = config["model"]
    api_key = config["api_key"]

    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "resolution": resolution,
        "response_format": "url",
    }
    if ref_urls:
        body["reference_images"] = ref_urls
        _log(f"附带 {len(ref_urls)} 张参考图")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    _log(f"开始生成 模型={model} prompt长度={len(prompt)} size={size} resolution={resolution}")

    t0 = time.time()
    last_err = None
    task_id = None  # 记录已创建的task_id，后续重试只重试轮询不重新POST

    for attempt in range(3):
        conn = None
        try:
            host, port, path, use_ssl = _parse_url(url)
            conn = _make_conn(host, port, use_ssl)

            # ── 第一步：POST（只在没有task_id时执行）──
            if task_id is None:
                _rate_limiter.acquire()
                conn.request("POST", path, body=data, headers=headers)
                resp = conn.getresponse()

                if resp.status == 200:
                    resp_data = resp.read().decode("utf-8")
                    result = json.loads(resp_data)
                elif resp.status == 401:
                    error_body = resp.read().decode("utf-8", errors="replace")[:200]
                    raise RuntimeError(f"图片生成失败 401: API Key无效 {error_body}")
                else:
                    error_body = resp.read().decode("utf-8", errors="replace")[:200]
                    raise RuntimeError(f"图片生成失败 HTTP {resp.status}: {error_body}")

                elapsed = round(time.time() - t0, 1)

                # 检测异步任务响应
                task_id = result.get("id", "")
                status = result.get("status", "").lower()
                if task_id and status in ("pending", "processing", "running", "queued", "in_progress"):
                    _log(f"检测到异步任务 id={task_id} status={status}，开始轮询...")
                    _log(f"[Task_Created] task_id={task_id} prompt_len={len(prompt)}")
                elif task_id and status in ("completed", "succeeded", "success", "done"):
                    # 同步返回了结果
                    img = _extract_image(result)
                    if img:
                        _log(f"同步完成(共{elapsed}s)")
                        return img
                else:
                    # 未知状态，尝试提取
                    img = _extract_image(result)
                    if img:
                        _log(f"完成(共{elapsed}s)")
                        return img
                    raise RuntimeError(f"模型未返回图片。响应: {json.dumps(result, ensure_ascii=False)[:300]}")

            # ── 第二步：用已有task_id轮询（失败时重试轮询，不重新POST）──
            try:
                return _poll_task(base, api_key, task_id)
            except RuntimeError as poll_err:
                err_str = str(poll_err)
                # 内容审核失败：永久性失败，不重试
                if "任务失败" in err_str and "upstream" not in err_str.lower():
                    raise
                # 网络/轮询失败：用同一个task_id重试
                if attempt < 2:
                    _log(f"轮询失败(task_id={task_id}): {err_str[:80]}，用同一task_id重试轮询...")
                    last_err = err_str
                    time.sleep(5 * (attempt + 1))
                    continue
                raise

        except http.client.HTTPException as e:
            elapsed = round(time.time() - t0, 1)
            last_err = f"HTTP {e}"
            _log(f"失败(共{elapsed}s) 尝试{attempt+1}/3 - {last_err}")
            # POST阶段的网络错误：如果已有task_id，只重试轮询
            if task_id:
                if attempt < 2:
                    _log(f"已有task_id={task_id}，重试轮询而非重新POST")
                    time.sleep(5 * (attempt + 1))
                    continue
            else:
                # POST本身失败：可以重试POST
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    _log(f"  {wait}秒后重试POST...")
                    time.sleep(wait)
                    continue
            raise RuntimeError(last_err)
        except RuntimeError:
            raise
        except Exception as e:
            elapsed = round(time.time() - t0, 1)
            last_err = str(e)
            _log(f"失败(共{elapsed}s) 尝试{attempt+1}/3 - {last_err}")
            if task_id:
                if attempt < 2:
                    _log(f"已有task_id={task_id}，重试轮询而非重新POST")
                    time.sleep(5 * (attempt + 1))
                    continue
            else:
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    _log(f"  {wait}秒后重试POST...")
                    time.sleep(wait)
                    continue
            raise RuntimeError(last_err)
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass


def _download_url(url, save_path, max_redirects=5):
    """通过http.client下载URL内容并保存，支持重定向"""
    if max_redirects <= 0:
        raise RuntimeError("重定向次数过多")

    host, port, path, use_ssl = _parse_url(url)
    conn = _make_conn(host, port, use_ssl)
    try:
        conn.request("GET", path, headers={"User-Agent": "NovelToDrama/1.0"})
        resp = conn.getresponse()

        if resp.status in (301, 302, 307, 308):
            redirect_url = resp.getheader("Location")
            if redirect_url:
                conn.close()
                return _download_url(redirect_url, save_path, max_redirects - 1)

        if resp.status == 200:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(resp.read())
            return save_path
        else:
            error_body = resp.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"图片下载失败 HTTP {resp.status}: {error_body}")
    finally:
        conn.close()


def save_image(image_data, save_path):
    """保存图片到文件。"""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    if image_data.startswith("http"):
        _download_url(image_data, save_path)
    elif image_data.startswith("data:"):
        _, b64 = image_data.split(",", 1)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(b64))
    else:
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(image_data))

    return save_path
