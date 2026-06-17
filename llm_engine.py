# -*- coding: utf-8 -*-
"""Synapse — LLM 引擎（统一 OpenAI 兼容格式调用）"""

import json
import os
import ssl
import http.client
import math
import threading
import urllib.parse


def resolve_style_prompt(art_style_id, app_dir=None):
    """根据画风id查找完整prompt词，返回格式化字符串"""
    if not art_style_id:
        return ""
    if app_dir is None:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    # 查预设
    for fname in ("style_presets.json", "custom_styles.json"):
        fpath = os.path.join(app_dir, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    styles = json.load(f)
                for s in styles:
                    if s.get("id") == art_style_id:
                        # 只返回纯prompt文本，不拼接tone/lighting元数据
                        # 防止Mimo的Echo Effect直接回显标签
                        raw_prompt = s.get("prompt", "")
                        if raw_prompt:
                            # 剥离 [Rendering Style: xxx] 标签（character.txt模板自己路由）
                            import re
                            raw_prompt = re.sub(r'\[Rendering Style:\s*[^\]]+\]\s*', '', raw_prompt).strip()
                        return raw_prompt or s.get("name", "")
            except Exception:
                pass
    return art_style_id  # 找不到就原样返回


def build_style_context(settings, app_dir=None):
    """从settings构建完整的画风上下文字符串（含修饰词）"""
    art_style_id = settings.get("art_style", "")
    style_desc = resolve_style_prompt(art_style_id, app_dir)
    modifiers = []
    for mod_key in ("style_tone", "style_lighting", "style_texture"):
        mod_id = settings.get(mod_key, "")
        if mod_id:
            modifiers.append(mod_id)
    if modifiers:
        style_desc += " | Modifiers: " + ", ".join(modifiers)
    return style_desc


def _make_ssl_context():
    """创建SSL上下文，绕过PyInstaller环境可能的证书问题"""
    ctx = ssl.create_default_context()
    return ctx


def _parse_base_url(base_url):
    """解析base_url为 (host, port, path_prefix, use_ssl)"""
    parsed = urllib.parse.urlparse(base_url)
    use_ssl = parsed.scheme == "https"
    host = parsed.hostname
    port = parsed.port or (443 if use_ssl else 80)
    path_prefix = parsed.path.rstrip("/")
    return host, port, path_prefix, use_ssl


def call_llm(config, messages, temperature=0.7, max_tokens=8192, response_format=None, timeout=200,
             top_p=None, frequency_penalty=None):
    """
    统一 LLM 调用接口。
    config: dict with base_url, api_key, model
    messages: [{"role": "system"/"user"/"assistant", "content": "..."}]
    response_format: None or {"type": "json_object"}
    timeout: 请求超时秒数，默认300秒
    top_p: 核采样参数，控制选词范围（0-1），None用默认值
    frequency_penalty: 频率惩罚参数，避免重复用词（0-2），None用默认值
    返回: str (LLM 输出文本)
    """
    host, port, path_prefix, use_ssl = _parse_base_url(config["base_url"])
    api_path = f"{path_prefix}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p is not None:
        body["top_p"] = top_p
    if frequency_penalty is not None:
        body["frequency_penalty"] = frequency_penalty
    if response_format:
        body["response_format"] = response_format

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    # DEBUG: 记录请求发出时间
    import time as _t, datetime as _dt
    _llm_debug_log = r"D:\Phineas\Synapse\storyboard_debug.log"
    _llm_t0 = _t.time()
    try:
        with open(_llm_debug_log, "a", encoding="utf-8") as _f:
            _f.write(f"{_dt.datetime.now().strftime('%H:%M:%S')} call_llm SENDING -> {host}:{port}{api_path}, model={config['model']}, timeout={timeout}s, body={len(data)}B\n")
            _f.flush()
    except Exception:
        pass

    try:
        if use_ssl:
            ctx = _make_ssl_context()
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request("POST", api_path, body=data, headers=headers)
        resp = conn.getresponse()
        resp_data = resp.read().decode("utf-8")
        _llm_elapsed = _t.time() - _llm_t0
        try:
            with open(_llm_debug_log, "a", encoding="utf-8") as _f:
                _f.write(f"{_dt.datetime.now().strftime('%H:%M:%S')} call_llm RESPONSE <- status={resp.status}, size={len(resp_data)}B, elapsed={_llm_elapsed:.1f}s\n")
                _f.flush()
        except Exception:
            pass
        conn.close()

        if resp.status != 200:
            raise RuntimeError(f"LLM API Error {resp.status}: {resp_data[:500]}")
        result = json.loads(resp_data)
        return result["choices"][0]["message"]["content"]
    except RuntimeError:
        _llm_elapsed = _t.time() - _llm_t0
        try:
            with open(_llm_debug_log, "a", encoding="utf-8") as _f:
                _f.write(f"{_dt.datetime.now().strftime('%H:%M:%S')} call_llm RUNTIME_ERROR after {_llm_elapsed:.1f}s\n")
                _f.flush()
        except Exception:
            pass
        raise
    except Exception as e:
        _llm_elapsed = _t.time() - _llm_t0
        try:
            with open(_llm_debug_log, "a", encoding="utf-8") as _f:
                _f.write(f"{_dt.datetime.now().strftime('%H:%M:%S')} call_llm EXCEPTION after {_llm_elapsed:.1f}s: {e}\n")
                _f.flush()
        except Exception:
            pass
        raise RuntimeError(f"LLM 调用失败: {e}")


def call_llm_stream(config, messages, temperature=0.7, max_tokens=8192, timeout=200,
                     cancel_event=None, conn_holder=None, read_timeout=60,
                     top_p=None, frequency_penalty=None):
    """
    流式 LLM 调用，yield 每个 chunk 的文本。
    支持 cancel_event: 外部可在超时后请求取消，真正关闭socket。
    conn_holder: 可选 dict, 把 conn 暴露给外层以便 close()。
    read_timeout: 单次 socket 读超时(秒), 避免 readline() 永久阻塞。
    top_p: 核采样参数，控制选词范围（0-1），None用默认值
    frequency_penalty: 频率惩罚参数，避免重复用词（0-2），None用默认值
    """
    import socket as _socket

    host, port, path_prefix, use_ssl = _parse_base_url(config["base_url"])
    api_path = f"{path_prefix}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    body = {
        "model": config["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if top_p is not None:
        body["top_p"] = top_p
    if frequency_penalty is not None:
        body["frequency_penalty"] = frequency_penalty

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    try:
        if use_ssl:
            ctx = _make_ssl_context()
            conn = http.client.HTTPSConnection(host, port, timeout=read_timeout, context=ctx)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=read_timeout)

        if conn_holder is not None:
            conn_holder["conn"] = conn

        conn.request("POST", api_path, body=data, headers=headers)
        resp = conn.getresponse()

        if resp.status != 200:
            resp_data = resp.read().decode("utf-8", errors="replace")
            conn.close()
            raise RuntimeError(f"LLM API Error {resp.status}: {resp_data[:500]}")

        while True:
            if cancel_event is not None and cancel_event.is_set():
                try:
                    conn.close()
                except Exception:
                    pass
                return

            try:
                raw_line = resp.readline()
            except _socket.timeout:
                # 读超时不代表请求失败，继续轮询 cancel_event
                _log(f"call_llm_stream: readline timeout (read_timeout={read_timeout}s), continuing...")
                continue
            if not raw_line:
                break

            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    conn.close()
                    return
                try:
                    obj = json.loads(data_str)
                    if "error" in obj:
                        error_msg = obj["error"].get("message", "Unknown LLM Error")
                        yield f"\n[生成中断: {error_msg}]"
                        conn.close()
                        return
                    choices = obj.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content", "")
                    if content:
                        if not getattr(call_llm_stream, '_first_logged', False):
                            call_llm_stream._first_logged = True
                            _log(f"call_llm_stream: FIRST content chunk ({len(content)} chars): {content[:100]}")
                        yield content
                except json.JSONDecodeError:
                    pass

        conn.close()

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"LLM 流式调用失败: {e}")


def call_llm_stream_collect(config, messages, temperature=0.7, max_tokens=8192,
                             first_token_timeout=150, total_timeout=300):
    """流式调用LLM并收集完整输出，支持首token超时检测。
    超时后真正关闭底层连接，不让服务端继续空算。
    返回: str (完整LLM输出文本)
    """
    chunks = []
    first_chunk_received = threading.Event()
    stop_event = threading.Event()
    error_holder = [None]
    conn_holder = {}

    def _collect():
        try:
            for chunk in call_llm_stream(
                config, messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=total_timeout,
                cancel_event=stop_event,
                conn_holder=conn_holder,
                read_timeout=5,
            ):
                chunks.append(chunk)
                if not first_chunk_received.is_set():
                    _log(f"_collect: first chunk received after collecting")
                    first_chunk_received.set()
        except Exception as e:
            _log(f"_collect: exception: {e}")
            error_holder[0] = e
            if not first_chunk_received.is_set():
                first_chunk_received.set()

    t = threading.Thread(target=_collect, daemon=True)
    t.start()

    got_first = first_chunk_received.wait(timeout=first_token_timeout)
    if not got_first:
        _log(f"call_llm_stream_collect: FIRST TOKEN TIMEOUT after {first_token_timeout}s - cancelling request")
        stop_event.set()
        conn = conn_holder.get("conn")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        t.join(timeout=3)
        raise RuntimeError(
            "LLM stream: no response in {}s (request cancelled)".format(first_token_timeout))

    if error_holder[0]:
        stop_event.set()
        conn = conn_holder.get("conn")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise error_holder[0]

    remaining = max(1, total_timeout - first_token_timeout)
    t.join(timeout=remaining)

    if t.is_alive():
        stop_event.set()
        conn = conn_holder.get("conn")
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        t.join(timeout=3)
        raise RuntimeError(
            "LLM stream: total timeout after {}s (request cancelled)".format(total_timeout))

    if error_holder[0]:
        raise error_holder[0]

    return "".join(chunks)


def generate_titles(config, settings, templates_dir):
    """
    根据用户创意生成3-5个专业漫剧标题
    settings: dict with idea, genre, tone, art_style
    返回: dict with titles list
    """
    template = _load_template(templates_dir, "title.txt")
    system_prompt = template.replace("{idea}", settings.get("idea", "")).replace(
        "{genre}", ", ".join(settings.get("genre", []))
    ).replace("{tone}", settings.get("tone", "")).replace(
        "{art_style}", settings.get("art_style", "anime")
    )

    user_input = f"创意：{settings.get('idea', '')}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    import re as _re
    last_error = None
    for attempt in range(3):
        try:
            # 优先用流式累积，更稳定
            full_text = ""
            for chunk in call_llm_stream(config, messages, temperature=0.9, max_tokens=4096):
                full_text += chunk
            # 清理Markdown代码块
            cleaned = _re.sub(r'```(?:json)?\s*\n?|\s*```', '', full_text).strip()
            return _parse_json_response(cleaned)
        except Exception as e:
            last_error = e
            continue
    # 最后一次尝试用非流式
    result = call_llm(config, messages, temperature=0.9, max_tokens=4096)
    cleaned = _re.sub(r'```(?:json)?\s*\n?|\s*```', '', result).strip()
    return _parse_json_response(cleaned)


def generate_outline(config, project, templates_dir):
    """
    生成完整分集大纲
    project: 完整项目数据（包含settings和选中的title）
    返回: dict (大纲结构化数据)
    """
    template = _load_template(templates_dir, "outline.txt")
    settings = project.get("settings", {})
    expected_episodes = int(settings.get("episodes", 5))

    # 画风解析：用完整prompt词替代枚举值
    style_context = build_style_context(settings)

    # 填充模板变量
    system_prompt = template.replace("{title}", project.get("title", settings.get("title", "未命名"))
    ).replace("{idea}", settings.get("idea", "")
    ).replace("{genre}", ", ".join(settings.get("genre", []))
    ).replace("{art_style}", style_context
    ).replace("{episodes}", str(expected_episodes)
    ).replace("{episode_duration}", str(settings.get("episode_duration", 2))
    ).replace("{tone}", settings.get("tone", "")
    ).replace("{dialogue_style}", settings.get("dialogue_style", ""))

    user_input = f"创意：{settings.get('idea', '')}\n标题：{project.get('title', '未命名')}"

    # 最多重试2次（首次+1次重试）
    for attempt in range(2):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        result = call_llm(config, messages, temperature=0.8, max_tokens=10000)
        parsed = _parse_json_response(result)

        # 剥离校验锚点字段
        parsed.pop("_EOF", None)
        truncated = parsed.pop("_truncated", False)

        # 校验集数
        actual_episodes = parsed.get("chapters") or parsed.get("episodes") or []
        if len(actual_episodes) >= expected_episodes and not truncated:
            return parsed

        # 集数不足或被截断，重试并加强提示
        print(f"[OUTLINE] Attempt {attempt+1}: got {len(actual_episodes)}/{expected_episodes} episodes, retrying...")
        user_input = (
            f"创意：{settings.get('idea', '')}\n"
            f"标题：{project.get('title', '未命名')}\n"
            f"【重要提醒】你上次只输出了 {len(actual_episodes)} 集，但要求是 {expected_episodes} 集。"
            f"请务必输出完整的 {expected_episodes} 集 JSON，末尾必须包含 _EOF: true。"
        )

    # 2次都失败，返回最后一次结果（带警告）
    print(f"[OUTLINE] WARNING: Only got {len(actual_episodes)}/{expected_episodes} after 2 attempts")
    return parsed


def _detect_episode_markers(novel_text):
    """
    检测用户手动标注的分集标记。
    返回 (titles, splits) 或 (None, None)。
    titles: list[str] — 每集标题
    splits: list[tuple(int,int)] — (start_para, end_para) 段落索引范围
    """
    import re as _re

    paragraphs = [p for p in novel_text.split("\n\n") if p.strip()]
    total = len(paragraphs)

    # 中文数字映射
    CN_NUM = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,
              '九':9,'十':10,'十一':11,'十二':12,'十三':13,'十四':14,
              '十五':15,'十六':16,'十七':17,'十八':18,'十九':19,'二十':20,
              '二十一':21,'二十二':22,'二十三':23,'二十四':24,'二十五':25}

    # 在每个段落中查找分集标记
    # 第X集/章/回/节 [分隔符] [标题]
    MARKER_RE = _re.compile(
        r'^(?:第)\s*'                          # "第"
        r'([\d一二三四五六七八九十廿]+)\s*'       # 数字(阿拉伯或中文)
        r'(集|章|回|节|幕|部分|话|卷)'           # 量词
        r'[\s:：\-—\|｜·.、]*'                  # 可选分隔符
        r'(.{0,50})?$'                          # 可选标题(最多50字)
    )
    # Episode/Chapter + 数字
    EN_MARKER_RE = _re.compile(
        r'^(?:Episode|Chapter|Part|EP)\s*\.?\s*(\d+)\s*[\s:：\-—\.]*\s*(.{0,50})?$',
        _re.IGNORECASE
    )

    markers = []  # (para_idx, episode_num, title)
    for idx, para in enumerate(paragraphs):
        first_line = para.strip().split('\n')[0].strip()
        if not first_line or len(first_line) > 80:
            continue

        m = MARKER_RE.match(first_line)
        if m:
            num_str, _, title = m.group(1), m.group(2), m.group(3) or ''
            num = CN_NUM.get(num_str) or (int(num_str) if num_str.isdigit() else None)
            if num and num >= 1:
                markers.append((idx, num, title.strip()))
                continue

        m = EN_MARKER_RE.match(first_line)
        if m:
            num, title = int(m.group(1)), m.group(2) or ''
            markers.append((idx, num, title.strip()))

    if len(markers) < 2:
        return None, None

    # 按段落顺序排序(不按集号，因为有些小说不按顺序标)
    markers.sort(key=lambda x: x[0])

    # 去重：同一个段落只保留第一个标记
    seen = set()
    unique = []
    for m in markers:
        if m[0] not in seen:
            seen.add(m[0])
            unique.append(m)
    markers = unique

    if len(markers) < 2:
        return None, None

    print(f"[PARSE_NOVEL] 检测到 {len(markers)} 个分集标记: {[(m[1], m[2][:20]) for m in markers]}")

    # 构造 splits 和 titles
    titles = []
    splits = []
    for i, (para_idx, ep_num, title) in enumerate(markers):
        start = para_idx
        # end = 下一个标记的前一段落，或者最后一个段落
        if i < len(markers) - 1:
            end = markers[i+1][0] - 1
        else:
            end = total - 1
        if end < start:
            end = start
        splits.append((start, end))
        titles.append(title if title else f"第{ep_num}集")

    return titles, splits


def parse_novel(config, novel_text, episodes, episode_duration, templates_dir):
    """
    解析用户上传的小说，提取标题、大纲、角色、分集切割点。
    如果用户已在文本中标注分集标记（如"第一集"、"第二章"），优先使用用户标注。
    返回: dict with keys: titles, outline (summary, characters, chapters)
    """
    import re as _re

    # ── 第一步：检测用户手动标注的分集标记 ──
    user_titles, user_splits = _detect_episode_markers(novel_text)

    paragraphs = [p for p in novel_text.split("\n\n") if p.strip()]
    total_paragraphs = len(paragraphs)

    if user_splits is not None:
        # 用户已标注分集 → 直接使用，只让LLM提取角色和全局摘要
        n_chapters = len(user_splits)
        print(f"[PARSE_NOVEL] 使用用户标注的 {n_chapters} 集分集（跳过LLM拆分）")

        # 构造 chapters（先用标记的标题，摘要后面LLM补）
        chapters = []
        for i, (start, end) in enumerate(user_splits):
            chapters.append({
                "title": user_titles[i],
                "summary": "",
                "start_paragraph": start,
                "end_paragraph": end,
            })

        # 让LLM提取角色 + 全局摘要 + 每集摘要 + 标题建议
        # 拼出各集内容供LLM理解
        chapter_texts = []
        for i, ch in enumerate(chapters):
            s, e = ch["start_paragraph"], ch["end_paragraph"]
            text = "\n\n".join(paragraphs[s:e+1])
            chapter_texts.append(f"=== 第{i+1}集（{ch['title']}）===\n{text}")

        meta_context = f"""=== 小说原文（已按用户标注分为 {n_chapters} 集）===
{chr(10).join(chapter_texts)}

=== 任务 ===
用户已在小说中手动标注了分集，你不需要重新拆分。
请只提取以下信息：
1. titles: 3-5个整部剧的标题建议
2. outline.summary: 全局摘要（1-2句话）
3. outline.characters: 所有角色信息
4. outline.chapters: 每集的summary（1-2句话概要），title直接使用用户标注的标题

输出JSON格式与标准格式相同，chapters数组长度必须为 {n_chapters}。
"""

        meta_template = """You are a novel structure analyst. The user has already split their novel into episodes. Your job is ONLY to extract metadata (characters, summaries, title suggestions). Do NOT re-split the novel.

Output valid JSON only. No markdown code blocks. No text before or after JSON.

{
  "titles": ["标题1", "标题2", "标题3"],
  "outline": {
    "summary": "全局摘要",
    "characters": [
      {"name": "角色名", "brief": "外貌描述", "personality": "性格描述"}
    ],
    "chapters": [
      {"title": "沿用用户标注的标题", "summary": "本集概要", "start_paragraph": 0, "end_paragraph": 15}
    ]
  }
}"""

        messages = [
            {"role": "system", "content": meta_template},
            {"role": "user", "content": meta_context},
        ]

        last_error = None
        for attempt in range(3):
            try:
                result = call_llm(config, messages, temperature=0.3, max_tokens=10000, timeout=900)
                cleaned = _re.sub(r'```(?:json)?\s*\n?|\s*```$', '', result, flags=_re.MULTILINE).strip()
                parsed = _parse_json_response(cleaned)

                llm_chapters = parsed.get("outline", {}).get("chapters", [])
                characters = parsed.get("outline", {}).get("characters", [])

                if not characters:
                    print(f"[PARSE_NOVEL] Attempt {attempt+1}: no characters found, retrying...")
                    continue

                if not parsed.get("titles"):
                    parsed["titles"] = ["未命名"]

                # 用LLM返回的摘要补全chapters，但保留用户标注的标题和段落范围
                for i in range(n_chapters):
                    if i < len(llm_chapters):
                        llm_ch = llm_chapters[i]
                        # 标题优先用用户标注的
                        if not chapters[i]["title"] or chapters[i]["title"].startswith("第"):
                            chapters[i]["title"] = llm_ch.get("title", chapters[i]["title"])
                        # 摘要用LLM生成的
                        if llm_ch.get("summary"):
                            chapters[i]["summary"] = llm_ch["summary"]

                parsed["outline"]["chapters"] = chapters
                print(f"[PARSE_NOVEL] 用户标注分集解析成功：{n_chapters} 集，{len(characters)} 个角色")
                return parsed

            except Exception as e:
                last_error = e
                print(f"[PARSE_NOVEL] Attempt {attempt+1} failed: {e}")
                continue

        # LLM全部失败但分集已有，返回最低可用结果
        print(f"[PARSE_NOVEL] LLM元数据提取失败，返回基础结构")
        return {
            "titles": ["未命名"],
            "outline": {
                "summary": "",
                "characters": [],
                "chapters": chapters,
            }
        }

    # ── 原有逻辑：无用户标注，让LLM自动拆分 ──
    template = _load_template(templates_dir, "parse_novel.txt")

    context = f"""=== 小说原文 ===
{novel_text}

=== 目标参数 ===
集数: {episodes} 集
每集时长: {episode_duration} 秒
原文段落数: {total_paragraphs} 段
"""

    messages = [
        {"role": "system", "content": template},
        {"role": "user", "content": context},
    ]

    last_error = None
    for attempt in range(3):
        try:
            result = call_llm(config, messages, temperature=0.3, max_tokens=10000, timeout=900)
            cleaned = _re.sub(r'```(?:json)?\s*\n?|\s*```$', '', result, flags=_re.MULTILINE).strip()
            parsed = _parse_json_response(cleaned)

            # 验证结构
            titles = parsed.get("titles", [])
            outline = parsed.get("outline", {})
            chapters = outline.get("chapters", [])
            characters = outline.get("characters", [])

            if len(chapters) != episodes:
                print(f"[PARSE_NOVEL] Attempt {attempt+1}: got {len(chapters)}/{episodes} chapters, retrying...")
                continue

            if not characters:
                print(f"[PARSE_NOVEL] Attempt {attempt+1}: no characters found, retrying...")
                continue

            if not titles:
                parsed["titles"] = ["未命名"]

            # 修正段落索引边界
            for i, ch in enumerate(chapters):
                if i == 0:
                    ch["start_paragraph"] = 0
                if i < len(chapters) - 1:
                    ch["end_paragraph"] = min(ch["end_paragraph"], chapters[i + 1]["start_paragraph"] - 1)
                else:
                    ch["end_paragraph"] = total_paragraphs - 1

            return parsed

        except Exception as e:
            last_error = e
            print(f"[PARSE_NOVEL] Attempt {attempt+1} failed: {e}")
            continue

    raise RuntimeError(f"小说解析失败（3次重试）: {last_error}")


def generate_outline_stream(config, project, templates_dir):
    """
    流式生成完整分集大纲，yield每个chunk的文本。
    最后一个yield是解析后的JSON dict。
    """
    template = _load_template(templates_dir, "outline.txt")
    settings = project.get("settings", {})
    expected_episodes = int(settings.get("episodes", 5))

    style_context = build_style_context(settings)

    system_prompt = template.replace("{title}", project.get("title", settings.get("title", "未命名"))
    ).replace("{idea}", settings.get("idea", "")
    ).replace("{genre}", ", ".join(settings.get("genre", []))
    ).replace("{art_style}", style_context
    ).replace("{episodes}", str(expected_episodes)
    ).replace("{episode_duration}", str(settings.get("episode_duration", 2))
    ).replace("{tone}", settings.get("tone", "")
    ).replace("{dialogue_style}", settings.get("dialogue_style", ""))

    user_input = f"创意：{settings.get('idea', '')}\n标题：{project.get('title', '未命名')}"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    full_text = ""
    for chunk in call_llm_stream(config, messages, temperature=0.8, max_tokens=10000):
        full_text += chunk
        yield {"type": "chunk", "content": chunk}

    # Parse the final JSON
    parsed = _parse_json_response(full_text)

    # 剥离校验锚点，但保留 _truncated 供上层 API 路由校验
    parsed.pop("_EOF", None)

    yield {"type": "done", "outline": parsed}


def _log_char(msg):
    print(f"[CHAR_PROMPT] {msg}", flush=True)


def generate_character_prompt(config, character_info, art_style, templates_dir):
    """
    第4步：为角色生成专业级图片提示词
    character_info: 角色设定信息
    返回: str (英文图片提示词)
    """
    import re
    template = _load_template(templates_dir, "character.txt")
    system_prompt = template.replace("{art_style}", art_style)

    char_name = character_info.get('name', 'unknown')
    _log_char(f"开始生成角色prompt: {char_name}")

    # 恢复全量JSON输入（保留模板全部专业规则），末尾加格式指令防JSON回显
    user_content = (
        json.dumps(character_info, ensure_ascii=False) +
        "\n\nIMPORTANT: Output ONLY the final English prompt paragraph as specified in the system instructions. "
        "Do NOT output JSON. Do NOT include any code blocks, explanations, or metadata."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    prompt = call_llm(config, messages, temperature=0.7, max_tokens=2048)

    if not prompt:
        prompt = ""

    # 清理Markdown代码块标记
    prompt = re.sub(r'```(?:json)?\s*\n?|\s*```', '', prompt).strip()

    # 防御2：检测JSON回显 → 第二次LLM调用（强化指令重试）
    is_json_like = '{' in prompt and '}' in prompt and len(prompt) < 800
    if is_json_like:
        _log_char(f"检测到JSON回显，触发第二次LLM调用重试...")
        try:
            retry_messages = [
                {
                    "role": "system",
                    "content": system_prompt + "\n\nABSOLUTE RULE: Your response MUST be a plain English paragraph ONLY. "
                        "DO NOT output JSON. DO NOT use { } or [ ]. DO NOT echo the input. "
                        "Write 150-350 words of English descriptive text for an image generation AI."
                },
                {
                    "role": "user",
                    "content": user_content
                },
            ]
            prompt = call_llm(config, retry_messages, temperature=0.7, max_tokens=2048)
            prompt = re.sub(r'```(?:json)?\s*\n?|\s*```', '', prompt or '').strip()
            _log_char(f"第二次调用完成: prompt长度={len(prompt)}")
        except Exception as e:
            _log_char(f"第二次LLM调用失败: {e}")

    # 防御3：终极Fallback安全网 — 增强版（含角色名+结构化五官标签）
    is_still_bad = len(prompt) < 15 or ('{' in prompt and '}' in prompt)
    if is_still_bad:
        _log_char(f"触发终极Fallback安全网，强制构建增强版prompt...")
        # 智能推断gender：查字段→匹配关键词→兜底Male
        raw_gender = character_info.get('gender', '')
        if raw_gender:
            gender = raw_gender
        else:
            _desc = (character_info.get('description', '') + ' ' + character_info.get('appearance', '') + ' ' + character_info.get('personality', '')).lower()
            _name = char_name.lower()
            if any(k in _desc for k in ['男', 'male', '他', '先生', '少年', '男', 'his ', 'him ', 'man ', 'boy ', 'masculine', 'husband', 'father', 'brother', 'son', 'prince', 'king', 'lord']):
                gender = 'Male'
            elif any(k in _desc for k in ['女', 'female', '她', '女士', '少女', 'her ', 'she ', 'woman ', 'girl ', 'feminine', 'wife', 'mother', 'sister', 'daughter', 'princess', 'queen', 'lady']):
                gender = 'Female'
            elif any(k in _name for k in ['公主', 'queen', 'princess', 'girl']):
                gender = 'Female'
            else:
                gender = 'Male'  # 兜底Male，消除Female偏见
        appearance = character_info.get('appearance', '')
        clothing = character_info.get('clothing', '')
        face_hint = appearance if appearance else f"a unique {gender.lower()} character"
        cloth_hint = clothing if clothing else "detailed outfit with distinct accessories"

        fallback_tags = [
            "16:9 landscape aspect ratio, character sheet, turnaround reference photo",
            "three horizontal panels arranged left to right: front view on the left, back view in the center, three-quarter front lateral view on the right, equal width for each panel, seamless horizontal alignment",
            "ABSOLUTE SOLID PURE WHITE BACKGROUND. NO ENVIRONMENT. NO SCENE. NO PROPS. NO PATTERNS. NO TEXTURES ON BACKGROUND.",
            f"{gender} character",
            f"the character {char_name}, {face_hint}",
            "Face: distinct face shape, defined nose type, clear lip shape, distinct eyebrow style, pronounced cheekbones and chin landmarks",
            "Eyes: specific eye shape with exact iris color, gaze directed looking directly at the camera, identical eye details in all views",
            "Hair: specific hairstyle with length, texture, and color details",
            "Skin: specific skin tone and complexion description",
            f"Somatotype: {'defined waist and slender feminine silhouette' if 'Female' in gender or 'female' in gender else 'broad shoulders and masculine build'}",
            f"Clothing: {cloth_hint}",
            art_style,
            "studio lighting, uniform soft flat diffused lighting, completely shadows-free rendering, no harsh shading, no contrast blockages",
            "hyper-detailed, sharp focus, intricate texture mapping, professional concept art character asset sheet",
            "no text, no watermark, no signature, no extra limbs, no blurry elements, no deformed hands, no distorted faces, no background clutter, no multiple characters, no gender swap, no opposite gender features"
        ]
        prompt = ", ".join([str(t).strip() for t in fallback_tags if t])
        _log_char(f"Fallback完成: prompt长度={len(prompt)}")

    return prompt


def _word_count_range(episode_duration):
    """根据每集时长返回字数范围字符串（缩短15%让分镜保留更多细节）"""
    dur = int(episode_duration)
    if dur <= 45:
        return "700-850字"
    elif dur <= 55:
        return "850-1100字"
    elif dur <= 75:
        return "1200-1550字"
    elif dur <= 100:
        return "1700-2400字"
    elif dur <= 150:
        return "3000-3800字"
    else:
        return "3800-5100字"

def generate_novel_chapter(config, outline, chapter_index, previous_summaries, templates_dir, episode_duration=120):
    """
    第5步：生成一集小说正文
    返回: str (小说正文)
    """
    template = _load_template(templates_dir, "novel.txt")

    _oc = outline.get('chapters') or outline.get('episodes') or []

    # 大纲瘦身：只传当前集 + 前后各1集上下文 + 全局设定
    global_info = {k: v for k, v in outline.items() if k not in ('chapters', 'episodes')}
    start = max(0, chapter_index - 1)
    end = min(len(_oc), chapter_index + 2)
    nearby_episodes = []
    for i in range(start, end):
        ep = _oc[i].copy()
        ep['_episode_number'] = i + 1
        nearby_episodes.append(ep)

    slim_outline = {
        **global_info,
        "episodes": nearby_episodes,
        "_note": f"共{len(_oc)}集，当前只展示第{start+1}-{end}集作为上下文窗口"
    }

    context = f"""=== 大纲 ===
{json.dumps(slim_outline, ensure_ascii=False, indent=2)}

=== 当前要写的集数：第{chapter_index + 1}集 ===
本集标题：{_oc[chapter_index]['title']}
本集概要：{_oc[chapter_index]['summary']}

=== 目标参数 ===
每集时长: {episode_duration} 秒
目标字数: {_word_count_range(episode_duration)}（这是硬性限制，超出即为失败）

=== 前情提要 ===
{previous_summaries if previous_summaries else '这是第一集，没有前情。'}
"""

    messages = [
        {"role": "system", "content": template},
        {"role": "user", "content": context},
    ]

    return call_llm(config, messages, temperature=0.85, max_tokens=8192)


def generate_novel_chapter_stream(config, outline, chapter_index, previous_summaries, templates_dir, episode_duration=120):
    """
    流式生成一集小说正文，yield chunk文本，最后yield done事件。
    内置3次重试：如果LLM流式调用失败且尚未yield任何chunk，自动重试。
    """
    template = _load_template(templates_dir, "novel.txt")

    _oc = outline.get('chapters') or outline.get('episodes') or []

    global_info = {k: v for k, v in outline.items() if k not in ('chapters', 'episodes')}
    start = max(0, chapter_index - 1)
    end = min(len(_oc), chapter_index + 2)
    nearby_episodes = []
    for i in range(start, end):
        ep = _oc[i].copy()
        ep['_episode_number'] = i + 1
        nearby_episodes.append(ep)

    slim_outline = {
        **global_info,
        "episodes": nearby_episodes,
        "_note": f"共{len(_oc)}集，当前只展示第{start+1}-{end}集作为上下文窗口"
    }

    context = f"""=== 大纲 ===
{json.dumps(slim_outline, ensure_ascii=False, indent=2)}

=== 当前要写的集数：第{chapter_index + 1}集 ===
本集标题：{_oc[chapter_index]['title']}
本集概要：{_oc[chapter_index]['summary']}

=== 目标参数 ===
每集时长: {episode_duration} 秒
目标字数: {_word_count_range(episode_duration)}（这是硬性限制，超出即为失败）

=== 前情提要 ===
{previous_summaries if previous_summaries else '这是第一集，没有前情。'}
"""

    stream_messages = [
        {"role": "system", "content": template},
        {"role": "user", "content": context},
    ]

    max_retries = 3
    last_error = None
    for attempt in range(max_retries):
        full_text = ""
        yielded_any = False
        try:
            for chunk in call_llm_stream(config, stream_messages, temperature=0.85, max_tokens=8192):
                full_text += chunk
                yielded_any = True
                yield {"type": "chunk", "content": chunk}
            # 成功完成
            yield {"type": "done", "novel_text": full_text}
            return
        except Exception as e:
            last_error = e
            _log(f"generate_novel_chapter_stream attempt {attempt+1}/{max_retries} failed: {e}")
            if yielded_any:
                # 已经yield了部分chunk，无法干净重试，把已有的当结果
                _log(f"already yielded {len(full_text)} chars, using partial result")
                if len(full_text.strip()) > 100:
                    yield {"type": "done", "novel_text": full_text}
                    return
                else:
                    yield {"type": "error", "message": f"生成中断: {e}"}
                    return
            # 还没yield任何chunk，可以安全重试
            if attempt < max_retries - 1:
                import time as _t
                _t.sleep(2)
                continue

    # 全部重试失败
    yield {"type": "error", "message": f"生成失败(重试{max_retries}次): {last_error}"}


def _inject_characters_in_scene(clips, all_characters=None):
    """
    从dialogue + scene_description中自动提取每个clip的出场角色名。
    1) dialogue中的character字段（精确匹配）
    2) a_track.scene_description中的角色名（子串匹配，含简称匹配）
    后处理步骤，不依赖LLM额外输出字段。
    """
    char_names = [c["name"] for c in all_characters] if all_characters else []
    # 构建简称映射："李父（李德福）" -> "李父"，同时保留原名
    name_variants = []  # [(full_name, short_name), ...]
    for cname in char_names:
        short = cname
        for sep in ["（", "(", "["]:
            if sep in cname:
                short = cname[:cname.index(sep)].strip()
                break
        name_variants.append((cname, short))
    for clip in clips:
        names = set()
        # 从dialogue提取
        b_track = clip.get("b_track", {})
        for d in b_track.get("dialogue", []):
            if isinstance(d, dict) and d.get("character"):
                dchar = d["character"]
                names.add(dchar)
                # dialogue里的角色名可能是简称，反查全名
                for full, short in name_variants:
                    if dchar == short and dchar != full:
                        names.add(full)
        # 从scene_description提取（全名+简称子串匹配）
        a_track = clip.get("a_track", {})
        scene_desc = a_track.get("scene_description", "")
        if scene_desc:
            for full, short in name_variants:
                if full in scene_desc or short in scene_desc:
                    names.add(full)
        clip["characters_in_scene"] = list(names)


def _build_novel_windows(novel_text, batch_total, overlap_chars=50, context_chars=200):
    """把正文切成 batch_total 个窗口，带少量重叠，避免每批都重复整章全文。
    返回: list[dict] 每个元素 {"prev_tail": str, "main": str, "next_head": str}
      - prev_tail: 上一个窗口的尾部文本（供尾帧参考衔接）
      - main: 本窗口主文本
      - next_head: 下一个窗口的开头文本（供尾帧衔接）
    """
    text = (novel_text or "").strip()
    empty = {"prev_tail": "", "main": text, "next_head": ""}
    if not text:
        return [empty.copy() for _ in range(batch_total)]
    if batch_total <= 1 or len(text) <= 1200:
        return [empty.copy() for _ in range(batch_total)]

    step = max(800, math.ceil(len(text) / batch_total))
    main_windows = []
    n = len(text)

    for i in range(batch_total):
        start = max(0, i * step - overlap_chars)
        end = min(n, (i + 1) * step + overlap_chars)
        if start >= end:
            main_windows.append(text)
            continue
        while start > 0 and start < n and text[start] not in "。！？；\n":
            start -= 1
            if i > 0 and (i * step - start) > step + overlap_chars:
                break
        while end < n and text[end - 1] not in "。！？；\n":
            end += 1
            if end >= n:
                end = n
                break
        chunk = text[start:end].strip()
        if not chunk:
            chunk = text
        main_windows.append(chunk)

    while len(main_windows) < batch_total:
        main_windows.append(text)
    main_windows = main_windows[:batch_total]

    # 构建 enriched 窗口：附带上下文
    enriched = []
    for i in range(batch_total):
        main = main_windows[i]
        # 上一个窗口的尾部
        if i > 0:
            prev_main = main_windows[i - 1]
            prev_tail = prev_main[-context_chars:] if len(prev_main) > context_chars else prev_main
        else:
            prev_tail = ""
        # 下一个窗口的开头
        if i < batch_total - 1:
            next_main = main_windows[i + 1]
            next_head = next_main[:context_chars] if len(next_main) > context_chars else next_main
        else:
            next_head = ""
        enriched.append({"prev_tail": prev_tail, "main": main, "next_head": next_head})

    return enriched


def _extract_clip_context(clip):
    """从clip中提取上下文信息，兼容多种LLM输出格式"""
    a = clip.get("a_track", {})
    b = clip.get("b_track", {})
    c = clip.get("c_track", {})
    
    # 场景：优先b_track.scene_description，降级a_track
    scene = b.get("scene_description") or a.get("scene_description") or ""
    
    # 镜头：b_track.camera_movement
    camera = b.get("camera_movement") or a.get("camera", "")
    
    # 台词
    dialogues = b.get("dialogue", [])
    if dialogues:
        dialogue_text = "；".join(
            f"{d.get('character','')}: {d.get('line','')}" 
            for d in dialogues if isinstance(d, dict)
        )
    else:
        dialogue_text = "(无台词)"
    
    # 视觉焦点：A轨reference_prompt前80字
    visual = (a.get("reference_prompt") or a.get("scene_description") or "")[:80]
    
    # 尾帧：C轨tail_frame_prompt（用于下一个clip的视觉衔接）
    tail_frame = (c.get("tail_frame_prompt") or c.get("scene_description") or "")[:80]
    
    return {
        "scene": scene[:300] if scene else "(无场景描述)",
        "camera": camera[:100] if camera else "(无镜头信息)",
        "dialogue": dialogue_text[:200],
        "visual": visual if visual else "(无视觉信息)",
        "tail_frame": tail_frame if tail_frame else "(无尾帧信息)",
    }


def _create_placeholder_clip(batch_idx, clip_duration):
    """降级占位clip（当LLM连续失败时使用）"""
    return {
        "clip_id": batch_idx + 1,
        "duration": clip_duration,
        "a_track": {
            "reference_prompt": "placeholder scene, simple background",
            "scene_description": "placeholder scene",
            "camera": "static wide shot",
            "negative_prompt": "",
        },
        "b_track": {
            "scene_description": "placeholder scene",
            "camera_movement": "static",
            "dialogue": [],
            "narration": "",
            "sfx": "",
            "music_style": "",
        },
        "c_track": {
            "tail_frame_prompt": "placeholder scene ending",
            "scene_description": "placeholder scene ending",
            "camera": "static wide shot",
            "negative_prompt": "",
        },
    }


def generate_storyboard(config, novel_text, chapter_info, outline, characters,
                         clip_duration, art_style, templates_dir, episode_duration=120):
    """
    第6步：生成双轨分镜脚本（单clip模式）
    每次调用LLM只生成1个clip，降低单次请求量，减少服务端压力。
    返回: list[dict] 每个片段包含 a_track 和 b_track
    """
    import time
    print("[SB-DEBUG] generate_storyboard entered", flush=True)
    LOG_FILE = r"D:\Phineas\Synapse\storyboard_debug.log"
    print(f"[SB-DEBUG] LOG_FILE={LOG_FILE}", flush=True)
    def log_debug(msg):
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S") + " " + msg + "\n")
        except Exception as _e:
            print(f"[SB-DEBUG] log_debug write error: {_e}: {msg}", flush=True)
    log_debug("=" * 60)
    print("[SB-DEBUG] log_debug initialized OK", flush=True)
    log_debug("generate_storyboard START batched mode v2")
    template = _load_template(templates_dir, "storyboard.txt")
    clip_count = max(2, round(episode_duration / clip_duration))
    BATCH_SIZE = 1  # 每次只生成1个clip，降低单次请求量

    # 构建 system_prompt
    # 注入模板参数。注意：clip_count设为1，因为每次只生成1个clip。
    # 模板中的"Hard Clip Count Constraint"会被批次指令覆盖。
    system_prompt = template.replace("{art_style}", art_style).replace(
        "{clip_duration}", str(clip_duration)
    ).replace(
        "{episode_duration}", str(episode_duration)
    ).replace(
        "{clip_count}", "1"
    ).replace(
        "{clip_count_min}", "1"
    ).replace(
        "{clip_count_max}", "1"
    )

    char_summary = ""
    for char in characters:
        char_summary += f"- {char['name']}: {char.get('brief', '')}\n"

    outline_chapters = outline.get("chapters") or outline.get("episodes") or []
    opening_hook = outline_chapters[0].get("opening_hook", "") if outline_chapters else ""
    cliffhanger = outline_chapters[-1].get("cliffhanger", "") if outline_chapters else ""

    base_context = f"""
=== 角色列表 ===
{char_summary}

=== 本集信息 ===
标题：{chapter_info.get('title', '')}
概要：{chapter_info.get('summary', '')}

=== 声音风格 ===
{outline.get('sound_style', {}).get('总体', '根据场景自动匹配')}
"""

    # 计算批次 + 正文窗口切片（三段式：上一clip尾部 + 本clip正文 + 下一clip开头）
    clip_indices = list(range(clip_count))
    batches = [clip_indices[i:i + BATCH_SIZE] for i in range(0, len(clip_indices), BATCH_SIZE)]
    total_batches = len(batches)
    novel_windows = _build_novel_windows(novel_text, total_batches, overlap_chars=50, context_chars=200)

    all_clips = []
    t0 = time.time()

    # ── 串行模式：每个clip按顺序生成，前clip输出注入下一个 ──
    used_dialogues = []  # 串行模式，不需要锁

    # 预分配叙事节拍（基于位置，不依赖运行时顺序）
    _narrative_beats = [
        "Setup/Establishing (set the scene, introduce tension)",
        "Rising Suspicion (doubt, questioning, probing)",
        "Emotional Escalation (anger, fear, desperation intensifies)",
        "Revelation/Turning Point (truth exposed, major shift)",
        "Climax/Decision (character commits to action)",
        "Cliffhanger/Resolution Hook (unresolved tension, urge to continue)",
    ]

    # ── 串行生成单个batch的函数 ──
    def _generate_one_batch(batch_idx, previous_clip=None):
        """串行生成单个batch（前clip输出注入下一个）"""
        batch = batches[batch_idx]
        batch_num = batch_idx + 1
        clip_start = batch[0] + 1
        is_first = (batch_idx == 0)
        is_last = (batch_idx == total_batches - 1)

        # 给每个clip完整小说正文 + 前后clip的衔接参考
        win = novel_windows[batch_idx] if batch_idx < len(novel_windows) else {"prev_tail": "", "main": novel_text, "next_head": ""}
        prev_tail = win["prev_tail"]
        next_head = win["next_head"]

        batch_instructions = f"""

===== 批次指令（由系统注入，优先级最高） =====

**你必须忽略系统提示中关于clip数量的约束。本次只需要生成 1 个 clip：第 {clip_start} 个。**
输出格式：一个只包含1个clip对象的JSON数组 [ {{{{...}}}} ]。

本集总共 {clip_count} 个 clip，分 {total_batches} 批并行生成。当前是第 {batch_num}/{total_batches} 批。

**叙事时序规则（最重要）：**
下方提供了本clip对应的小说片段。请严格按照该片段内容生成第 {clip_start} 个clip。
- 只基于提供的小说片段生成，不要跳到其他片段的内容
- 前后衔接参考仅用于保证场景连贯，不要重复或提前生成
"""
        # 三轨模式：每个clip都输出 a_track(参考图) + b_track(音视频) + c_track(尾帧)
        batch_instructions += "- **每个clip必须输出三轨：a_track（含reference_prompt参考图）、b_track（音视频）、c_track（含tail_frame_prompt尾帧）。三轨都有各自的scene_description、camera、negative_prompt。**\n"
        if is_first:
            batch_instructions += f"- 本集第一个 clip MUST 对应 opening_hook：{opening_hook}\n"
        if is_last:
            batch_instructions += f"- 本集最后一个 clip MUST 对应 cliffhanger：{cliffhanger}\n"

        # 叙事节拍分配（基于位置）
        beat_idx = min(batch_idx, len(_narrative_beats) - 1)
        batch_instructions += f"\n**NARRATIVE BEAT (this clip's dramatic function):** {_narrative_beats[beat_idx]}\n"
        batch_instructions += "Your dialogue for this clip MUST align with this beat. Do NOT use a beat already covered by previous clips.\n"

        # 读取已完成clip的台词（防重复）
        if used_dialogues:
            batch_instructions += f"\n**ALREADY USED DIALOGUE (BANNED — do NOT repeat or paraphrase any of these):**\n" + "\n".join(used_dialogues) + "\n"
        batch_instructions += "Your dialogue line MUST be completely different from all lines above — different words, different meaning, different emotional function.\n"
        # 注入角色视觉锚点（防LLM在A/C轨之间改写外观描述）
        if characters:
            anchor_lines = []
            for char in characters:
                brief = char.get('brief', '')
                if brief:
                    anchor_lines.append(f"  {char['name']}: {brief}")
            if anchor_lines:
                batch_instructions += "\n**CHARACTER VISUAL ANCHOR (copy these EXACT phrases into reference_prompt and tail_frame_prompt — do NOT paraphrase):**\n" + "\n".join(anchor_lines) + "\n"

        # ── 前clip上下文注入（串行衔接核心）──
        if previous_clip is not None:
            prev_ctx = _extract_clip_context(previous_clip)
            batch_instructions += f"""
**前一个clip的完整输出（你必须与之衔接）：**
- 场景描述：{prev_ctx['scene']}
- 镜头运动：{prev_ctx['camera']}
- 台词：{prev_ctx['dialogue']}
- 视觉焦点：{prev_ctx['visual']}
- 尾帧：{prev_ctx['tail_frame']}

**衔接规则：**
1. 场景过渡必须平滑（如果前clip在室内，你不能突然跳到完全不同的地方，除非有过渡）
2. 镜头运动必须连贯（前clip是推镜，你接拉镜或固定镜，不要跳跃）
3. 情绪必须递进（不能突然倒退到平静，除非有剧情节奏转折）
4. 台词不能重复或改述前clip的任何台词
"""
        else:
            # 第一个clip：用opening_hook代替
            batch_instructions += f"""
**这是本集第一个clip（没有前clip参考）：**
- 开场钩子：{opening_hook}
- 本集标题：{chapter_info.get('title', '')}
- 本集概要：{chapter_info.get('summary', '')}

**要求：** 建立场景、引入角色、设置悬念。开场必须抓住观众注意力。
"""

        # 构建用户消息：只发本clip对应的小说片段 + 前后衔接参考（不发全文，避免LLM估算百分比出错）
        context_parts = base_context + batch_instructions

        # 明确告知本clip在全文中的位置
        segment_char_start = len(novel_text) * batch_idx // total_batches
        segment_char_end = len(novel_text) * (batch_idx + 1) // total_batches
        context_parts += f"\n=== 本clip对应的小说片段（第{segment_char_start+1}~{segment_char_end}字，共{len(win['main'])}字）===\n{win['main']}\n"
        if prev_tail:
            context_parts += f"\n=== 上一个clip的小说末尾（前文衔接，不要重复生成）===\n{prev_tail}\n"
        if next_head:
            context_parts += f"\n=== 下一个clip的小说开头（后文预告，不要提前生成）===\n{next_head}\n"

        user_message = context_parts

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        log_debug("batch {}/{} (parallel) sending {} chars novel_text, system_prompt {} chars".format(
            batch_num, total_batches, len(novel_text), len(system_prompt)))

        # LLM API级重试（处理502、超时、rate limit等API错误）
        result = None
        for api_attempt in range(3):
            try:
                result = call_llm(config, messages, temperature=0.7, max_tokens=10000, timeout=200,
                                  top_p=0.9, frequency_penalty=0.3)
                log_debug("batch {} LLM returned {} chars".format(batch_num, len(result) if isinstance(result, str) else str(type(result))))
                break
            except RuntimeError as e:
                if api_attempt < 2:
                    # 指数退避：429专用3/6/12秒，其他错误2/4/8秒
                    is_429 = "429" in str(e)
                    base = 3 if is_429 else 2
                    wait = base * (2 ** api_attempt)
                    log_debug("batch {} LLM API error (attempt {}/3): {}, retrying in {}s".format(
                        batch_num, api_attempt + 1, e, wait))
                    time.sleep(wait)
                else:
                    log_debug("batch {} LLM API failed after 3 attempts: {}".format(batch_num, e))
                    raise RuntimeError("分镜脚本第 {} 批LLM调用失败（3次重试）: {}".format(batch_num, e))

        try:
            clips = _parse_json_response(result)
        except Exception as e:
            log_debug("batch {} parse error: {}".format(batch_num, e))
            clips = None

        for _retry in range(3):
            if isinstance(clips, list):
                break
            log_debug("batch {} retry {}/3".format(batch_num, _retry + 1))
            retry_msgs = list(messages) + [
                {"role": "assistant", "content": result if isinstance(result, str) else ""},
                {"role": "user", "content": "你的上次输出不是有效JSON。请严格输出纯JSON数组，不要加任何解释文字、不要用Markdown代码块包裹。直接以 [ 开头，以 ] 结尾。"},
            ]
            result = call_llm(config, retry_msgs, temperature=0.7, max_tokens=10000, timeout=200,
                              top_p=0.9, frequency_penalty=0.3)
            log_debug("batch {} retry {} LLM returned {} chars".format(batch_num, _retry + 1, len(result) if isinstance(result, str) else str(type(result))))
            try:
                clips = _parse_json_response(result)
            except Exception as e:
                log_debug("batch {} retry {} parse error: {}".format(batch_num, _retry + 1, e))
                clips = None

        if not isinstance(clips, list) or len(clips) == 0:
            log_debug("batch {} FAILED after all retries (result: {})".format(
                batch_num, type(clips).__name__ if clips is not None else "None",
                len(clips) if isinstance(clips, list) else ""))
            raise RuntimeError("分镜脚本第 {} 批生成失败：LLM输出不是有效JSON数组或数组为空".format(batch_num))
        # 校验每个clip是dict且包含关键字段
        valid_clips = [c for c in clips if isinstance(c, dict) and "a_track" in c and "b_track" in c]
        if len(valid_clips) == 0:
            log_debug("batch {} clips parsed but none have a_track+b_track fields: {}".format(
                batch_num, [type(c).__name__ for c in clips[:3]]))
            raise RuntimeError("分镜脚本第 {} 批生成失败：返回的clip缺少必要字段".format(batch_num))
        if len(valid_clips) < len(clips):
            log_debug("batch {} filtered {}/{} valid clips".format(batch_num, len(valid_clips), len(clips)))
        clips = valid_clips
        # 每batch只生成1个clip，LLM可能返回多个 → 只取第一个
        if len(clips) > 1:
            log_debug("batch {} returned {} clips, keeping only first".format(batch_num, len(clips)))
            clips = clips[:1]
        # 三轨校验：确保 a_track(参考图) + c_track(尾帧) 都存在
        for c in clips:
            a = c.get("a_track", {})
            ct = c.get("c_track", {})
            # c_track 不存在时降级：从 a_track 创建
            if not ct:
                log_debug("batch {} clip missing c_track, creating from a_track".format(batch_num))
                ct = {
                    "tail_frame_prompt": a.get("tail_frame_prompt", a.get("image_prompt", "")),
                    "scene_description": a.get("scene_description", ""),
                    "camera": a.get("camera", ""),
                    "negative_prompt": a.get("negative_prompt", ""),
                }
                c["c_track"] = ct
            if not ct.get("tail_frame_prompt"):
                log_debug("batch {} clip c_track missing tail_frame_prompt, adding placeholder".format(batch_num))
                ct["tail_frame_prompt"] = a.get("reference_prompt", a.get("image_prompt", a.get("scene_description", "")))
            # a_track 不存在 reference_prompt 时降级：从 image_prompt 创建
            if not a.get("reference_prompt") and a.get("image_prompt"):
                log_debug("batch {} clip a_track has image_prompt instead of reference_prompt, migrating".format(batch_num))
                a["reference_prompt"] = a.pop("image_prompt")
        log_debug("batch {} parsed OK: {} clips".format(batch_num, len(clips)))

        # 将本batch的台词写入共享池（供后续clip参考）
        for c in clips:
            b = c.get("b_track", {})
            dlgs = b.get("dialogue", [])
            for d in dlgs:
                if isinstance(d, dict):
                    used_dialogues.append(f"  clip{batch_idx+1} - {d.get('character','?')}: \"{d.get('line','')}\"")

        elapsed = round(time.time() - t0, 1)
        print(f"[storyboard] batch {batch_num}/{total_batches} done, got {len(clips)} clips ({elapsed}s)")
        return batch_idx, clips

    # ── 串行执行，每个clip按顺序生成 ──
    log_debug("serial mode: {} batches, sequential execution".format(total_batches))
    all_clips = []
    previous_clip = None

    for batch_idx in range(total_batches):
        batch_num = batch_idx + 1
        clips = None
        
        # 3次重试
        for attempt in range(3):
            try:
                _, clips = _generate_one_batch(batch_idx, previous_clip=previous_clip)
                break
            except Exception as e:
                log_debug("clip {} attempt {}/3 failed: {}".format(batch_num, attempt + 1, e))
                if attempt < 2:
                    time.sleep(5 * (attempt + 1))
                else:
                    log_debug("clip {} all 3 attempts failed, using placeholder".format(batch_num))
                    clips = [_create_placeholder_clip(batch_idx, clip_duration)]
        
        all_clips.extend(clips)
        previous_clip = clips[-1]  # 更新前clip引用

    # 按顺序分配clip_id
    for idx, clip in enumerate(all_clips):
        clip["clip_id"] = idx + 1

    _inject_characters_in_scene(all_clips, characters)
    for clip in all_clips:
        clip["duration"] = clip_duration

    elapsed = round(time.time() - t0, 1)
    print(f"[storyboard] all batches done, total {len(all_clips)} clips in {elapsed}s")
    log_debug("all batches done, total {} clips in {}s".format(len(all_clips), elapsed))
    return all_clips


def modify_content(config, instruction, current_content, content_type, templates_dir, characters=None):
    """
    通用修改接口：用户告诉LLM修改内容
    instruction: 用户的修改指令
    current_content: 当前内容
    content_type: "outline" / "novel" / "storyboard" / "character"
    返回: 修改后的结构化数据
    """
    template = _load_template(templates_dir, "revision.txt")

    # === 智能分治：outline类型尝试只修改目标集 ===
    if content_type == "outline" and isinstance(current_content, dict):
        eps = current_content.get("episodes") or current_content.get("chapters") or []
        if len(eps) > 5:
            target_indices = _detect_target_episodes(instruction, len(eps))
            if target_indices:
                return _modify_outline_partial(
                    config, template, instruction, current_content,
                    target_indices, eps, templates_dir,
                )

    context = f"""
=== 内容类型 ===
{content_type}

=== 当前内容 ===
{json.dumps(current_content, ensure_ascii=False, indent=2) if isinstance(current_content, (dict, list)) else current_content}

=== 用户修改指令 ===
{instruction}
"""

    messages = [
        {"role": "system", "content": template},
        {"role": "user", "content": context},
    ]

    result = call_llm(config, messages, temperature=0.7, max_tokens=10000)
    if content_type in ("outline", "storyboard"):
        parsed = _parse_json_response(result)
        if content_type == "storyboard" and isinstance(parsed, list):
            _inject_characters_in_scene(parsed, characters)
        return parsed
    return result


def _detect_target_episodes(instruction, total_episodes):
    """
    从用户指令中检测目标集数。返回0-indexed列表，或None（无法定位）。
    支持："第30集" "最后一集" "第5集到第10集" "最后三集" "第1、2、3集"
    """
    import re as _re
    targets = set()

    # 匹配 "第N集"
    for m in _re.finditer(r'第\s*(\d+)\s*集', instruction):
        idx = int(m.group(1)) - 1
        if 0 <= idx < total_episodes:
            targets.add(idx)

    # 匹配 "最后一集"
    if _re.search(r'最后一集|最后1集', instruction):
        targets.add(total_episodes - 1)

    # 匹配 "最后N集"
    m = _re.search(r'最后\s*(\d+)\s*集', instruction)
    if m:
        n = int(m.group(1))
        for i in range(max(0, total_episodes - n), total_episodes):
            targets.add(i)

    # 匹配 "第N集到第M集"
    m = _re.search(r'第\s*(\d+)\s*集\s*到\s*第\s*(\d+)\s*集', instruction)
    if m:
        start, end = int(m.group(1)) - 1, int(m.group(2)) - 1
        for i in range(max(0, start), min(end + 1, total_episodes)):
            targets.add(i)

    return sorted(targets) if targets else None


def _modify_outline_partial(config, template, instruction, old_outline, target_indices, eps, templates_dir):
    """
    只把目标集（+前后各1集上下文）发给LLM，修改后回填到原outline。
    """
    # 取目标集+前后各1集作为上下文窗口
    window = set()
    for idx in target_indices:
        for di in range(-1, 2):
            ni = idx + di
            if 0 <= ni < len(eps):
                window.add(ni)
    window = sorted(window)

    # 构建子集
    eps_subset = [eps[i] for i in window]
    subset_map = {new_i: orig_i for new_i, orig_i in enumerate(window)}

    subset_json = json.dumps(eps_subset, ensure_ascii=False, indent=2)
    context = f"""
=== 内容类型 ===
outline（局部修改模式：只修改指定集数）

=== 说明 ===
以下是30集大纲中的第{','.join(str(i+1) for i in window)}集（共{len(window)}集）。
用户只想修改其中的第{','.join(str(i+1) for i in target_indices)}集。
请只返回修改后的这{len(window)}集数组，保持原JSON结构。
其他集数由系统保留，不需要返回。

=== 当前子集内容（JSON数组） ===
{subset_json}

=== 用户修改指令 ===
{instruction}
"""

    messages = [
        {"role": "system", "content": template},
        {"role": "user", "content": context},
    ]

    result = call_llm(config, messages, temperature=0.7, max_tokens=10000)
    parsed = _parse_json_response(result)

    # 校验返回的是list且长度合理
    if not isinstance(parsed, list) or len(parsed) == 0:
        raise ValueError(f"局部修改返回格式错误：期望数组，得到{type(parsed).__name__}")

    # 将修改结果回填到原outline
    new_eps = list(eps)  # 复制原集
    for new_i, ep_data in enumerate(parsed):
        orig_i = subset_map.get(new_i)
        if orig_i is not None and 0 <= orig_i < len(new_eps):
            new_eps[orig_i] = ep_data

    # 写回原outline的对应字段
    result_outline = dict(old_outline)
    if "episodes" in old_outline:
        result_outline["episodes"] = new_eps
    elif "chapters" in old_outline:
        result_outline["chapters"] = new_eps
    else:
        result_outline["episodes"] = new_eps

    return result_outline


def generate_subtitle(config, storyboards, templates_dir):
    """
    第9步：从B轨的Dialogue部分提取字幕
    storyboards: 所有集的分镜脚本
    返回: list[dict] 每条字幕 {start, end, text, character}
    """
    context = f"""
请从以下分镜脚本的对话部分提取字幕，按照时间轴排列。
每个片段的时长信息已标注。

分镜脚本：
{json.dumps(storyboards, ensure_ascii=False, indent=2)}

请输出一个JSON数组，每个元素包含：
- start: 字幕开始时间（秒）
- end: 字幕结束时间（秒）
- text: 字幕文字（中文台词）
- character: 说话角色名字

只输出JSON数组，不要其他文字。
"""

    messages = [{"role": "user", "content": context}]
    result = call_llm(config, messages, temperature=0.3, max_tokens=8192)
    return _parse_json_response(result)


# ── 内部工具函数 ──


def _load_template(templates_dir, filename):
    """加载提示词模板"""
    import os

    path = os.path.join(templates_dir, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _parse_json_response(text):
    """从LLM输出中提取JSON，增强容错。剥离Markdown代码块标记。"""
    import re as _re
    text = text.strip()
    # 剥离推理模型的<think>标签
    text = _re.sub(r'<think>.*?</think>', '', text, flags=_re.DOTALL).strip()
    # 剥离Markdown JSON代码块包裹
    text = _re.sub(r'^```(?:json)?\s*\n?|\s*```$', '', text, flags=_re.MULTILINE).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试找到JSON对象或数组
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start_idx = text.find(open_ch)
        if start_idx == -1:
            continue
        # 从后往前找配对的闭合括号
        for j in range(len(text) - 1, start_idx, -1):
            if text[j] == close_ch:
                try:
                    return json.loads(text[start_idx:j + 1])
                except json.JSONDecodeError:
                    continue

    # 最后尝试：截断JSON修复（补闭合括号）
    # 如果存在 _EOF 标记但JSON不完整，说明发生了截断——不再静默补全
    has_eof_hint = '_EOF' in text
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start_idx = text.find(open_ch)
        if start_idx == -1:
            continue
        partial = text[start_idx:]
        for suffix in ['', '}', ']}', '"}]', '"]}', '"}', '"}}', '"}]}', ']}}']:
            try:
                parsed = json.loads(partial + suffix)
                # 空数组/空dict视为无效，跳过（LLM返回空结构时不应通过）
                if isinstance(parsed, list) and len(parsed) == 0:
                    continue
                if isinstance(parsed, dict) and len(parsed) == 0:
                    continue
                # 如果模板要求 _EOF 但解析结果没有，标记为截断
                if has_eof_hint and isinstance(parsed, dict) and '_EOF' not in parsed:
                    parsed['_truncated'] = True
                return parsed
            except json.JSONDecodeError:
                continue

    # 所有解析尝试失败，记录原始输出并返回None让调用方降级处理
    print(f"[LLM] JSON解析失败，原始输出:\n{text[:2000]}", flush=True)
    try:
        import sys, os
        exe_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(exe_dir, 'llm_debug.log')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"[LLM] JSON解析失败，原始输出:\n{text}\n")
    except:
        pass
    return None
