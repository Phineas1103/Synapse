# -*- coding: utf-8 -*-
"""Synapse — FastAPI 后端（核心 API）"""

import os
import sys
import json
import time
import asyncio
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# 确保模块路径
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Frozen app: JSON data files (style_presets etc.) are in _internal/ alongside the modules
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.join(os.path.dirname(sys.executable), '_internal')
else:
    DATA_DIR = APP_DIR
import config
import llm_engine
import image_engine
import video_engine
import ffmpeg_utils
import project_manager
from task_queue import TaskQueue

# ── 全局任务队列 ──
image_queue = None
video_queue = None

# --- 异步视频提交任务追踪 ---
_submit_jobs = {}  # {job_id: {total, submitted, failed, done, results, error_list}}

# --- 异步分镜图生成任务追踪 ---
_frame_gen_jobs = {}  # {job_id: {status, total, completed, failed, in_progress, results, errors, project_id}}


def create_app():
    app = FastAPI(title="Synapse")

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"success": False, "message": str(exc)})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:18090", "http://localhost:18090"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = os.path.join(APP_DIR, "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # ════════════════════════════════════════
    #  配置 API
    # ════════════════════════════════════════

    @app.get("/api/config")
    async def api_get_config():
        cfg = config.load_config()
        # 隐藏 API Key：只返回掩码，不暴露原始 key
        for section in ("llm", "image", "video"):
            key = cfg[section].get("api_key", "")
            if key and len(key) > 8:
                cfg[section]["api_key_masked"] = key[:4] + "****" + key[-4:]
            elif key:
                cfg[section]["api_key_masked"] = "****"
            else:
                cfg[section]["api_key_masked"] = ""
            del cfg[section]["api_key"]
        return cfg

    @app.post("/api/config")
    async def api_save_config(request: Request):
        data = await request.json()
        cfg = config.load_config()
        for section in ("llm", "image", "video"):
            if section in data:
                new_cfg = data[section]
                # api_key: __UNCHANGED__ = user didn't touch it; empty/masked also preserve
                new_key = new_cfg.get("api_key", "")
                if new_key == "__UNCHANGED__" or "****" in new_key or not new_key:
                    new_cfg["api_key"] = cfg[section]["api_key"]
                # Skip empty fields to avoid overwriting with blank
                for field in ("provider", "base_url", "model", "endpoint_type", "custom_endpoint"):
                    if not new_cfg.get(field, "").strip():
                        new_cfg[field] = cfg[section].get(field, "")
                cfg[section].update(new_cfg)
        config.save_config(cfg)
        return {"success": True}

    @app.get("/api/config/presets")
    async def api_get_presets():
        return config.get_presets()

    @app.post("/api/config/test")
    async def api_test_config(request: Request):
        data = await request.json()
        return config.test_api_connection(
            data["type"], data["base_url"], data["api_key"], data["model"]
        )

    # ════════════════════════════════════════
    #  画风 API
    # ════════════════════════════════════════

    def _load_json(filename, default=None):
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default if default is not None else []

    def _save_json(filename, data):
        path = os.path.join(DATA_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @app.get("/api/styles")
    async def api_get_styles():
        presets = _load_json("style_presets.json", [])
        custom = _load_json("custom_styles.json", [])
        return {"presets": presets, "custom": custom}

    @app.post("/api/styles")
    async def api_save_style(request: Request):
        data = await request.json()
        custom = _load_json("custom_styles.json", [])
        # 如果已存在同id则覆盖，否则追加
        existing = [s for s in custom if s.get("id") == data.get("id")]
        if existing:
            custom = [s if s.get("id") != data.get("id") else data for s in custom]
        else:
            custom.append(data)
        _save_json("custom_styles.json", custom)
        return {"success": True, "count": len(custom)}

    @app.delete("/api/styles/{style_id}")
    async def api_delete_style(style_id: str):
        custom = _load_json("custom_styles.json", [])
        custom = [s for s in custom if s.get("id") != style_id]
        _save_json("custom_styles.json", custom)
        return {"success": True}

    @app.get("/api/styles/modifiers")
    async def api_get_style_modifiers():
        return _load_json("style_modifiers.json", {})

    @app.post("/api/styles/ai-generate")
    async def api_ai_generate_style(request: Request):
        data = await request.json()
        description = data.get("description", "")
        cfg = config.load_config()
        prompt = (
            "# Role\n"
            "你是一个顶级的 AI 图像生成 Prompt 架构师与画风翻译专家。你的任务是将用户口语化的画风描述，精准转化为一套高度结构化、无渲染污染、且严格符合下游漫剧生成管线规范的自定义画风 JSON 配置。\n\n"
            "# Execution Core (执行核心)\n"
            "当你接收到用户的画风描述后，必须严格按照以下四个步骤进行增量式推理，并最终输出符合格式要求的 JSON。\n\n"
            "### 第一步：画风渲染路线判定 (Rendering Route Classification)\n"
            "首先，你必须根据用户的描述，将画风绝对划分为以下三类之一（有且仅有这三类，严禁自造标签）：\n"
            "1. **Realistic Photography** (真人摄影/电影胶片/写实级质感)\n"
            "2. **2D Anime Style** (传统二次元/二次元水墨/赛璐珞卡通/漫画线稿)\n"
            "3. **Semi-Realistic Art** (半写实CG/手绘插画/厚涂艺术/概念设计)\n\n"
            "### 第二步：关键词红线约束 (Whitelist & Blacklist Rules)\n"
            "根据你判定的分类路线，在构建英文 prompt 字段时，必须严格遵守以下红线，严禁混用！\n\n"
            "- **路线 A：若属于 [Realistic Photography]**\n"
            "  * 【必须包含的白名单词汇】: 至少从以下词汇中选用 3-5 个融入 prompt 以强化真实感：film grain, photographic bokeh, skin pores, fabric weave, anamorphic lens, studio color grading, natural skin imperfections, true-to-life, DSLR, 35mm lens, shallow depth-of-field。\n"
            "  * 【绝对禁用的黑名单词汇】: 严禁出现 cel-shading, stylized, illustrated, vector, anime, comic, drawing 及其任何同义词。\n\n"
            "- **路线 B：若属于 [2D Anime Style]**\n"
            "  * 【必须包含的白名单词汇】: 至少从以下词汇中选用 3-5 个融入 prompt 以强化线条与平涂感：cel-shading, ink lines, flat coloring, bold outlines, vector lines, screen-tone, clean linework, vibrant saturated palette。\n"
            "  * 【绝对禁用的黑名单词汇】: 严禁出现 photographic, realistic, film grain, DSLR, 35mm, photography, ray-tracing 及其任何同义词。\n\n"
            "- **路线 C：若属于 [Semi-Realistic Art]**\n"
            "  * 【必须包含的白名单词汇】: 至少从以下词汇中选用 3-5 个融入 prompt 以强化艺术化渲染：soft gradients, painterly textures, mixed media, fine-line brushwork, watercolor washes, textured canvas, semi-abstract。\n"
            "  * 【平衡规则】: 可以包含比例均衡的写实骨骼比例(realistic proportions)描述，但绝不能带有摄影器械词汇(DSLR/35mm)或纯二次元描边词汇(cel-shading)。\n\n"
            "### 第三步：视觉描述字段（prompt）深度去环境污染与格式控制\n"
            "prompt 字段必须是一段纯粹的、无具体宏观物体的、长度在 50-80 词之间的英文扁平段落，且必须遵循以下铁律：\n"
            "1. **分类标签强制前置**：必须以 [Rendering Style: 你的分类路线] 开头。例如：[Rendering Style: 2D Anime Style] Traditional abstract ink wash...\n"
            "2. **严禁包含任何环境/实体污染源**：只允许描写渲染技术、画面质感、介质特征、色彩科学与光影媒介。绝对禁止出现任何人物(character, girl, man)、场景建筑(buildings, streets, trees, mountains)、特定物件或具体情节内容。\n"
            "3. **严禁使用图片描述句式**：这个 prompt 描述的是渲染技术本身（滤镜/材质底膜），不是在描述任何具体图片的画面内容。绝对禁止使用\u2018画面中有……\u2019、\u2018呈现出……\u2019、\u2018a picture showing...\u2019、\u2018depicting a scene with...\u2019等描述图片的句式或其英文等价词。\n"
            "4. **单色画风联动约束**：如果第四步判定色调（tone）为 monochrome，英文 prompt 内部必须强行包含具体的黑白/单色渲染词汇（如 grayscale palette, desaturated, silver gelatin print, monochrome tonal range 等），绝对不能只靠 tone 字段声明而 prompt 内部毫无体现。\n"
            "5. **格式要求**：必须是一段连贯的英文学术级图像学文本，不要写成逗号分隔的关键词列表。\n\n"
            "### 第四步：其他字段提取规范\n"
            "- id：英文小写下划线组合，3-16个字符，作为程序内部唯一标识。\n"
            "- name：中文画风名称，2-4个汉字。\n"
            "- name_en：英文画风名称，词首大写。\n"
            "- tone：色彩倾向。必须且只能从以下 4 个中选择一个：cool / warm / neutral / monochrome（如果用户提到黑白老电影、单色调水墨，必须选 monochrome，并激活第三步的单色联动规则）。\n"
            "- lighting：光影倾向。必须且只能从以下 6 个中选择一个：natural / neon / dramatic / cinematic / moonlight / soft（若属于日漫柔光、柔和光晕，务必选择 soft）。\n\n"
            "# Output Format (JSON 约束)\n"
            "不要输出任何解释性文本、前言或 Markdown 包裹块。只输出一个合法、紧凑、可被 json.loads() 直接解析的 JSON 字符串，格式如下：\n\n"
            "请严格输出JSON格式，不要输出其他内容：\n"
            '{{"id":"xxx","name":"xxx","name_en":"xxx","prompt":"[Rendering Style: xxx] ...","tone":"xxx","lighting":"xxx"}}'
        )
        # 注入用户原始描述
        prompt += "\n\n# USER INTENT: " + description + "\nGenerate a style that matches THIS specific description. Replace all example values above with values derived from the user's actual description."
        user_msg = f"用户描述：{description}\n\n请根据上述用户描述，生成对应的画风JSON配置。"
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg}
        ]
        result = llm_engine.call_llm(cfg["llm"], messages, max_tokens=4096)
        # 尝试解析JSON
        import re
        match = re.search(r'\{[^{}]+\}', result)
        if match:
            style_data = json.loads(match.group())
            return {"success": True, "style": style_data}
        return {"success": False, "error": "AI生成失败，请重试", "raw": result}

    # ════════════════════════════════════════
    #  项目 API
    # ════════════════════════════════════════

    @app.get("/api/projects")
    async def api_list_projects():
        return project_manager.list_projects()

    @app.post("/api/projects")
    async def api_create_project(request: Request):
        data = await request.json()
        settings = {
            "clip_duration": data.get("clip_duration", 10),
            "art_style": data.get("art_style", ""),
            "art_style_display": data.get("art_style_display", ""),
            "style_tone": data.get("style_tone", ""),
            "style_lighting": data.get("style_lighting", ""),
            "style_texture": data.get("style_texture", ""),
            "genre": data.get("genre", []),
            "episodes": data.get("episodes", 10),
            "episode_duration": data.get("episode_duration", 2),
        }
        project_id = project_manager.create_project(data["name"], settings)
        return {"success": True, "project_id": project_id}

    @app.get("/api/projects/{project_id}")
    async def api_get_project(project_id: str):
        try:
            project = project_manager.load_project(project_id)
            # 修复 frames 中的 image_url / tail_frame_url，
            # 确保前端直接使用 f.image_url 时指向正确的后端路径
            frames_data = project.get("frames")
            if frames_data and isinstance(frames_data, dict):
                for ch_str, ch_data in frames_data.items():
                    if not isinstance(ch_data, dict):
                        continue
                    flist = ch_data.get("frames", [])
                    if not isinstance(flist, list):
                        continue
                    for f in flist:
                        clip_idx = f.get("clip_index")
                        if clip_idx is not None:
                            if f.get("status") == "completed" and f.get("image_path"):
                                f["image_url"] = f"/api/projects/{project_id}/frames/{ch_str}/{clip_idx}/image"
                            if f.get("status") == "completed" and f.get("tail_frame_path"):
                                f["tail_frame_url"] = f"/api/projects/{project_id}/frames/{ch_str}/{clip_idx}/tail"
            return project
        except FileNotFoundError:
            raise HTTPException(404, "项目不存在")

    @app.post("/api/projects/{project_id}/save")
    async def api_save_project(project_id: str, request: Request):
        data = await request.json()
        project_manager.save_project(project_id, data)
        return {"success": True}

    @app.delete("/api/projects/{project_id}")
    async def api_delete_project(project_id: str):
        project_manager.delete_project(project_id)
        return {"success": True}


    @app.get("/api/projects/{project_id}/chat")
    async def api_get_chat_history(project_id: str):
        """获取项目的对话历史"""
        project = project_manager.load_project(project_id)
        return {"success": True, "chat_history": project.get("chat_history", [])}

    @app.post("/api/projects/{project_id}/chat")
    async def api_save_chat_message(project_id: str, request: Request):
        """追加对话消息并持久化（含200K token截断）"""
        data = await request.json()
        project = project_manager.load_project(project_id)

        chat = project.get("chat_history", [])
        messages = data.get("messages", [])
        chat.extend(messages)

        # 保留最近150次交互（300条消息）
        MAX_MESSAGES = 300
        if len(chat) > MAX_MESSAGES:
            chat = chat[-MAX_MESSAGES:]

        project["chat_history"] = chat
        project_manager.save_project(project_id, project)
        return {"success": True, "count": len(chat)}

    # ════════════════════════════════════════
    #  第2步：智能大纲（起名 + 大纲生成）
    # ════════════════════════════════════════

    @app.post("/api/projects/{project_id}/titles")
    def api_generate_titles(project_id: str):
        """根据创意生成3-5个推荐标题"""
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        settings = project.get("settings", {})

        if not settings.get("idea", "").strip():
            return JSONResponse(status_code=400, content={"success": False, "message": "请先输入创意"})

        try:
            result = llm_engine.generate_titles(cfg["llm"], settings, config.TEMPLATES_DIR)
            titles_raw = result.get("titles", [])
            slogans_raw = result.get("slogans", [])
            # 把平行数组合并成对象数组: [{title, reason}]
            merged = []
            for idx, t in enumerate(titles_raw):
                merged.append({"title": t, "reason": slogans_raw[idx] if idx < len(slogans_raw) else ""})
            return {"success": True, "titles": merged}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/outline")
    async def api_generate_outline(project_id: str, request: Request):
        """生成完整分集大纲（可选传入selected_title）"""
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        # 用户选择的标题（可选）
        selected_title = data.get("title", "")
        if selected_title:
            project["title"] = selected_title

        try:
            outline = llm_engine.generate_outline(cfg["llm"], project, config.TEMPLATES_DIR)
            project["outline"] = outline
            project_manager.save_project(project_id, project)
            return {"success": True, "outline": outline}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/outline/stream")
    async def api_generate_outline_stream(project_id: str, request: Request):
        """流式生成大纲（SSE）- 分批生成抗截断 + 真实保活流"""
        from fastapi.responses import StreamingResponse
        import json as _json
        import copy

        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        selected_title = data.get("title", "")
        if selected_title:
            project["title"] = selected_title

        def event_stream():
            try:
                total_episodes = int(project.get("settings", {}).get("episodes", 10))
                batch_size = 10
                merged_episodes = []
                final_outline = None

                for start_idx in range(0, total_episodes, batch_size):
                    end_idx = min(start_idx + batch_size, total_episodes)
                    current_count = end_idx - start_idx

                    batch_project = copy.deepcopy(project)
                    batch_project["settings"]["episodes"] = current_count

                    if merged_episodes:
                        last_ep = merged_episodes[-1]
                        cliff = last_ep.get("cliffhanger", last_ep.get("hook", "无"))
                        prev_context = (
                            "\n\n【前情提要】前" + str(start_idx) + "集已生成。"
                            "第" + str(start_idx) + "集结尾悬念是：" + str(cliff) + "。"
                            "请紧接其后，从第" + str(start_idx + 1) + "集继续创作。"
                            "注意：本次只需要生成" + str(current_count) + "集！"
                        )
                        batch_project["settings"]["idea"] = (
                            str(batch_project["settings"].get("idea", "")) + prev_context
                        )

                    batch_success = False
                    for attempt in range(2):
                        if attempt > 0:
                            msg = "[系统] 检测到截断，正在重试第 " + str(start_idx + 1) + "-" + str(end_idx) + " 集..."
                        else:
                            msg = "[系统] 正在创作第 " + str(start_idx + 1) + "-" + str(end_idx) + " 集大纲..."
                        chunk_data = _json.dumps({"type": "chunk", "content": msg}, ensure_ascii=False)
                        yield "data: " + chunk_data + "\n\n"

                        batch_outline = None
                        try:
                            for event in llm_engine.generate_outline_stream(
                                cfg["llm"], batch_project, config.TEMPLATES_DIR
                            ):
                                if event["type"] == "chunk":
                                    yield "data: " + _json.dumps(event, ensure_ascii=False) + "\n\n"
                                elif event["type"] == "done":
                                    batch_outline = event.get("outline")
                        except Exception as e:
                            print(f"[OUTLINE_BATCH] Batch {start_idx+1}-{end_idx} attempt {attempt+1} error: {e}")
                            continue

                        if batch_outline:
                            eps = batch_outline.get("chapters") or batch_outline.get("episodes") or []
                            is_truncated = batch_outline.get("_truncated", False)

                            if len(eps) >= current_count and not is_truncated:
                                for i, ep in enumerate(eps[:current_count]):
                                    ep["episode"] = start_idx + i + 1
                                merged_episodes.extend(eps[:current_count])

                                if not final_outline:
                                    final_outline = batch_outline
                                batch_success = True
                                break

                    if not batch_success:
                        raise Exception(
                            "生成第 " + str(start_idx + 1) + "-" + str(end_idx) + " 集连续失败，模型输出不稳定，请稍后再试。"
                        )

                if final_outline:
                    if "episodes" in final_outline:
                        final_outline["episodes"] = merged_episodes
                    else:
                        final_outline["chapters"] = merged_episodes

                    project["outline"] = final_outline
                    project_manager.save_project(project_id, project)
                    done_data = _json.dumps({"type": "done", "outline": final_outline}, ensure_ascii=False)
                    yield "data: " + done_data + "\n\n"

            except Exception as e:
                err_data = _json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
                yield "data: " + err_data + "\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/projects/{project_id}/outline/modify")
    async def api_modify_outline(project_id: str, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        try:
            old_outline = project["outline"]
            result = llm_engine.modify_content(
                cfg["llm"], data["instruction"], old_outline,
                "outline", config.TEMPLATES_DIR,
            )

            # === 三层防御：校验LLM返回的outline ===
            # 1) 必须是dict且包含episodes或chapters
            if not isinstance(result, dict):
                return JSONResponse(status_code=500, content={
                    "success": False,
                    "message": "AI返回的数据格式错误（非对象），大纲未改变。请换个方式描述修改要求。"
                })

            new_eps = result.get("episodes") or result.get("chapters")
            if not isinstance(new_eps, list) or len(new_eps) == 0:
                return JSONResponse(status_code=500, content={
                    "success": False,
                    "message": "AI返回的大纲缺少集数数据，大纲未改变。请换个方式描述修改要求。"
                })

            # 2) 集数不能少于原来的2/3（防止LLM偷懒）
            old_eps = old_outline.get("episodes") or old_outline.get("chapters") or []
            if len(old_eps) > 0 and len(new_eps) < len(old_eps) * 2 // 3:
                return JSONResponse(status_code=500, content={
                    "success": False,
                    "message": f"AI只返回了{len(new_eps)}集（原{len(old_eps)}集），数据不完整，大纲未改变。建议指定具体集数修改。"
                })

            # 3) 校验通过，保存
            project["outline"] = result
            project_manager.save_project(project_id, project)
            return {"success": True, "outline": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    # ── 上传小说解析 ──
    @app.post("/api/projects/{project_id}/parse-novel")
    async def api_parse_novel(project_id: str, request: Request):
        """解析用户上传的小说，提取标题、大纲、角色"""
        try:
            data = await request.json()
            novel_text = data.get("novel_text", "").strip()
            if not novel_text:
                return JSONResponse(status_code=400, content={"success": False, "message": "未收到小说文本"})

            project = project_manager.load_project(project_id)
            cfg = config.load_config()

            episodes = int(project.get("settings", {}).get("episodes", 10))
            episode_duration = int(project.get("settings", {}).get("episode_duration", 60))

            result = llm_engine.parse_novel(
                cfg["llm"], novel_text, episodes, episode_duration, config.TEMPLATES_DIR
            )

            # 如果检测到用户标注的分集，自动更新项目集数设置
            actual_chapters = len(result.get("outline", {}).get("chapters", []))
            if actual_chapters > 0 and actual_chapters != episodes:
                print(f"[PARSE_NOVEL] 自动更新集数: {episodes} → {actual_chapters}（用户标注）")
                project["settings"]["episodes"] = actual_chapters

            # 保存原始小说到项目（用于后续按段落切割）
            project["_uploaded_novel"] = novel_text
            project["_novel_paragraphs"] = [p for p in novel_text.split("\n\n") if p.strip()]
            project_manager.save_project(project_id, project)

            return {"success": True, **result}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    # ── 用户选择标题后，切割小说并存储到各集 ──
    @app.post("/api/projects/{project_id}/split-novel")
    async def api_split_novel(project_id: str, request: Request):
        """用户选择标题后，按段落索引切割小说到各集"""
        try:
            data = await request.json()
            selected_title = data.get("title", "")
            outline = data.get("outline", {})

            project = project_manager.load_project(project_id)
            paragraphs = project.get("_novel_paragraphs", [])
            if not paragraphs:
                # 降级：从 _uploaded_novel 重新生成段落列表
                uploaded = project.get("_uploaded_novel", "")
                if not uploaded:
                    return JSONResponse(status_code=400, content={"success": False, "message": "未找到上传的小说文本"})
                paragraphs = [p for p in uploaded.split("\n\n") if p.strip()]
                project["_novel_paragraphs"] = paragraphs
                project_manager.save_project(project_id, project)

            # 保存标题和大纲
            if selected_title:
                project["title"] = selected_title
            project["outline"] = outline
            project["settings"]["novel_source"] = "uploaded"

            # 按段落索引切割
            chapters = outline.get("chapters", [])
            for i, ch in enumerate(chapters):
                start = ch.get("start_paragraph", 0)
                end = ch.get("end_paragraph", len(paragraphs) - 1)
                # 安全边界
                start = max(0, min(start, len(paragraphs) - 1))
                end = max(start, min(end, len(paragraphs) - 1))
                chapter_text = "\n\n".join(paragraphs[start:end + 1])

                project.setdefault("chapters", {})[str(i)] = {
                    "title": ch.get("title", f"第{i+1}集"),
                    "summary": ch.get("summary", ""),
                    "novel_text": chapter_text,
                    "confirmed": False,
                    "summary_text": chapter_text[:200],
                }

            # 清理临时数据
            project.pop("_uploaded_novel", None)
            project.pop("_novel_paragraphs", None)

            project_manager.save_project(project_id, project)
            return {"success": True, "chapters_count": len(chapters)}

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    # ════════════════════════════════════════
    #  第4步：角色定妆（并发版）
    # ════════════════════════════════════════

    def _worker_generate_character(char, project_id, art_style, cfg):
        """单角色并发工作线程：LLM生成prompt → 图片生成 → 保存"""
        char_name = char.get("name", "未命名")
        try:
            # 1. LLM生成角色prompt
            prompt = llm_engine.generate_character_prompt(
                cfg["llm"], char, art_style, config.TEMPLATES_DIR
            )
            # 2. 图片生成（内部处理异步轮询）
            image_data = image_engine.generate_image(
                cfg["image"], prompt, resolution="2K"
            )
            # 3. 保存
            image_path = project_manager.save_character_image(
                project_id, char_name, image_data
            )
            return {
                "name": char_name, "prompt": prompt,
                "image_path": image_path, "confirmed": False,
            }
        except Exception as e:
            return {
                "name": char_name, "prompt": "", "image_path": "",
                "error": str(e), "confirmed": False,
            }

    @app.post("/api/projects/{project_id}/characters/generate")
    def api_generate_characters(project_id: str):
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        outline = project["outline"]
        characters = outline.get("characters", [])
        art_style = llm_engine.resolve_style_prompt(
            project["settings"].get("art_style", ""), DATA_DIR
        )

        total = len(characters)
        max_workers = min(total, 200) or 1

        def sse_generator():
            """SSE流：每完成一个角色推送进度，最后推送完整结果"""
            results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_char = {
                    executor.submit(
                        _worker_generate_character,
                        char, project_id, art_style, cfg
                    ): char
                    for char in characters
                }
                for future in as_completed(future_to_char):
                    result = future.result()
                    results.append(result)
                    completed = len(results)
                    # SSE: 每完成一个角色推送进度
                    event_data = json.dumps({
                        "type": "progress",
                        "completed": completed,
                        "total": total,
                        "character": result,
                    }, ensure_ascii=False)
                    yield f"data: {event_data}\n\n"

            # 保存项目
            project["characters"] = results
            project_manager.save_project(project_id, project)

            # SSE: 最终完成事件
            final_data = json.dumps({
                "type": "complete",
                "characters": results,
            }, ensure_ascii=False)
            yield f"data: {final_data}\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/projects/{project_id}/characters/{char_name}/regenerate")
    async def api_regenerate_character(project_id: str, char_name: str, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        art_style = llm_engine.resolve_style_prompt(
            project["settings"].get("art_style", ""), DATA_DIR
        )

        # 如果有修改指令，先修改提示词
        char_info = None
        for char in project["outline"].get("characters", []):
            if char["name"] == char_name:
                char_info = char
                break

        if not char_info:
            raise HTTPException(404, "角色不存在")

        instruction = data.get("instruction", "")
        if instruction:
            current_prompt = ""
            for c in project["characters"]:
                if c["name"] == char_name:
                    current_prompt = c.get("prompt", "")
                    break
            new_prompt = llm_engine.modify_content(
                cfg["llm"], instruction, current_prompt, "character_prompt", config.TEMPLATES_DIR
            )
        else:
            new_prompt = llm_engine.generate_character_prompt(
                cfg["llm"], char_info, art_style, config.TEMPLATES_DIR
            )

        try:
            image_data = image_engine.generate_image(cfg["image"], new_prompt, resolution="2K")
            image_path = project_manager.save_character_image(project_id, char_name, image_data)

            for c in project["characters"]:
                if c["name"] == char_name:
                    c["prompt"] = new_prompt
                    c["image_path"] = image_path
                    c["confirmed"] = False
                    break

            project_manager.save_project(project_id, project)
            return {"success": True, "prompt": new_prompt, "image_path": image_path}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/characters/confirm")
    async def api_confirm_characters(project_id: str, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        project["characters"] = data.get("characters", project["characters"])
        project_manager.save_project(project_id, project)
        return {"success": True}

    @app.post("/api/projects/{project_id}/characters/{char_name}/retry")
    def api_retry_character(project_id: str, char_name: str):
        """重试单个角色的定妆照生成"""
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        outline = project.get("outline", {})
        characters = outline.get("characters", [])
        art_style = llm_engine.resolve_style_prompt(
            project["settings"].get("art_style", ""), DATA_DIR
        )
        # 找到对应角色
        target_char = None
        for c in characters:
            if c.get("name") == char_name:
                target_char = c
                break
        if not target_char:
            return JSONResponse(status_code=404, content={"success": False, "message": f"角色 {char_name} 未找到"})
        try:
            result = _worker_generate_character(target_char, project_id, art_style, cfg)
            if result.get("error"):
                return JSONResponse(status_code=500, content={"success": False, "message": result["error"]})
            # 更新项目中的角色数据
            for c in project["characters"]:
                if c.get("name") == char_name:
                    c["prompt"] = result["prompt"]
                    c["image_path"] = result["image_path"]
                    c["confirmed"] = False
                    if "error" in c:
                        del c["error"]
                    break
            project_manager.save_project(project_id, project)
            return {"success": True, "prompt": result["prompt"], "image_path": result["image_path"]}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/characters/{char_name}/upload")
    async def api_upload_character_image(project_id: str, char_name: str, request: Request):
        """上传角色定妆照（替代AI生成的图片）"""
        try:
            project = project_manager.load_project(project_id)
            form = await request.form()
            image_file = form.get("image")
            if not image_file:
                return JSONResponse(status_code=400, content={"success": False, "message": "未收到图片文件"})

            # Read file bytes
            image_bytes = await image_file.read()
            if not image_bytes:
                return JSONResponse(status_code=400, content={"success": False, "message": "图片文件为空"})

            # Save image
            ext = ".png"
            if image_file.filename:
                if image_file.filename.lower().endswith(".jpg") or image_file.filename.lower().endswith(".jpeg"):
                    ext = ".jpg"
            img_dir = os.path.join(config.PROJECTS_DIR, project_id, "characters")
            os.makedirs(img_dir, exist_ok=True)
            save_path = os.path.join(img_dir, f"{project_manager._safe_filename(char_name)}{ext}")
            with open(save_path, "wb") as f:
                f.write(image_bytes)

            # Update character record
            for c in project.get("characters", []):
                if c["name"] == char_name:
                    c["image_path"] = save_path
                    break

            project_manager.save_project(project_id, project)
            return {"success": True, "image_path": save_path}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": f"上传失败: {str(e)}"})

    # ════════════════════════════════════════
    #  第5步：生成小说
    # ════════════════════════════════════════

    @app.post("/api/projects/{project_id}/novel/{chapter_index}")
    def api_generate_novel(project_id: str, chapter_index: int):
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        # 收集前几集的摘要
        summaries = []
        for i in range(chapter_index):
            ch = project["chapters"].get(str(i), {})
            if ch.get("summary_text"):
                summaries.append(f"第{i+1}集 {ch.get('title', '')}：{ch['summary_text'][:200]}")
        previous = "\n".join(summaries) if summaries else ""

        try:
            _ep_dur = int(project.get("settings", {}).get("episode_duration", 120))
            novel_text = llm_engine.generate_novel_chapter(
                cfg["llm"], project["outline"], chapter_index,
                previous, config.TEMPLATES_DIR, episode_duration=_ep_dur,
            )
            outline_chapters = project["outline"].get("chapters") or project["outline"].get("episodes") or []
            chapter_info = outline_chapters[chapter_index]
            project["chapters"][str(chapter_index)] = {
                "title": chapter_info["title"],
                "summary": chapter_info["summary"],
                "novel_text": novel_text,
                "confirmed": False,
                "summary_text": novel_text[:200],
            }
            project_manager.save_project(project_id, project)
            return {"success": True, "novel_text": novel_text, "chapter": project["chapters"][str(chapter_index)]}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.get("/api/projects/{project_id}/novel/{chapter_index}/stream")
    def api_generate_novel_stream(project_id: str, chapter_index: int):
        """流式生成单集小说（SSE）"""
        from fastapi.responses import StreamingResponse
        import json as _json

        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        # 如果已有小说文本（用户上传模式），直接返回，不调LLM
        existing = project.get("chapters", {}).get(str(chapter_index), {})
        if existing.get("novel_text"):
            def skip_stream():
                done_data = _json.dumps({"type": "done", "novel_text": existing["novel_text"]}, ensure_ascii=False)
                yield "data: " + done_data + "\n\n"
            return StreamingResponse(skip_stream(), media_type="text/event-stream",
                                     headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        summaries = []
        for i in range(chapter_index):
            ch = project["chapters"].get(str(i), {})
            if ch.get("summary_text"):
                summaries.append(f"第{i+1}集 {ch.get('title', '')}：{ch['summary_text'][:200]}")
        previous = "\n".join(summaries) if summaries else ""

        _ep_dur = int(project.get("settings", {}).get("episode_duration", 120))

        def event_stream():
            full_novel = ""
            had_error = False
            try:
                for event in llm_engine.generate_novel_chapter_stream(
                    cfg["llm"], project["outline"], chapter_index,
                    previous, config.TEMPLATES_DIR, episode_duration=_ep_dur,
                ):
                    if event["type"] == "chunk":
                        yield "data: " + _json.dumps(event, ensure_ascii=False) + "\n\n"
                    elif event["type"] == "done":
                        full_novel = event["novel_text"]
                    elif event["type"] == "error":
                        # Generator yielded an error after retries exhausted
                        had_error = True
                        yield "data: " + _json.dumps(event, ensure_ascii=False) + "\n\n"
                        return

                if not had_error and full_novel:
                    outline_chapters = project["outline"].get("chapters") or project["outline"].get("episodes") or []
                    chapter_info = outline_chapters[chapter_index]
                    project["chapters"][str(chapter_index)] = {
                        "title": chapter_info["title"],
                        "summary": chapter_info["summary"],
                        "novel_text": full_novel,
                        "confirmed": False,
                        "summary_text": full_novel[:200],
                    }
                    project_manager.save_project(project_id, project)

                    done_data = _json.dumps({"type": "done", "novel_text": full_novel}, ensure_ascii=False)
                    yield "data: " + done_data + "\n\n"

            except Exception as e:
                err_data = _json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
                yield "data: " + err_data + "\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/projects/{project_id}/novel/batch")
    async def api_generate_novel_batch(project_id: str, request: Request):
        """批量生成所有集小说（并发LLM调用）"""
        try:
            data = await request.json()
            chapter_indices = data.get("chapters", [])
            if not chapter_indices:
                return JSONResponse(status_code=400, content={"success": False, "message": "未指定章节"})

            project = project_manager.load_project(project_id)
            cfg = config.load_config()
            outline_chapters = project["outline"].get("chapters") or project["outline"].get("episodes") or []

            def _batch_work():
                import concurrent.futures
                _ep_dur = int(project.get("settings", {}).get("episode_duration", 120))
                def _gen_one(idx):
                    try:
                        novel_text = llm_engine.generate_novel_chapter(
                            cfg["llm"], project["outline"], idx,
                            "", config.TEMPLATES_DIR, episode_duration=_ep_dur,
                        )
                        chapter_info = outline_chapters[idx]
                        return idx, {
                            "title": chapter_info["title"],
                            "summary": chapter_info["summary"],
                            "novel_text": novel_text,
                            "confirmed": False,
                            "summary_text": novel_text[:200],
                        }, None
                    except Exception as e:
                        return idx, None, str(e)

                results = {}
                errors = {}
                max_workers = min(3, len(chapter_indices))

                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(_gen_one, idx): idx for idx in chapter_indices}
                    for future in concurrent.futures.as_completed(futures):
                        idx, chapter_data, error = future.result()
                        if chapter_data:
                            results[str(idx)] = chapter_data
                            project["chapters"][str(idx)] = chapter_data
                        else:
                            errors[str(idx)] = error

                project_manager.save_project(project_id, project)
                return {
                    "success": True,
                    "chapters": results,
                    "errors": errors,
                    "total": len(chapter_indices),
                    "completed": len(results),
                }

            return await asyncio.to_thread(_batch_work)

        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": f"批量生成失败: {str(e)}"})

    @app.post("/api/projects/{project_id}/novel/{chapter_index}/modify")
    async def api_modify_novel(project_id: str, chapter_index: int, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        current = project["chapters"].get(str(chapter_index), {}).get("novel_text", "")
        try:
            result = llm_engine.modify_content(
                cfg["llm"], data["instruction"], current, "novel", config.TEMPLATES_DIR
            )
            project["chapters"][str(chapter_index)]["novel_text"] = result
            project["chapters"][str(chapter_index)]["confirmed"] = False
            project_manager.save_project(project_id, project)
            return {"success": True, "novel_text": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/novel/{chapter_index}/confirm")
    async def api_confirm_novel(project_id: str, chapter_index: int):
        project = project_manager.load_project(project_id)
        if str(chapter_index) in project["chapters"]:
            project["chapters"][str(chapter_index)]["confirmed"] = True
            project_manager.save_project(project_id, project)
        return {"success": True}

    @app.post("/api/projects/{project_id}/novel/{chapter_index}/polish")
    async def api_polish_novel(project_id: str, chapter_index: int, request: Request):
        """AI润色选中的文字片段"""
        data = await request.json()
        selected_text = data.get("selected_text", "")
        if not selected_text or len(selected_text) < 3:
            return JSONResponse(status_code=400, content={"success": False, "message": "选中文字太短"})

        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        chapter = project.get("chapters", {}).get(str(chapter_index), {})
        full_text = chapter.get("novel_text", "")

        # Build context: selected text + surrounding text
        idx = full_text.find(selected_text)
        context_before = full_text[max(0, idx-200):idx] if idx >= 0 else ""
        context_after = full_text[idx+len(selected_text):idx+len(selected_text)+200] if idx >= 0 else ""

        instruction = f"""请润色以下选中的文字段落，使其更加生动、有画面感、符合角色性格。
只返回润色后的文字，不要加任何解释或前后缀。
保持字数大致相当（允许±20%），保持上下文连贯。

【前文上下文】{context_before}
【需要润色的文字】{selected_text}
【后文上下文】{context_after}"""

        try:
            result = llm_engine.modify_content(
                cfg["llm"], instruction, selected_text, "novel", config.TEMPLATES_DIR
            )
            return {"success": True, "polished_text": result.strip()}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/novel/{chapter_index}/save")
    async def api_save_novel(project_id: str, chapter_index: int, request: Request):
        """保存编辑后的小说文本"""
        data = await request.json()
        project = project_manager.load_project(project_id)
        novel_text = data.get("novel_text", "")
        if str(chapter_index) in project.get("chapters", {}):
            project["chapters"][str(chapter_index)]["novel_text"] = novel_text
            project["chapters"][str(chapter_index)]["summary_text"] = novel_text[:200]
            project_manager.save_project(project_id, project)
        return {"success": True}

    # ════════════════════════════════════════
    #  第6步：生成分镜脚本
    # ════════════════════════════════════════

    def _enrich_characters_in_scene(clips, characters):
        """从reference_prompt中提取所有被提及的角色名，补全characters_in_scene"""
        char_names = [c["name"] for c in characters]
        for clip in clips:
            existing = set(clip.get("characters_in_scene", []))
            # 从a_track和c_track的prompt中检测角色名
            a = clip.get("a_track", {})
            c = clip.get("c_track", {})
            text = " ".join([
                a.get("reference_prompt", ""),
                a.get("scene_description", ""),
                c.get("tail_frame_prompt", ""),
                c.get("scene_description", ""),
            ])
            for name in char_names:
                if name not in existing and name in text:
                    existing.add(name)
            clip["characters_in_scene"] = list(existing)
        return clips

    @app.post("/api/projects/{project_id}/storyboard/batch")
    async def api_batch_storyboard(project_id: str, request: Request):
        """批量并行生成多集分镜脚本（智能调度+限流）"""
        data = await request.json()
        chapter_indices = data.get("chapter_indices", [])
        if not chapter_indices:
            return JSONResponse(status_code=400, content={"success": False, "message": "chapter_indices不能为空"})

        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        outline_chapters = project["outline"].get("chapters") or project["outline"].get("episodes") or []

        art_style = llm_engine.resolve_style_prompt(
            project["settings"].get("art_style", ""), DATA_DIR
        )

        import time as _time
        import queue as _queue
        import threading as _threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # ── 共享状态 ──
        results = {}
        errors = {}
        save_lock = _threading.Lock()
        rate_lock = _threading.Lock()
        submit_interval = [5.0]  # 初始5秒间隔，可变
        success_streak = [0]     # 连续成功计数
        active_count = [0]       # 当前活跃worker数
        max_workers = min(35, len(chapter_indices))

        def _gen_one_chapter(ch_idx):
            """生成单集分镜（线程安全）"""
            nonlocal project
            try:
                chapter_data = project["chapters"].get(str(ch_idx), {})
                if ch_idx >= len(outline_chapters):
                    return ch_idx, None, f"集索引{ch_idx}超出大纲范围（共{len(outline_chapters)}集）"
                chapter_info = outline_chapters[ch_idx]
                novel_text = chapter_data.get("novel_text", "")
                if not novel_text:
                    return ch_idx, None, "请先生成小说正文"

                for attempt in range(2):
                    try:
                        print(f"[batch] chapter {ch_idx} attempt {attempt+1}/2 start")
                        sb = llm_engine.generate_storyboard(
                            cfg["llm"], novel_text, chapter_info, project["outline"],
                            project["characters"],
                            project["settings"].get("clip_duration", 10),
                            art_style,
                            config.TEMPLATES_DIR,
                            project["settings"].get("episode_duration", 120),
                        )
                        print(f"[batch] chapter {ch_idx} done, {len(sb)} clips")
                        return ch_idx, sb, None
                    except Exception as e:
                        err_str = str(e)
                        print(f"[batch] chapter {ch_idx} attempt {attempt+1} failed: {e}")
                        # 429自适应：遇到限流时自动减速
                        if "429" in err_str or "Too many requests" in err_str:
                            with rate_lock:
                                submit_interval[0] = min(submit_interval[0] * 2, 30)
                                success_streak[0] = 0
                                print(f"[batch] 429 detected, submit_interval -> {submit_interval[0]:.1f}s")
                        if attempt == 0:
                            _time.sleep(5)
                        else:
                            return ch_idx, None, err_str
            except Exception as e:
                print(f"[batch] chapter {ch_idx} unexpected error: {e}")
                return ch_idx, None, f"意外错误: {str(e)}"

        def _on_chapter_done(ch_idx, sb, err):
            """每集完成后的回调：立即保存"""
            if err:
                errors[ch_idx] = err
                return

            # 检查placeholder
            has_placeholder = False
            if isinstance(sb, list):
                for clip in sb:
                    a_desc = clip.get("a_track", {}).get("scene_description", "")
                    if "placeholder" in a_desc.lower():
                        has_placeholder = True
                        break

            if has_placeholder:
                errors[ch_idx] = f"第{ch_idx+1}集包含placeholder，LLM未正常生成"
                print(f"[batch] chapter {ch_idx} contains placeholder, marking as failed")
                return

            # 线程安全保存
            with save_lock:
                try:
                    # 重新加载最新project（避免覆盖其他线程的修改）
                    fresh_project = project_manager.load_project(project_id)
                    _enrich_characters_in_scene(sb, fresh_project.get("characters", []))
                    fresh_project["storyboards"][str(ch_idx)] = {
                        "clips": sb,
                        "confirmed": False,
                    }
                    project_manager.save_project(project_id, fresh_project)
                    results[ch_idx] = sb
                    print(f"[batch] chapter {ch_idx} saved to project.json")
                except Exception as save_err:
                    print(f"[batch] chapter {ch_idx} save error: {save_err}")
                    errors[ch_idx] = f"保存失败: {save_err}"

            # 成功后逐步恢复速率
            with rate_lock:
                success_streak[0] += 1
                if success_streak[0] >= 3:
                    submit_interval[0] = max(submit_interval[0] * 0.8, 2)
                    success_streak[0] = 0
                    print(f"[batch] 3 consecutive successes, submit_interval -> {submit_interval[0]:.1f}s")

        # ── 智能调度器 ──
        def _run_with_scheduler():
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                pending = list(chapter_indices)
                running_futures = {}

                while pending or running_futures:
                    # 提交新任务（有空位且有任务）
                    while pending and len(running_futures) < max_workers:
                        ch_idx = pending.pop(0)
                        future = executor.submit(_gen_one_chapter, ch_idx)
                        running_futures[future] = ch_idx
                        # 错峰提交
                        if pending:
                            _time.sleep(submit_interval[0])

                    # 等待至少一个完成
                    if not running_futures:
                        break
                    done_futures = [f for f in running_futures if f.done()]
                    if not done_futures:
                        _time.sleep(0.5)
                        continue

                    for future in done_futures:
                        ch_idx = running_futures.pop(future)
                        try:
                            ch_idx, sb, err = future.result()
                            _on_chapter_done(ch_idx, sb, err)
                        except Exception as e:
                            _on_chapter_done(ch_idx, None, str(e))

        _run_with_scheduler()

        return {
            "success": True,
            "results": {str(k): {"clips": v} for k, v in results.items()},
            "errors": {str(k): v for k, v in errors.items()},
        }

    @app.post("/api/projects/{project_id}/storyboard/{chapter_index}")
    def api_generate_storyboard(project_id: str, chapter_index: int):
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        chapter_data = project["chapters"].get(str(chapter_index), {})
        outline_chapters = project["outline"].get("chapters") or project["outline"].get("episodes") or []
        chapter_info = outline_chapters[chapter_index]
        novel_text = chapter_data.get("novel_text", "")

        if not novel_text:
            return JSONResponse(status_code=400, content={"success": False, "message": "请先生成小说正文"})

        try:
            art_style = llm_engine.resolve_style_prompt(
                project["settings"].get("art_style", ""), DATA_DIR
            )
            # API级重试：整体重试1次（总共2次机会）
            last_error = None
            for attempt in range(2):
                try:
                    storyboard = llm_engine.generate_storyboard(
                        cfg["llm"], novel_text, chapter_info, project["outline"],
                        project["characters"],
                        project["settings"].get("clip_duration", 10),
                        art_style,
                        config.TEMPLATES_DIR,
                        project["settings"].get("episode_duration", 120),
                    )
                    _enrich_characters_in_scene(storyboard, project.get("characters", []))
                    project["storyboards"][str(chapter_index)] = {
                        "clips": storyboard,
                        "confirmed": False,
                    }
                    project_manager.save_project(project_id, project)
                    return {"success": True, "storyboard": storyboard}
                except Exception as e:
                    last_error = e
                    if attempt == 0:
                        import time
                        time.sleep(5)
                        continue
                    else:
                        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/storyboard/{chapter_index}/modify")
    async def api_modify_storyboard(project_id: str, chapter_index: int, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        current = project["storyboards"].get(str(chapter_index), {}).get("clips", [])
        try:
            result = llm_engine.modify_content(
                cfg["llm"], data["instruction"], current, "storyboard", config.TEMPLATES_DIR,
                characters=project.get("characters", [])
            )
            project["storyboards"][str(chapter_index)]["clips"] = result
            project["storyboards"][str(chapter_index)]["confirmed"] = False
            project_manager.save_project(project_id, project)
            return {"success": True, "storyboard": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/storyboard/{chapter_index}/confirm")
    async def api_confirm_storyboard(project_id: str, chapter_index: int):
        project = project_manager.load_project(project_id)
        if str(chapter_index) in project["storyboards"]:
            project["storyboards"][str(chapter_index)]["confirmed"] = True
            project_manager.save_project(project_id, project)
        return {"success": True}

    @app.post("/api/projects/{project_id}/storyboard/{chapter_index}/reorder")
    async def api_reorder_storyboard(project_id: str, chapter_index: int, request: Request):
        """重排分镜clips顺序"""
        project = project_manager.load_project(project_id)
        ch_key = str(chapter_index)
        sb = project.get("storyboards", {}).get(ch_key)
        if not sb or not sb.get("clips"):
            return JSONResponse(status_code=404, content={"success": False, "message": "分镜不存在"})

        try:
            data = await request.json()
            order = data.get("order", [])
            raw_clips = sb["clips"]
            print(f"[reorder] raw_clips type={type(raw_clips).__name__}, order={order}")
            # Unwrap nested dict: {clips:[...], confirmed:false} → [...]
            if isinstance(raw_clips, list):
                clips = raw_clips
            elif isinstance(raw_clips, dict):
                clips = raw_clips.get("clips", [])
            else:
                clips = []
            print(f"[reorder] clips count={len(clips)}, order count={len(order)}")
        except Exception as e:
            print(f"[reorder] PARSE ERROR: {e}")
            return JSONResponse(status_code=500, content={"success": False, "message": f"解析错误: {e}"})

        if len(order) != len(clips):
            return JSONResponse(status_code=400, content={"success": False, "message": f"order长度不匹配: order={len(order)} clips={len(clips)}"})

        # Validate indices
        if sorted(order) != list(range(len(clips))):
            return JSONResponse(status_code=400, content={"success": False, "message": "order索引无效"})

        # Reorder clips
        reordered = [clips[i] for i in order]
        for idx, clip in enumerate(reordered):
            clip["clip_index"] = idx
        sb["clips"] = reordered

        # Reorder frames if they exist
        frames_data = project.get("frames", {}).get(ch_key)
        if frames_data and frames_data.get("frames"):
            old_frames = frames_data["frames"]
            new_frames = []
            for new_pos, orig_idx in enumerate(order):
                f = next((fr for fr in old_frames if fr.get("clip_index") == orig_idx), None)
                if f:
                    f["clip_index"] = new_pos
                    new_frames.append(f)
            frames_data["frames"] = new_frames

        # Reorder videos/tasks if they exist
        videos_data = project.get("videos", {}).get(ch_key)
        if videos_data and videos_data.get("tasks"):
            old_tasks = videos_data["tasks"]
            new_tasks = []
            for new_pos, orig_idx in enumerate(order):
                t = next((tk for tk in old_tasks if tk.get("clip_index") == orig_idx), None)
                if t:
                    t["clip_index"] = new_pos
                    new_tasks.append(t)
            videos_data["tasks"] = new_tasks

        project_manager.save_project(project_id, project)
        print(f"分镜重排: project={project_id} chapter={chapter_index} order={order}")
        return {"success": True}

    # ════════════════════════════════════════
    #  第7步：生成分镜图
    # ════════════════════════════════════════

    @app.get("/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/image")
    def api_get_frame_image(project_id: str, chapter_index: int, clip_index: int):
        """返回分镜图文件（直接按 chapter/clip index 从磁盘读取，不依赖 project.json）"""
        frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{chapter_index:03d}")
        real_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")
        if not os.path.exists(real_path):
            raise HTTPException(404, "图片不存在")
        return FileResponse(real_path, media_type="image/png")

    @app.get("/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/tail")
    def api_get_tail_frame(project_id: str, chapter_index: int, clip_index: int):
        """返回尾帧图片文件（直接按 chapter/clip index 从磁盘读取，不依赖 project.json）"""
        frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{chapter_index:03d}")
        real_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")
        if not os.path.exists(real_path):
            raise HTTPException(404, "尾帧图片不存在")
        return FileResponse(real_path, media_type="image/png")

    @app.post("/api/projects/{project_id}/frames/all/generate")
    def api_generate_all_frames(project_id: str):
        """全量生成所有集的分镜图（异步模式：立即返回job_id，后台线程池执行）"""
        import uuid

        # 如果已有正在运行的任务，返回同一个job_id
        for jid, job in _frame_gen_jobs.items():
            if job.get("project_id") == project_id and job.get("status") == "running":
                return {"success": True, "job_id": jid, "total": job["total"],
                        "completed": job["completed"], "failed": job["failed"],
                        "in_progress": job["in_progress"], "already_running": True}

        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        storyboards = project.get("storyboards", {})
        if not storyboards:
            return JSONResponse(status_code=400, content={"success": False, "message": "请先生成分镜脚本"})

        # 收集需要生成的任务
        char_images = {}
        for char in project["characters"]:
            if char.get("image_path") and os.path.exists(char["image_path"]):
                char_images[char["name"]] = char["image_path"]
        tasks = []
        for ch_str, sb_data in storyboards.items():
            ch_idx = int(ch_str)
            clips = sb_data.get("clips", [])
            existing = project.get("frames", {}).get(ch_str, {}).get("frames", [])
            existing_map = {f["clip_index"]: f for f in existing}
            for i, clip in enumerate(clips):
                old = existing_map.get(i)
                # 跳过已完成且文件存在的
                if (old and old.get("status") == "completed"
                        and old.get("image_path") and os.path.exists(old["image_path"])
                        and old.get("tail_frame_path") and os.path.exists(old["tail_frame_path"])):
                    continue
                tasks.append((ch_idx, i, clip))

        if not tasks:
            # 全部已完成，直接返回
            all_frames = {}
            for ch_str, sb_data in storyboards.items():
                frames_list = project.get("frames", {}).get(ch_str, {}).get("frames", [])
                for f in frames_list:
                    if f.get("status") == "completed" and f.get("image_path"):
                        f["image_url"] = f"/api/projects/{project_id}/frames/{ch_str}/{f['clip_index']}/image"
                    if f.get("status") == "completed" and f.get("tail_frame_path"):
                        f["tail_frame_url"] = f"/api/projects/{project_id}/frames/{ch_str}/{f['clip_index']}/tail"
                all_frames[ch_str] = frames_list
            return {"success": True, "all_frames": all_frames, "total": 0, "skipped": True}

        # 创建job
        job_id = str(uuid.uuid4())[:8]
        _frame_gen_jobs[job_id] = {
            "status": "running", "project_id": project_id,
            "total": len(tasks), "completed": 0, "failed": 0, "in_progress": 0,
            "results": {}, "errors": {},
        }
        image_engine._log(f"[frame_job] {job_id} started: {len(tasks)} clips to generate for project {project_id}")

        # 后台线程执行
        def _run_frame_gen():
            job = _frame_gen_jobs[job_id]
            MAX_FRAME_RETRIES = 5
            save_lock = threading.Lock()

            def _generate_one(task):
                ch_idx, clip_idx, clip = task
                a_track = clip.get("a_track", {})
                c_track = clip.get("c_track", {})
                ref_images = []
                for char_name in clip.get("characters_in_scene", []):
                    if char_name in char_images:
                        ref_images.append({"name": char_name, "path": char_images[char_name]})

                with save_lock:
                    job["in_progress"] = job.get("in_progress", 0) + 1

                def _gen_with_retry(prompt, save_fn, label):
                    """独立重试：先生成（拿到URL），再保存（可独立重试）"""
                    image_data = None
                    for retry in range(MAX_FRAME_RETRIES + 1):
                        try:
                            if image_data is None:
                                image_data = image_engine.generate_image(
                                    cfg["image"], prompt, ref_images, resolution="1K"
                                )
                            path = save_fn(project_id, ch_idx, clip_idx, image_data)
                            return path
                        except Exception as e:
                            last_err = str(e)
                            err_lower = last_err.lower()
                            # 如果是下载/保存失败（图片URL已拿到），只重试保存
                            if image_data is not None and ("下载" in err_lower or "save" in err_lower or "http" in err_lower or "timeout" in err_lower):
                                image_engine._log(f"{label}保存失败 ch{ch_idx} clip{clip_idx} (第{retry+1}次): {last_err[:80]}，仅重试下载...")
                                time.sleep(3)
                                continue
                            # 生成失败，重试全部
                            image_data = None
                            if retry < MAX_FRAME_RETRIES:
                                wait = 10 * (retry + 1)
                                image_engine._log(f"{label}失败 ch{ch_idx} clip{clip_idx} (第{retry+1}次): {last_err[:80]}，{wait}秒后重试...")
                                time.sleep(wait)
                    return ""

                # ── 尾帧 + 头帧并行 ──
                results = {}
                with ThreadPoolExecutor(max_workers=2) as inner:
                    tail_prompt = c_track.get("tail_frame_prompt", "")
                    if tail_prompt:
                        inner.submit(lambda: results.update({"tail": _gen_with_retry(
                            tail_prompt, project_manager.save_tail_frame_image, "尾帧"
                        )}))
                    ref_prompt = a_track.get("reference_prompt", "")
                    if ref_prompt:
                        inner.submit(lambda: results.update({"head": _gen_with_retry(
                            ref_prompt, project_manager.save_frame_image, "头帧"
                        )}))
                    # inner.__exit__ 自动等待所有任务完成

                tail_path = results.get("tail", "")
                image_path = results.get("head", "")
                missing = []
                if not image_path:
                    missing.append("头帧生成失败")
                if tail_prompt and not tail_path:
                    missing.append("尾帧生成失败")
                status = "failed" if missing else "completed"

                with save_lock:
                    if status == "completed":
                        job["completed"] += 1
                    else:
                        job["failed"] += 1
                    job["in_progress"] = max(0, job["in_progress"] - 1)

                result = {
                    "chapter": ch_idx, "clip_index": clip_idx,
                    "image_path": image_path, "tail_frame_path": tail_path,
                    "status": status, "frame_retry_count": MAX_FRAME_RETRIES,
                }
                if missing:
                    result["error"] = "；".join(missing)
                return result

            try:
                with ThreadPoolExecutor(max_workers=200) as executor:
                    futures = {executor.submit(_generate_one, t): t for t in tasks}
                    for future in as_completed(futures):
                        try:
                            r = future.result()
                            ch_str = str(r["chapter"])
                            with save_lock:
                                if ch_str not in job["results"]:
                                    job["results"][ch_str] = []
                                job["results"][ch_str].append(r)
                        except Exception as e:
                            t = futures[future]
                            ch_str = str(t[0])
                            with save_lock:
                                job["failed"] += 1
                                if ch_str not in job["results"]:
                                    job["results"][ch_str] = []
                                job["results"][ch_str].append({
                                    "chapter": t[0], "clip_index": t[1],
                                    "image_path": "", "status": "failed", "error": str(e)
                                })

                # 全部完成，合并写入project.json
                fresh_project = project_manager.load_project(project_id)
                fresh_project.setdefault("frames", {})
                for ch_str, sb_data in storyboards.items():
                    clips = sb_data.get("clips", [])
                    existing = fresh_project.get("frames", {}).get(ch_str, {}).get("frames", [])
                    existing_map = {f["clip_index"]: f for f in existing}
                    for r in job["results"].get(ch_str, []):
                        existing_map[r["clip_index"]] = r
                    merged = [existing_map.get(i, {"clip_index": i, "image_path": "", "status": "failed", "error": "未生成"}) for i in range(len(clips))]
                    for f in merged:
                        if f.get("status") == "completed" and f.get("image_path"):
                            f["image_url"] = f"/api/projects/{project_id}/frames/{ch_str}/{f['clip_index']}/image"
                        if f.get("status") == "completed" and f.get("tail_frame_path"):
                            f["tail_frame_url"] = f"/api/projects/{project_id}/frames/{ch_str}/{f['clip_index']}/tail"
                    fresh_project["frames"][ch_str] = {"frames": merged}
                project_manager.save_project(project_id, fresh_project)

                job["status"] = "completed"
                image_engine._log(f"[frame_job] {job_id} completed: {job['completed']} ok, {job['failed']} failed")
            except Exception as e:
                job["status"] = "failed"
                job["error"] = str(e)
                image_engine._log(f"[frame_job] {job_id} failed: {e}")

        t = threading.Thread(target=_run_frame_gen, daemon=True)
        t.start()

        return {"success": True, "job_id": job_id, "total": len(tasks)}

    @app.get("/api/projects/{project_id}/frames/generate_status")
    def api_frame_gen_status(project_id: str, job_id: str = ""):
        """轮询分镜图生成进度"""
        if not job_id:
            # 返回该项目最新的job
            for jid, job in reversed(list(_frame_gen_jobs.items())):
                if job.get("project_id") == project_id:
                    job_id = jid
                    break
        job = _frame_gen_jobs.get(job_id)
        if not job:
            return {"success": True, "status": "not_found", "completed": 0, "total": 0, "failed": 0, "in_progress": 0}
        return {
            "success": True,
            "job_id": job_id,
            "status": job["status"],
            "total": job["total"],
            "completed": job["completed"],
            "failed": job["failed"],
            "in_progress": job.get("in_progress", 0),
            "all_frames": job.get("results", {}) if job["status"] in ("completed", "failed") else None,
        }

    @app.post("/api/projects/{project_id}/frames/{chapter_index}/generate")
    def api_generate_frames(project_id: str, chapter_index: int):
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        storyboard = project["storyboards"].get(str(chapter_index), {}).get("clips", [])

        if not storyboard:
            return JSONResponse(status_code=400, content={"success": False, "message": "请先生成分镜脚本"})

        # 跳过已全部生成的集
        existing = project.get("frames", {}).get(str(chapter_index), {}).get("frames", [])
        if (
            len(existing) == len(storyboard)
            and all(f.get("status") == "completed" for f in existing)
            and all(f.get("image_path") and os.path.exists(f["image_path"]) for f in existing)
        ):
            for f in existing:
                f["image_url"] = f"/api/projects/{project_id}/frames/{chapter_index}/{f['clip_index']}/image"
            return {"success": True, "frames": existing, "skipped": True}

        # 收集角色定妆照路径
        char_images = {}
        for char in project["characters"]:
            if char.get("image_path") and os.path.exists(char["image_path"]):
                char_images[char["name"]] = char["image_path"]

        MAX_FRAME_RETRIES = 5

        def _generate_one(i_clip):
            i, clip = i_clip
            ref_images = []
            for char_name in clip.get("characters_in_scene", []):
                if char_name in char_images:
                    ref_images.append({"name": char_name, "path": char_images[char_name]})

            last_err = None
            image_data = None
            for retry in range(MAX_FRAME_RETRIES + 1):
                try:
                    if image_data is None:
                        image_data = image_engine.generate_image(
                            cfg["image"], clip["a_track"], ref_images
                        )
                    image_path = project_manager.save_frame_image(
                        project_id, chapter_index, i, image_data
                    )
                    return {"clip_index": i, "image_path": image_path, "status": "completed", "frame_retry_count": retry}
                except Exception as e:
                    last_err = str(e)
                    err_lower = last_err.lower()
                    # 下载/保存失败：URL已拿到，只重试保存
                    if image_data is not None and ("下载" in err_lower or "save" in err_lower or "http" in err_lower or "timeout" in err_lower):
                        image_engine._log(f"分镜图保存失败 ch{chapter_index} clip{i} (第{retry+1}次): {last_err[:80]}，仅重试下载...")
                        time.sleep(3)
                        continue
                    # 生成失败：重试全部
                    image_data = None
                    if retry < MAX_FRAME_RETRIES:
                        wait = 10 * (retry + 1)
                        image_engine._log(f"分镜图生成失败 ch{chapter_index} clip{i} (第{retry+1}次): {last_err[:80]}，{wait}秒后重试...")
                        time.sleep(wait)
            return {"clip_index": i, "image_path": "", "status": "failed", "error": f"重试{MAX_FRAME_RETRIES}次仍失败: {last_err}", "frame_retry_count": MAX_FRAME_RETRIES}

        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = [None] * len(storyboard)
        with ThreadPoolExecutor(max_workers=200) as executor:
            futures = {executor.submit(_generate_one, (i, clip)): i for i, clip in enumerate(storyboard)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    results[idx] = {"clip_index": idx, "image_path": "", "status": "failed", "error": str(e)}

        for f in results:
            if f.get("status") == "completed" and f.get("image_path"):
                f["image_url"] = f"/api/projects/{project_id}/frames/{chapter_index}/{f['clip_index']}/image"

        project["frames"][str(chapter_index)] = {"frames": results}
        project_manager.save_project(project_id, project)
        return {"success": True, "frames": results}

    @app.post("/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/regenerate")
    async def api_regenerate_frame(project_id: str, chapter_index: int, clip_index: int, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        storyboard = project["storyboards"].get(str(chapter_index), {}).get("clips", [])
        if clip_index >= len(storyboard):
            raise HTTPException(400, "片段不存在")

        clip = storyboard[clip_index]
        track = data.get("track", "a")  # "a" = 参考图, "c" = 尾帧

        # AI修改：用户给出修改指令，用LLM改写场景描述后再生成图片
        instruction = data.get("instruction", "")
        if instruction:
            track_key = "a_track" if track == "a" else "c_track"
            prompt_field = "scene_description"
            current_scene = clip.get(track_key, {}).get(prompt_field, "")
            modified = llm_engine.modify_content(
                cfg["llm"], instruction, current_scene, prompt_field, config.TEMPLATES_DIR
            )
            if isinstance(modified, dict):
                target_track = modified
            elif isinstance(modified, str):
                target_track = dict(clip.get(track_key, {}))
                target_track[prompt_field] = modified
            else:
                target_track = clip.get(track_key, {})
        else:
            if track == "c":
                target_track = data.get("c_track", clip.get("c_track", {}))
            else:
                target_track = data.get("a_track", clip.get("a_track", {}))

        # 收集角色定妆照
        char_images = {}
        for char in project["characters"]:
            if char.get("image_path") and os.path.exists(char["image_path"]):
                char_images[char["name"]] = char["image_path"]

        ref_images = []
        for char_name in clip.get("characters_in_scene", []):
            if char_name in char_images:
                ref_images.append({"name": char_name, "path": char_images[char_name]})

        MAX_FRAME_RETRIES = 5
        image_data = None
        last_err = None
        for retry in range(MAX_FRAME_RETRIES + 1):
            try:
                image_data = image_engine.generate_image(
                    cfg["image"], target_track, ref_images, resolution="1K"
                )
                break
            except Exception as e:
                last_err = str(e)
                if retry < MAX_FRAME_RETRIES:
                    wait = 10 * (retry + 1)
                    image_engine._log(f"分镜图重新生成失败 ch{chapter_index} clip{clip_index} track={track} (第{retry+1}次): {last_err[:80]}，{wait}秒后重试...")
                    time.sleep(wait)

        if image_data is None:
            return JSONResponse(status_code=500, content={"success": False, "message": f"重试{MAX_FRAME_RETRIES}次仍失败: {last_err}"})

        if track == "c":
            # 尾帧：保存到tail_frame
            image_path = project_manager.save_tail_frame_image(
                project_id, chapter_index, clip_index, image_data
            )
            # 更新storyboard中的c_track（如果用户修改了）
            if data.get("c_track"):
                storyboard[clip_index]["c_track"] = data["c_track"]
                project_manager.save_project(project_id, project)
            # 更新frames中的tail_frame_path
            frames = project["frames"].get(str(chapter_index), {}).get("frames", [])
            for f in frames:
                if f["clip_index"] == clip_index:
                    f["tail_frame_path"] = image_path
                    break
            project_manager.save_project(project_id, project)
            return {"success": True, "image_path": f"/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/tail"}
        else:
            # 参考图：保存为frame
            image_path = project_manager.save_frame_image(
                project_id, chapter_index, clip_index, image_data
            )
            # 更新storyboard中的a_track（如果用户修改了）
            if data.get("a_track"):
                storyboard[clip_index]["a_track"] = data["a_track"]
                project_manager.save_project(project_id, project)
            frames = project["frames"].get(str(chapter_index), {}).get("frames", [])
            for f in frames:
                if f["clip_index"] == clip_index:
                    f["image_path"] = image_path
                    f["status"] = "completed"
                    break
            project_manager.save_project(project_id, project)
            return {"success": True, "image_path": f"/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/image"}

    @app.post("/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/upload")
    async def api_upload_frame_image(project_id: str, chapter_index: int, clip_index: int, request: Request):
        """上传本地图片替换分镜图或尾帧"""
        try:
            project = project_manager.load_project(project_id)
            form = await request.form()
            track = form.get("track", "a")  # "a" = 参考图, "c" = 尾帧
            image_file = form.get("image")
            if not image_file:
                return JSONResponse(status_code=400, content={"success": False, "message": "未收到图片文件"})
            image_bytes = await image_file.read()
            if not image_bytes:
                return JSONResponse(status_code=400, content={"success": False, "message": "图片文件为空"})
            # 保存到frames目录
            frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{chapter_index:03d}")
            os.makedirs(frame_dir, exist_ok=True)
            if track == "c":
                save_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")
            else:
                save_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")
            with open(save_path, "wb") as f:
                f.write(image_bytes)
            # 更新project数据
            frames_data = project.get("frames", {}).get(str(chapter_index), {}).get("frames", [])
            found = False
            for fr in frames_data:
                if fr["clip_index"] == clip_index:
                    if track == "c":
                        fr["tail_frame_path"] = save_path
                    else:
                        fr["image_path"] = save_path
                        fr["status"] = "completed"
                    found = True
                    break
            if not found:
                entry = {"clip_index": clip_index, "status": "completed"}
                if track == "c":
                    entry["tail_frame_path"] = save_path
                else:
                    entry["image_path"] = save_path
                frames_data.append(entry)
                project.setdefault("frames", {})[str(chapter_index)] = {"frames": frames_data}
            project_manager.save_project(project_id, project)
            img_type = "tail" if track == "c" else "image"
            return {"success": True, "image_path": f"/api/projects/{project_id}/frames/{chapter_index}/{clip_index}/{img_type}"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    # ════════════════════════════════════════
    #  第8步：生成视频
    # ════════════════════════════════════════


    @app.get("/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/video")
    def api_get_video_file(project_id: str, chapter_index: int, clip_index: int):
        """返回视频文件"""
        project = project_manager.load_project(project_id)
        tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])
        task = next((t for t in tasks if t.get("clip_index") == clip_index), None)
        if not task or not task.get("video_path") or not os.path.exists(task["video_path"]):
            raise HTTPException(404, "视频不存在")
        ext = os.path.splitext(task["video_path"])[1].lower()
        media_type = "video/mp4" if ext == ".mp4" else f"video/{ext.lstrip('.')}"
        resp = FileResponse(task["video_path"], media_type=media_type)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp

    @app.post("/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/upload")
    async def api_upload_video(project_id: str, chapter_index: int, clip_index: int, request: Request):
        """上传本地视频替换"""
        try:
            project = project_manager.load_project(project_id)
            form = await request.form()
            video_file = form.get("video")
            if not video_file:
                return JSONResponse(status_code=400, content={"success": False, "message": "未收到视频文件"})
            video_bytes = await video_file.read()
            if not video_bytes:
                return JSONResponse(status_code=400, content={"success": False, "message": "视频文件为空"})
            video_dir = os.path.join(config.PROJECTS_DIR, project_id, "videos", f"ch{chapter_index:03d}")
            os.makedirs(video_dir, exist_ok=True)
            save_path = os.path.join(video_dir, f"clip_{clip_index:03d}.mp4")
            with open(save_path, "wb") as f:
                f.write(video_bytes)
            # Update tasks
            tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])
            found = False
            for t in tasks:
                if t.get("clip_index") == clip_index:
                    t["video_path"] = save_path
                    t["video_url"] = f"/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/video"
                    t["status"] = "completed"
                    t.pop("error", None)
                    found = True
                    break
            if not found:
                tasks.append({"clip_index": clip_index, "video_path": save_path, "video_url": f"/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/video", "status": "completed"})
                project.setdefault("videos", {})[str(chapter_index)] = {"tasks": tasks}
            project_manager.save_project(project_id, project)
            return {"success": True, "video_path": save_path, "video_url": f"/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/video"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    def _rank_characters(clip, char_map):
        """按重要度排序角色：dialogue台词数 > scene_description出现顺序"""
        scores = {}
        b_track = clip.get("b_track", {})
        for d in b_track.get("dialogue", []):
            if isinstance(d, dict) and d.get("character"):
                cname = d["character"]
                scores[cname] = scores.get(cname, 0) + 10
        a_track = clip.get("a_track", {})
        scene_desc = a_track.get("scene_description", "")
        for cname in char_map:
            idx = scene_desc.find(cname)
            if idx >= 0:
                scores[cname] = scores.get(cname, 0) + max(1, 100 - idx)
        ranked = sorted(scores.keys(), key=lambda n: scores[n], reverse=True)
        return [char_map[n] for n in ranked if n in char_map][:2]

    @app.post("/api/projects/{project_id}/videos/all/generate")
    def api_generate_videos_all(project_id: str):
        """全量提交所有集所有片段的视频生成任务（异步版本：立即返回，后台分批提交）"""
        # 防护：project_id不应包含模板字符串语法
        if '$' in project_id or '{' in project_id or '}' in project_id:
            return JSONResponse(status_code=400, content={"success": False, "message": f"无效的项目ID: {project_id}"})
        project = project_manager.load_project(project_id)
        outline = project.get("outline", {})
        chapters = outline.get("chapters", []) or outline.get("episodes", [])

        if not chapters:
            return JSONResponse(status_code=400, content={"success": False, "message": "请先生成大纲"})

        # --- 幂等检查 ---
        existing_videos = project.get("videos", {})
        already_running = set()
        reused_results = {}
        for ch_str, ch_data in existing_videos.items():
            for t in ch_data.get("tasks", []):
                if t.get("status") in ("submitted", "processing", "completed"):
                    already_running.add((int(ch_str), t.get("clip_index", -1)))
            reused_list = ch_data.get("tasks", [])
            if reused_list and any(t.get("status") in ("submitted", "processing", "completed") for t in reused_list):
                reused_results[ch_str] = [{"chapter": int(ch_str), "clip_index": t.get("clip_index", i), "task_id": t.get("task_id"), "status": t.get("status")} for i, t in enumerate(reused_list)]

        # --- 收集待提交任务 ---
        pending_tasks = []
        for ch_idx in range(len(chapters)):
            sb = project.get("storyboards", {}).get(str(ch_idx), {})
            clips = sb.get("clips", [])
            for clip_idx, clip in enumerate(clips):
                if (ch_idx, clip_idx) in already_running:
                    continue
                prev_bgm = clips[clip_idx - 1].get("b_track", {}).get("background_music") if clip_idx > 0 else None
                pending_tasks.append((ch_idx, clip_idx, clip, prev_bgm))

        if not pending_tasks:
            return {"success": True, "results": reused_results, "message": "所有任务都已提交"}

        # --- 创建异步任务 ---
        job_id = f"submit_{int(time.time() * 1000)}"
        _submit_jobs[job_id] = {
            "total": len(pending_tasks),
            "submitted": 0,
            "failed": 0,
            "skipped": 0,
            "done": False,
            "results": reused_results,
            "error_list": [],
            "started_at": time.time(),
        }

        # 后台线程分批提交
        threading.Thread(
            target=_submit_worker,
            args=(job_id, project_id, pending_tasks, reused_results, 20, 10),
            daemon=True
        ).start()

        video_engine._log(f"异步提交任务启动: job_id={job_id}, 待提交={len(pending_tasks)}个, 已跳过={len(already_running)}个")
        return {"success": True, "job_id": job_id, "total_tasks": len(pending_tasks), "skipped_tasks": len(already_running)}

    def _submit_worker(job_id, project_id, pending_tasks, reused_results, batch_size, sleep_sec):
        """后台分批提交视频任务"""
        try:
            project = project_manager.load_project(project_id)
            cfg = config.load_config()
            job = _submit_jobs[job_id]
            results = reused_results.copy() if reused_results else {}
            results = {k: list(v) for k, v in results.items()}  # deep copy lists

            for batch_start in range(0, len(pending_tasks), batch_size):
                batch = pending_tasks[batch_start:batch_start + batch_size]

                def _submit_one(item):
                    ch_idx, clip_idx, clip, prev_bgm = item
                    frames = project.get("frames", {}).get(str(ch_idx), {}).get("frames", [])
                    frame = next((f for f in frames if f["clip_index"] == clip_idx), None)
                    if not frame or frame.get("status") != "completed":
                        return {"chapter": ch_idx, "clip_index": clip_idx, "status": "failed", "error": "分镜图未生成"}
                    full_prompt = _build_b_track_prompt(clip, project.get("characters", []), prev_bgm=prev_bgm, clip_index=clip_idx)
                    image_paths = []
                    frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{ch_idx:03d}")
                    if clip_idx == 0:
                        ref_path = os.path.join(frame_dir, f"clip_{clip_idx:03d}.png")
                        if os.path.exists(ref_path):
                            image_paths.append(ref_path)
                        tail_path = os.path.join(frame_dir, f"clip_{clip_idx:03d}_tail.png")
                        if os.path.exists(tail_path):
                            image_paths.append(tail_path)
                    else:
                        prev_tail = os.path.join(frame_dir, f"clip_{clip_idx-1:03d}_tail.png")
                        if os.path.exists(prev_tail):
                            image_paths.append(prev_tail)
                        ref_path = os.path.join(frame_dir, f"clip_{clip_idx:03d}.png")
                        if os.path.exists(ref_path):
                            image_paths.append(ref_path)
                        tail_path = os.path.join(frame_dir, f"clip_{clip_idx:03d}_tail.png")
                        if os.path.exists(tail_path):
                            image_paths.append(tail_path)
                    try:
                        task_id = video_engine.submit_video(
                            cfg["video"], full_prompt, image_paths,
                            duration=project.get("settings", {}).get("clip_duration", 10),
                        )
                        return {"chapter": ch_idx, "clip_index": clip_idx, "task_id": task_id, "status": "submitted", "submitted_at": time.time()}
                    except Exception as e:
                        return {"chapter": ch_idx, "clip_index": clip_idx, "status": "failed", "error": str(e)}

                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(_submit_one, item) for item in batch]
                    for future in as_completed(futures):
                        r = future.result()
                        ch = str(r["chapter"])
                        results.setdefault(ch, []).append(r)
                        if r["status"] == "submitted":
                            job["submitted"] += 1
                        elif r["status"] == "failed":
                            job["failed"] += 1
                            job["error_list"].append(r.get("error", "未知错误"))

                video_engine._log(f"异步提交进度: job={job_id} batch={batch_start//batch_size+1} submitted={job['submitted']} failed={job['failed']}/{job['total']}")

                # 批间休息（最后一批不休息）
                if batch_start + batch_size < len(pending_tasks):
                    time.sleep(sleep_sec)

            # 全部提交完成，保存项目
            for ch in results:
                results[ch].sort(key=lambda x: x["clip_index"])
            project = project_manager.load_project(project_id)
            project["videos"] = project.get("videos", {})
            for ch, task_list in results.items():
                project["videos"][ch] = project["videos"].get(ch, {})
                project["videos"][ch]["tasks"] = task_list
            project_manager.save_project(project_id, project)
            job["results"] = results
            job["done"] = True
            job["finished_at"] = time.time()
            video_engine._log(f"异步提交完成: job={job_id} submitted={job['submitted']} failed={job['failed']} total={job['total']}")

        except Exception as e:
            _submit_jobs[job_id]["done"] = True
            _submit_jobs[job_id]["error_list"].append(f"后台提交异常: {str(e)}")
            video_engine._log(f"异步提交异常: job={job_id} error={e}")

    @app.get("/api/projects/{project_id}/videos/all/submit_status")
    def api_submit_status(project_id: str, job_id: str):
        """查询异步视频提交任务的进度"""
        job = _submit_jobs.get(job_id)
        if not job:
            return JSONResponse(status_code=404, content={"success": False, "message": "任务不存在"})
        return {"success": True, "job_id": job_id, "total": job["total"], "submitted": job["submitted"], "failed": job["failed"], "done": job["done"], "results": job["results"] if job["done"] else {}, "error_list": job["error_list"][-10:]}

    @app.post("/api/projects/{project_id}/videos/{chapter_index}/generate")
    def api_generate_videos(project_id: str, chapter_index: int):
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        storyboard = project["storyboards"].get(str(chapter_index), {}).get("clips", [])
        frames = project["frames"].get(str(chapter_index), {}).get("frames", [])

        if not frames:
            return JSONResponse(status_code=400, content={"success": False, "message": "请先生成分镜图"})

        char_map = {}
        for char in project["characters"]:
            if char.get("image_path") and os.path.exists(char["image_path"]):
                char_map[char["name"]] = {"name": char["name"], "image_path": char["image_path"]}

        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _submit_one(i, clip, prev_bgm=None):
            frame = next((f for f in frames if f["clip_index"] == i), None)
            if not frame or frame["status"] != "completed":
                return {"clip_index": i, "status": "failed", "error": "分镜图未生成"}
            full_prompt = _build_b_track_prompt(clip, project["characters"], prev_bgm=prev_bgm, clip_index=i)
            # 构建图片列表：首帧 + 参考图 + 尾帧（三图模型）
            image_paths = []
            frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{chapter_index:03d}")
            if i == 0:
                ref_path = os.path.join(frame_dir, f"clip_{i:03d}.png")
                if os.path.exists(ref_path):
                    image_paths.append(ref_path)
                tail_path = os.path.join(frame_dir, f"clip_{i:03d}_tail.png")
                if os.path.exists(tail_path):
                    image_paths.append(tail_path)
            else:
                prev_tail = os.path.join(frame_dir, f"clip_{i-1:03d}_tail.png")
                if os.path.exists(prev_tail):
                    image_paths.append(prev_tail)
                ref_path = os.path.join(frame_dir, f"clip_{i:03d}.png")
                if os.path.exists(ref_path):
                    image_paths.append(ref_path)
                tail_path = os.path.join(frame_dir, f"clip_{i:03d}_tail.png")
                if os.path.exists(tail_path):
                    image_paths.append(tail_path)
            try:
                task_id = video_engine.submit_video(
                    cfg["video"], full_prompt, image_paths,
                    duration=project["settings"].get("clip_duration", 10),
                )
                return {"clip_index": i, "task_id": task_id, "status": "submitted"}
            except Exception as e:
                return {"clip_index": i, "status": "failed", "error": str(e)}

        # 幂等检查：收集已有的正在运行/已完成的任务
        already_running = set()
        existing_tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])
        for t in existing_tasks:
            if t.get("status") in ("submitted", "processing", "completed"):
                already_running.add(t.get("clip_index", -1))

        reused_results = []
        new_tasks = []
        for i, clip in enumerate(storyboard):
            if i in already_running:
                reused_results.append(next(t for t in existing_tasks if t.get("clip_index") == i))
                continue
            prev_bgm = storyboard[i - 1].get("b_track", {}).get("background_music") if i > 0 else None
            new_tasks.append((i, clip, prev_bgm))

        results = []
        if already_running:
            video_engine._log(f"幂等检查: 跳过 {len(already_running)} 个已提交/已完成的单集视频任务")
            results.extend(reused_results)

        if new_tasks:
            with ThreadPoolExecutor(max_workers=250) as executor:
                futures = {}
                for i, clip, prev_bgm in new_tasks:
                    futures[executor.submit(_submit_one, i, clip, prev_bgm)] = i
                for future in as_completed(futures):
                    r = future.result()
                    r["submitted_at"] = time.time()
                    results.append(r)

        results.sort(key=lambda r: r["clip_index"])

        project["videos"][str(chapter_index)] = {"tasks": results}
        project_manager.save_project(project_id, project)
        return {"success": True, "tasks": results}

    @app.get("/api/projects/{project_id}/videos/all/poll")
    def api_poll_videos_all(project_id: str):
        """轮询所有集所有片段的视频生成状态（只查不写，不做自动重试）"""
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        videos_data = project.get("videos", {})

        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 收集需要查询的任务（submitted/processing）
        tasks_to_poll = []

        for ch_str, ch_data in videos_data.items():
            ch_idx = int(ch_str)
            tasks = ch_data.get("tasks", [])
            for task in tasks:
                # 只查询submitted/processing状态（download_status=failed不再自动重试，改为手动重试）
                if task["status"] in ("submitted", "processing"):
                    tasks_to_poll.append((ch_idx, task))

        # 并发查询所有 task 的 Grok 真实状态
        if tasks_to_poll:
            def _poll_one(item):
                ch_idx, task = item
                try:
                    poll_result = video_engine.poll_video(cfg["video"], task["task_id"])
                    return (ch_idx, task, poll_result, None)
                except Exception as e:
                    return (ch_idx, task, None, str(e))

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = {executor.submit(_poll_one, item): item for item in tasks_to_poll}
                for future in as_completed(futures):
                    ch_idx, task, poll_result, error = future.result()
                    if error:
                        video_engine._log(f"Poll异常 ch{ch_idx} clip{task.get('clip_index')}: {error}")
                        continue
                    task["status"] = poll_result["status"]
                    task.pop("consecutive_poll_errors", None)
                    if poll_result["status"] == "completed":
                        task["download_status"] = "downloading"
                        try:
                            video_path = project_manager.save_video_file(
                                project_id, ch_idx, task["clip_index"],
                                poll_result["video_url"],
                            )
                            task["video_path"] = video_path
                            task["video_url"] = f"/api/projects/{project_id}/videos/{ch_idx}/{task['clip_index']}/video"
                            task["download_status"] = "done"
                            task.pop("error", None)
                            task.pop("external_video_url", None)
                        except Exception as dl_err:
                            task["download_status"] = "failed"
                            task["external_video_url"] = poll_result["video_url"]
                            task["video_url"] = f"/api/projects/{project_id}/videos/{ch_idx}/{task['clip_index']}/video"
                            task["error"] = f"下载失败(API已完成): {str(dl_err)[:120]}"
                            video_engine._log(f"视频下载失败 ch{ch_idx} clip{task.get('clip_index')}: {dl_err}")
                    elif poll_result["status"] == "failed":
                        task["error"] = poll_result.get("error", "未知错误")

            # 补充video_url
            for ch_str, ch_data in videos_data.items():
                ch_idx = int(ch_str)
                for task in ch_data.get("tasks", []):
                    if task["status"] == "completed" and not task.get("video_url"):
                        task["video_url"] = f"/api/projects/{project_id}/videos/{ch_idx}/{task['clip_index']}/video"

        project_manager.save_project(project_id, project)
        return {"success": True, "results": videos_data}

    @app.get("/api/projects/{project_id}/videos/{chapter_index}/poll")
    def api_poll_videos(project_id: str, chapter_index: int):
        """单集视频轮询（只查不写，不做自动重试）"""
        project = project_manager.load_project(project_id)
        cfg = config.load_config()
        tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])

        results = []
        tasks_to_poll = []

        for task in tasks:
            # 只查询submitted/processing状态（download_status=failed不再自动重试，改为手动重试）
            if task["status"] in ("submitted", "processing"):
                tasks_to_poll.append(task)
            results.append(task)

        # 并发查询 Grok 真实状态
        if tasks_to_poll:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _poll_one(task):
                try:
                    poll_result = video_engine.poll_video(cfg["video"], task["task_id"])
                    return (task, poll_result, None)
                except Exception as e:
                    return (task, None, str(e))

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(_poll_one, t) for t in tasks_to_poll]
                for future in as_completed(futures):
                    task, poll_result, error = future.result()
                    if error:
                        continue
                    task["status"] = poll_result["status"]
                    task.pop("consecutive_poll_errors", None)
                    if poll_result["status"] == "completed":
                        task["download_status"] = "downloading"
                        try:
                            video_path = project_manager.save_video_file(
                                project_id, chapter_index, task["clip_index"],
                                poll_result["video_url"],
                            )
                            task["video_path"] = video_path
                            task["video_url"] = f"/api/projects/{project_id}/videos/{chapter_index}/{task['clip_index']}/video"
                            task["download_status"] = "done"
                            task.pop("error", None)
                            task.pop("external_video_url", None)
                        except Exception as dl_err:
                            task["download_status"] = "failed"
                            task["external_video_url"] = poll_result["video_url"]
                            task["video_url"] = f"/api/projects/{project_id}/videos/{chapter_index}/{task['clip_index']}/video"
                            task["error"] = f"下载失败(API已完成): {str(dl_err)[:120]}"
                            video_engine._log(f"视频下载失败 ch{chapter_index} clip{task.get('clip_index')}: {dl_err}")
                    elif poll_result["status"] == "failed":
                        task["error"] = poll_result.get("error", "未知错误")

            # 补充video_url
            for task in results:
                if task["status"] == "completed" and not task.get("video_url"):
                    task["video_url"] = f"/api/projects/{project_id}/videos/{chapter_index}/{task['clip_index']}/video"

        project_manager.save_project(project_id, project)
        return {"success": True, "tasks": results}

    @app.post("/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/retry")
    def api_retry_single_video(project_id: str, chapter_index: int, clip_index: int):
        """手动重试单个失败的视频生成任务"""
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])
        task = next((t for t in tasks if t.get("clip_index") == clip_index), None)

        if not task:
            return JSONResponse(status_code=404, content={"success": False, "message": "任务不存在"})

        if task.get("status") in ("submitted", "processing"):
            return JSONResponse(status_code=400, content={"success": False, "message": "该任务正在处理中，不可重试"})
        if task.get("status") == "completed":
            return JSONResponse(status_code=400, content={"success": False, "message": "该任务已完成，无需重试"})

        try:
            sb = project.get("storyboards", {}).get(str(chapter_index), {})
            clips = sb.get("clips", [])
            if clip_index >= len(clips):
                return JSONResponse(status_code=400, content={"success": False, "message": "分镜不存在"})
            clip = clips[clip_index]
            frames_list = project.get("frames", {}).get(str(chapter_index), {}).get("frames", [])
            frame = next((f for f in frames_list if f["clip_index"] == clip_index), None)

            if not frame or frame.get("status") != "completed":
                return JSONResponse(status_code=400, content={"success": False, "message": "对应分镜图未生成，无法构建视频提示词"})

            prev_bgm = clips[clip_index - 1].get("b_track", {}).get("background_music") if clip_index > 0 else None
            full_prompt = _build_b_track_prompt(clip, project.get("characters", []), prev_bgm=prev_bgm, clip_index=clip_index)

            image_paths = []
            frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{chapter_index:03d}")
            if clip_index == 0:
                ref_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")
                if os.path.exists(ref_path):
                    image_paths.append(ref_path)
                tail_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")
                if os.path.exists(tail_path):
                    image_paths.append(tail_path)
            else:
                prev_tail = os.path.join(frame_dir, f"clip_{clip_index-1:03d}_tail.png")
                if os.path.exists(prev_tail):
                    image_paths.append(prev_tail)
                ref_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")
                if os.path.exists(ref_path):
                    image_paths.append(ref_path)
                tail_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")
                if os.path.exists(tail_path):
                    image_paths.append(tail_path)

            clip_duration = project.get("settings", {}).get("clip_duration", 10)
            new_task_id = video_engine.submit_video(
                cfg["video"], full_prompt, image_paths, duration=clip_duration,
            )

            task["history_task_ids"] = task.get("history_task_ids", []) + [task.get("task_id")]
            task["task_id"] = new_task_id
            task["status"] = "submitted"
            task["submitted_at"] = time.time()
            task["video_retry_count"] = task.get("video_retry_count", 0) + 1
            task.pop("error", None)

            project_manager.save_project(project_id, project)
            return {"success": True, "message": "重新提交成功", "task": task}

        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": f"重试提交失败: {str(e)}"})

    @app.post("/api/projects/{project_id}/videos/{chapter_index}/{clip_index}/regenerate")
    async def api_regenerate_video(project_id: str, chapter_index: int, clip_index: int, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        cfg = config.load_config()

        storyboard = project["storyboards"].get(str(chapter_index), {}).get("clips", [])
        if clip_index >= len(storyboard):
            raise HTTPException(400, "片段不存在")

        clip = storyboard[clip_index]
        frames = project["frames"].get(str(chapter_index), {}).get("frames", [])
        frame = next((f for f in frames if f["clip_index"] == clip_index), None)

        if not frame or not frame.get("image_path"):
            raise HTTPException(400, "分镜图未生成")

        # 如果用户修改了B轨
        if data.get("b_track"):
            clip["b_track"] = data["b_track"]

        # 按重要度排序角色，最多2张
        char_map = {}
        for c in project["characters"]:
            if c.get("image_path") and os.path.exists(c["image_path"]):
                char_map[c["name"]] = {"name": c["name"], "image_path": c["image_path"]}
        scores = {}
        for d in clip.get("b_track", {}).get("dialogue", []):
            if isinstance(d, dict) and d.get("character"):
                scores[d["character"]] = scores.get(d["character"], 0) + 10
        scene_desc = clip.get("a_track", {}).get("scene_description", "")
        for cname in char_map:
            idx = scene_desc.find(cname)
            if idx >= 0:
                scores[cname] = scores.get(cname, 0) + max(1, 100 - idx)
        ranked = sorted(scores.keys(), key=lambda n: scores[n], reverse=True)
        ranked_chars = [char_map[n] for n in ranked if n in char_map][:2]

        prev_bgm = storyboard[clip_index - 1].get("b_track", {}).get("background_music") if clip_index > 0 else None
        full_prompt = _build_b_track_prompt(clip, project["characters"], prev_bgm=prev_bgm, clip_index=clip_index)

        image_paths = []
        frame_dir = os.path.join(config.PROJECTS_DIR, project_id, "frames", f"ch{chapter_index:03d}")
        if clip_index == 0:
            ref_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")
            if os.path.exists(ref_path):
                image_paths.append(ref_path)
            tail_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")
            if os.path.exists(tail_path):
                image_paths.append(tail_path)
        else:
            prev_tail = os.path.join(frame_dir, f"clip_{clip_index-1:03d}_tail.png")
            if os.path.exists(prev_tail):
                image_paths.append(prev_tail)
            ref_path = os.path.join(frame_dir, f"clip_{clip_index:03d}.png")
            if os.path.exists(ref_path):
                image_paths.append(ref_path)
            tail_path = os.path.join(frame_dir, f"clip_{clip_index:03d}_tail.png")
            if os.path.exists(tail_path):
                image_paths.append(tail_path)

        try:
            task_id = video_engine.submit_video(
                cfg["video"], full_prompt, image_paths,
                duration=project["settings"].get("clip_duration", 10),
            )

            tasks = project["videos"].get(str(chapter_index), {}).get("tasks", [])
            for t in tasks:
                if t["clip_index"] == clip_index:
                    t["task_id"] = task_id
                    t["status"] = "submitted"
                    t["submitted_at"] = time.time()
                    t["video_path"] = ""
                    break
            project_manager.save_project(project_id, project)

            return {"success": True, "task_id": task_id}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


    @app.get("/api/render-presets")
    async def api_render_presets():
        presets = []
        for key, cfg in ffmpeg_utils.RENDER_PRESETS.items():
            presets.append({
                "id": key,
                "name": cfg["name"],
                "desc": cfg["desc"],
                "codec": cfg["codec"],
                "resolution": cfg["resolution"],
                "fps": cfg["fps"],
            })
        return {"presets": presets, "default": "standard"}

    @app.get("/api/projects/{project_id}/compose/status")
    async def api_compose_status(project_id: str):
        """Return which chapters have composed videos."""
        project = project_manager.load_project(project_id)
        output_dir = project_manager.get_project_path(project_id, "output")
        chapters = project.get("outline", {}).get("chapters", []) or project.get("outline", {}).get("episodes", [])
        statuses = []
        for i in range(len(chapters)):
            ch_final = os.path.join(output_dir, f"ch{i:03d}_final.mp4")
            ch_concat = os.path.join(output_dir, f"ch{i:03d}_concat.mp4")
            has_final = os.path.exists(ch_final)
            has_concat = os.path.exists(ch_concat)
            # Count how many source videos exist
            video_tasks = project.get("videos", {}).get(str(i), {}).get("tasks", [])
            completed_videos = sum(1 for t in video_tasks if t.get("status") == "completed" and t.get("video_path"))
            total_clips = len(project.get("storyboards", {}).get(str(i), {}).get("clips", []))
            statuses.append({
                "index": i,
                "title": chapters[i].get("title", f"第{i+1}集"),
                "has_composed": has_final or has_concat,
                "composed_type": "final" if has_final else ("concat" if has_concat else None),
                "video_path": ch_final if has_final else (ch_concat if has_concat else None),
                "completed_videos": completed_videos,
                "total_clips": total_clips,
            })
        return {"chapters": statuses}

    # ════════════════════════════════════════
    #  第9步：后期合成
    # ════════════════════════════════════════

    @app.post("/api/projects/{project_id}/compose/all")
    async def api_compose_all(project_id: str, request: Request):
        """拼接所有已合成集为完整视频"""
        data = await request.json()
        project = project_manager.load_project(project_id)
        chapters = project.get("outline", {}).get("chapters", project.get("outline", {}).get("episodes", []))
        output_dir = project_manager.get_project_path(project_id, "output")

        preset_name = data.get("render_preset", "standard")
        if preset_name not in ffmpeg_utils.ALLOWED_PRESETS:
            preset_name = "standard"

        # 收集所有已合成的 _final.mp4
        final_paths = []
        for i in range(len(chapters)):
            final_path = os.path.join(output_dir, f"ch{i:03d}_final.mp4")
            if os.path.exists(final_path):
                final_paths.append(final_path)
                continue
            concat_path = os.path.join(output_dir, f"ch{i:03d}_concat.mp4")
            if os.path.exists(concat_path):
                final_paths.append(concat_path)

        if not final_paths:
            return JSONResponse(status_code=400, content={"success": False, "message": "没有已合成的剧集"})

        output_path = os.path.join(output_dir, "complete_final.mp4")
        try:
            ffmpeg_utils.concat_videos(final_paths, output_path, transition="none", preset_name=preset_name)
            return {"success": True, "video_path": output_path}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/compose/{chapter_index}")
    async def api_compose_chapter(project_id: str, chapter_index: int, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)

        video_tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])
        storyboard = project.get("storyboards", {}).get(str(chapter_index), {}).get("clips", [])

        # 按顺序收集视频路径
        video_paths = []
        for i, clip in enumerate(storyboard):
            task = next((t for t in video_tasks if t["clip_index"] == i), None)
            if task and task.get("video_path") and os.path.exists(task["video_path"]):
                video_paths.append(task["video_path"])

        # 调试日志写文件（PyInstaller noconsole下print丢失）
        try:
            _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
            with open(_log_path, "a", encoding="utf-8") as _f:
                from datetime import datetime as _dt
                _f.write(f"\n[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] chapter={chapter_index}\n")
                _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] storyboard clips: {len(storyboard)}\n")
                _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] video_tasks: {len(video_tasks)}\n")
                _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] video_paths collected: {len(video_paths)}\n")
                for _i, _vp in enumerate(video_paths):
                    _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE]   path[{_i}]: {_vp} exists={os.path.exists(_vp)}\n")
                _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] transition={data.get('transition', 'none')}\n")
                _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] transition_duration={data.get('transition_duration', 0.5)}\n")
                _f.write(f"[{_dt.now().strftime('%H:%M:%S')}] [COMPOSE] render_preset={data.get('render_preset', 'standard')}\n")
        except:
            pass

        if not video_paths:
            return JSONResponse(status_code=400, content={"success": False, "message": "没有已生成的视频"})

        output_dir = project_manager.get_project_path(project_id, "output")
        transition = data.get("transition", "none")
        # 渲染管线预设（防绕过：后端强制验证，无效值回退standard）
        preset_name = data.get("render_preset", "standard")
        if preset_name not in ffmpeg_utils.ALLOWED_PRESETS:
            preset_name = "standard"

        try:
            # 拼接视频
            concat_path = os.path.join(output_dir, f"ch{chapter_index:03d}_concat.mp4")
            transition_duration = float(data.get("transition_duration", 0.5))
            ffmpeg_utils.concat_videos(video_paths, concat_path, transition, transition_duration=transition_duration, preset_name=preset_name)

            # 直接返回concat结果，不加字幕
            return {
                "success": True,
                "video_path": concat_path,
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/compose/{chapter_index}/raw-export")
    async def api_raw_export_chapter(project_id: str, chapter_index: int):
        """直接拼接视频，不加字幕/转场，方便二次创作"""
        project = project_manager.load_project(project_id)
        video_tasks = project.get("videos", {}).get(str(chapter_index), {}).get("tasks", [])
        storyboard = project.get("storyboards", {}).get(str(chapter_index), {}).get("clips", [])

        # 按clip_index顺序收集视频路径
        video_paths = []
        for i in range(len(storyboard)):
            task = next((t for t in video_tasks if t.get("clip_index") == i), None)
            if task and task.get("video_path") and os.path.exists(task["video_path"]):
                video_paths.append(task["video_path"])

        if not video_paths:
            return JSONResponse(status_code=400, content={"success": False, "message": "没有已生成的视频"})

        output_dir = project_manager.get_project_path(project_id, "output")
        output_path = os.path.join(output_dir, f"ch{chapter_index:03d}_raw.mp4")

        try:
            # 用concat demuxer直接拼接，零滤镜
            import tempfile
            list_path = os.path.join(output_dir, f"_concat_list_{chapter_index}.txt")
            with open(list_path, "w", encoding="utf-8") as f:
                for vp in video_paths:
                    f.write(f"file '{vp}'\n")
            ffmpeg_bin = config.FFMPEG_PATH
            cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            os.remove(list_path)
            if result.returncode != 0:
                raise RuntimeError(f"拼接失败: {result.stderr[-500:]}")

            return {
                "success": True,
                "video_path": output_path,
                "video_url": f"/api/projects/{project_id}/compose/{chapter_index}/raw-video",
                "clip_count": len(video_paths),
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.get("/api/projects/{project_id}/compose/{chapter_index}/raw-video")
    def api_get_raw_video(project_id: str, chapter_index: int):
        """返回直接导出的视频文件"""
        output_dir = project_manager.get_project_path(project_id, "output")
        raw_path = os.path.join(output_dir, f"ch{chapter_index:03d}_raw.mp4")
        if not os.path.exists(raw_path):
            raise HTTPException(404, "视频不存在，请先执行直接导出")
        return FileResponse(raw_path, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    @app.get("/api/projects/{project_id}/compose/{chapter_index}/raw-export/save-as")
    def api_raw_export_save_as(project_id: str, chapter_index: int):
        """返回直接导出视频路径，供前端调用 pywebview 保存对话框"""
        output_dir = project_manager.get_project_path(project_id, "output")
        raw_path = os.path.join(output_dir, f"ch{chapter_index:03d}_raw.mp4")
        if not os.path.exists(raw_path):
            return JSONResponse(status_code=404, content={"success": False, "message": "视频不存在，请先执行直接导出"})
        return {"success": True, "source_path": raw_path, "default_name": f"第{chapter_index+1}集_raw.mp4"}

    @app.get("/api/projects/{project_id}/compose/all/save-as")
    def api_compose_all_save_as(project_id: str):
        """返回完整合成视频路径，供前端调用 pywebview 保存对话框"""
        output_dir = project_manager.get_project_path(project_id, "output")
        video_path = os.path.join(output_dir, "complete_final.mp4")
        if not os.path.exists(video_path):
            return JSONResponse(status_code=404, content={"success": False, "message": "完整视频不存在，请先全部合成"})
        return {"success": True, "source_path": video_path, "default_name": "完整视频_final.mp4"}

    @app.get("/api/projects/{project_id}/compose/{chapter_index}/save-as")
    def api_compose_save_as(project_id: str, chapter_index: int):
        """返回合成视频路径，供前端调用 pywebview 保存对话框"""
        output_dir = project_manager.get_project_path(project_id, "output")
        final_path = os.path.join(output_dir, f"ch{chapter_index:03d}_final.mp4")
        concat_path = os.path.join(output_dir, f"ch{chapter_index:03d}_concat.mp4")
        video_path = final_path if os.path.exists(final_path) else concat_path
        if not os.path.exists(video_path):
            return JSONResponse(status_code=404, content={"success": False, "message": "视频不存在，请先合成"})
        suffix = "_final" if video_path == final_path else "_concat"
        return {"success": True, "source_path": video_path, "default_name": f"第{chapter_index+1}集{suffix}.mp4"}

    # ════════════════════════════════════════
    #  海报生成功能
    # ════════════════════════════════════════

    @app.post("/api/projects/{project_id}/poster/generate")
    async def api_generate_poster(project_id: str, request: Request):
        """生成海报：基于分镜图 + 剧名"""
        try:
            data = await request.json()
            title = data.get("title", "")
            ch_idx = data.get("chapter", 0)
            clip_idx = data.get("clip_index", 0)
            frame_type = data.get("frame_type", "head")

            if not title:
                return JSONResponse(status_code=400, content={"success": False, "message": "请输入剧名"})

            project = project_manager.load_project(project_id)
            cfg = config.load_config()

            # 获取分镜图路径作为参考（根据frame_type选择首帧或尾帧）
            frames_data = project.get("frames", {}).get(str(ch_idx), {}).get("frames", [])
            ref_frame = next((f for f in frames_data if f.get("clip_index") == clip_idx), None)
            if not ref_frame:
                return JSONResponse(status_code=400, content={"success": False, "message": "该分镜图不存在，请先生成分镜图"})

            if frame_type == "tail":
                ref_image_path = ref_frame.get("tail_frame_path", "")
            else:
                ref_image_path = ref_frame.get("image_path", "")

            if not ref_image_path or not os.path.exists(ref_image_path):
                return JSONResponse(status_code=400, content={"success": False, "message": "分镜图文件不存在"})

            # 构建海报prompt
            poster_prompt = (
                f"You are a professional movie poster designer. I will provide you with a reference image from a short drama/film scene. "
                f"Your task: Design a cinematic movie poster based on this reference image as the foundation. "
                f"CRITICAL REQUIREMENTS: "
                f"1. DO NOT modify, alter, or change ANY element of the original reference image — keep the characters, composition, lighting, colors, and environment EXACTLY as they are in the source. "
                f"2. ONLY add poster design elements ON TOP of the existing image: Movie title text \"{title}\" prominently displayed in cinematic typography (Chinese calligraphy style or elegant serif font), "
                f"Subtle atmospheric overlay effects (light rays, particles, vignette), Professional poster border and framing elements, Dramatic lighting enhancement to make the scene pop. "
                f"3. The title text should be placed at the top or bottom, NOT covering the main characters' faces. "
                f"4. Style: High-end cinematic movie poster, dramatic and epic feel. "
                f"The reference image content should remain 100% intact — you are a poster designer adding design elements, NOT an image editor modifying the source material. "
                f"STRICTLY PROHIBITED: DO NOT add any text other than the title \"{title}\". Absolutely NO release dates, NO year numbers, NO actor names, NO taglines, NO marketing slogans like \"coming soon\" or \"震撼上映\", NO \"2024\", NO \"2025\", NO rating labels, NO studio logos. The ONLY text allowed on the entire poster is the movie title \"{title}\" and nothing else."
            )

            # 调用图片模型生成海报
            reference_images = [{"name": "scene", "path": ref_image_path}]
            image_data = image_engine.generate_image(
                cfg["image"], poster_prompt,
                reference_images=reference_images,
                size="3:4",
                resolution="2K"
            )

            # 保存海报
            poster_dir = os.path.join(config.PROJECTS_DIR, project_id, "poster")
            os.makedirs(poster_dir, exist_ok=True)
            poster_path = os.path.join(poster_dir, "poster.png")

            import base64
            if image_data.startswith("http"):
                project_manager._http_download(image_data, poster_path)
            elif image_data.startswith("data:"):
                _, b64 = image_data.split(",", 1)
                with open(poster_path, "wb") as f:
                    f.write(base64.b64decode(b64))
            else:
                with open(poster_path, "wb") as f:
                    f.write(base64.b64decode(image_data))

            # 更新project.json
            project["poster"] = {
                "image_path": poster_path,
                "image_url": f"/api/projects/{project_id}/poster/image",
                "title": title,
                "source_frame": {"chapter": ch_idx, "clip_index": clip_idx, "frame_type": frame_type},
                "status": "completed"
            }
            project_manager.save_project(project_id, project)

            return {
                "success": True,
                "image_path": poster_path,
                "image_url": f"/api/projects/{project_id}/poster/image?t={int(time.time())}",
                "title": title
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/poster/upload")
    async def api_upload_poster(project_id: str, request: Request):
        """上传本地海报图片"""
        try:
            project = project_manager.load_project(project_id)
            form = await request.form()
            image_file = form.get("image")
            title = form.get("title", "")
            if not image_file:
                return JSONResponse(status_code=400, content={"success": False, "message": "未收到图片文件"})

            image_bytes = await image_file.read()
            if not image_bytes:
                return JSONResponse(status_code=400, content={"success": False, "message": "图片文件为空"})

            poster_dir = os.path.join(config.PROJECTS_DIR, project_id, "poster")
            os.makedirs(poster_dir, exist_ok=True)
            save_path = os.path.join(poster_dir, "poster.png")
            with open(save_path, "wb") as f:
                f.write(image_bytes)

            project["poster"] = {
                "image_path": save_path,
                "image_url": f"/api/projects/{project_id}/poster/image",
                "title": title or project.get("poster", {}).get("title", ""),
                "source_frame": project.get("poster", {}).get("source_frame", {}),
                "status": "completed"
            }
            project_manager.save_project(project_id, project)

            return {
                "success": True,
                "image_path": save_path,
                "image_url": f"/api/projects/{project_id}/poster/image?t={int(time.time())}"
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": f"上传失败: {str(e)}"})

    @app.post("/api/projects/{project_id}/poster/modify")
    async def api_modify_poster(project_id: str, request: Request):
        """AI修改海报"""
        try:
            data = await request.json()
            instruction = data.get("instruction", "")
            if not instruction:
                return JSONResponse(status_code=400, content={"success": False, "message": "请输入修改指令"})

            project = project_manager.load_project(project_id)
            cfg = config.load_config()
            poster = project.get("poster", {})
            title = poster.get("title", project.get("name", ""))
            current_path = poster.get("image_path", "")

            if not current_path or not os.path.exists(current_path):
                return JSONResponse(status_code=400, content={"success": False, "message": "当前海报不存在，请先生成"})

            # 构建修改prompt
            modify_prompt = (
                f"You are a professional movie poster designer. I will provide you with a reference image (current poster). "
                f"Your task: Modify the poster based on the following instruction while keeping the overall design quality. "
                f"Instruction: {instruction} "
                f"Keep the movie title \"{title}\" visible and well-integrated. "
                f"Maintain cinematic poster quality and professional design standards."
            )

            reference_images = [{"name": "current_poster", "path": current_path}]
            image_data = image_engine.generate_image(
                cfg["image"], modify_prompt,
                reference_images=reference_images,
                size="3:4",
                resolution="2K"
            )

            poster_dir = os.path.join(config.PROJECTS_DIR, project_id, "poster")
            os.makedirs(poster_dir, exist_ok=True)
            poster_path = os.path.join(poster_dir, "poster.png")

            import base64
            if image_data.startswith("http"):
                project_manager._http_download(image_data, poster_path)
            elif image_data.startswith("data:"):
                _, b64 = image_data.split(",", 1)
                with open(poster_path, "wb") as f:
                    f.write(base64.b64decode(b64))
            else:
                with open(poster_path, "wb") as f:
                    f.write(base64.b64decode(image_data))

            poster["image_path"] = poster_path
            poster["image_url"] = f"/api/projects/{project_id}/poster/image"
            poster["status"] = "completed"
            project["poster"] = poster
            project_manager.save_project(project_id, project)

            return {
                "success": True,
                "image_path": poster_path,
                "image_url": f"/api/projects/{project_id}/poster/image?t={int(time.time())}"
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.get("/api/projects/{project_id}/poster/image")
    def api_get_poster_image(project_id: str):
        """返回海报图片"""
        project = project_manager.load_project(project_id)
        poster = project.get("poster", {})
        img_path = poster.get("image_path", "")
        if not img_path or not os.path.exists(img_path):
            raise HTTPException(404, "海报不存在")
        return FileResponse(img_path, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/projects/{project_id}/poster/export")
    def api_export_poster(project_id: str):
        """导出海报图片"""
        project = project_manager.load_project(project_id)
        poster = project.get("poster", {})
        img_path = poster.get("image_path", "")
        if not img_path or not os.path.exists(img_path):
            raise HTTPException(404, "海报不存在")
        title = poster.get("title", "poster")
        safe_title = project_manager._safe_filename(title)
        return FileResponse(
            img_path, media_type="image/png",
            filename=f"{safe_title}_poster.png",
            headers={"Cache-Control": "no-store"}
        )

    @app.get("/api/projects/{project_id}/poster/save-as")
    def api_poster_save_as(project_id: str):
        """返回海报路径信息，供前端调用pywebview原生保存对话框"""
        project = project_manager.load_project(project_id)
        poster = project.get("poster", {})
        img_path = poster.get("image_path", "")
        if not img_path or not os.path.exists(img_path):
            return JSONResponse(status_code=404, content={"success": False, "message": "海报不存在"})
        title = poster.get("title", "poster")
        safe_title = project_manager._safe_filename(title)
        return {"success": True, "source_path": img_path, "default_name": f"{safe_title}_poster.png"}

    # ════════════════════════════════════════
    #  第10步：导出
    # ════════════════════════════════════════

    @app.post("/api/projects/{project_id}/export")
    async def api_export(project_id: str, request: Request):
        data = await request.json()
        project = project_manager.load_project(project_id)
        output_dir = project_manager.get_project_path(project_id, "output")

        export_path = data.get("path", os.path.join(output_dir, "漫剧成品.mp4"))

        try:
            result = project_manager.export_project(
                project_id, export_path,
                resolution=data.get("resolution", "1080p"),
                fps=data.get("fps", 30),
                codec=data.get("codec", "h264"),
                bitrate=data.get("bitrate", "high"),
            )
            return {"success": True, "path": result}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/export/batch")
    async def api_export_batch(project_id: str, request: Request):
        """批量导出所有已合成的视频到指定文件夹"""
        import shutil
        import glob

        data = await request.json()
        target_folder = data.get("folder", "")

        output_dir = project_manager.get_project_path(project_id, "output")

        # 如果用户没指定文件夹，用项目输出目录
        if not target_folder or not os.path.isabs(target_folder):
            target_folder = output_dir

        if not os.path.exists(target_folder):
            os.makedirs(target_folder, exist_ok=True)

        # 收集所有已合成的视频
        video_files = sorted(glob.glob(os.path.join(output_dir, "ch*_final.mp4")))
        if not video_files:
            video_files = sorted(glob.glob(os.path.join(output_dir, "ch*_concat.mp4")))

        if not video_files:
            return JSONResponse(status_code=404, content={"success": False, "message": "没有已合成的视频"})

        exported = []
        for src in video_files:
            filename = os.path.basename(src)
            dst = os.path.join(target_folder, filename)
            try:
                shutil.copy2(src, dst)
                exported.append(dst)
            except Exception as e:
                print(f"[export-batch] 复制 {filename} 失败: {e}")

        return {"success": True, "exported": len(exported), "exported_paths": exported, "folder": target_folder}

    # ════════════════════════════════════════
    #  聊天 API（通用 LLM 对话）
    # ════════════════════════════════════════

    @app.post("/api/chat")
    async def api_chat(request: Request):
        data = await request.json()
        cfg = config.load_config()

        # Check API key configured
        llm_cfg = cfg.get("llm", {})
        if not llm_cfg.get("api_key"):
            return JSONResponse(status_code=400, content={"success": False, "message": "请先在设置中配置 API Key"})

        # Frontend sends {message, history, project_id}
        msg = data.get("message", "").strip()
        history = data.get("history", [])

        if not msg and not history:
            return JSONResponse(status_code=400, content={"success": False, "message": "消息不能为空"})

        # Build system prompt with project context
        system_prompt = (
            "你是 Synapse AI 创作助手，一个专业的故事创作和漫剧制作顾问。"
            "你擅长故事架构、角色设计、对白编写、分镜脚本和影视制作相关知识。"
            "请用中文回答，简洁专业，围绕用户的创作需求提供有价值的建议。"
            "回答控制在200字以内，除非用户明确要求详细展开。"
        )

        # Inject project context if available
        project_id = data.get("project_id")
        if project_id:
            try:
                proj = project_manager.load_project(project_id)
                ctx_parts = [f"当前项目：{proj.get('name', '未命名')}"]
                if proj.get("title"):
                    ctx_parts.append(f"作品标题：{proj['title']}")
                outline = proj.get("outline")
                if outline:
                    if outline.get("synopsis"):
                        ctx_parts.append(f"简介：{outline['synopsis'][:200]}")
                    chapters = outline.get("chapters") or outline.get("episodes") or []
                    if chapters:
                        ctx_parts.append(f"共{len(chapters)}集")
                step = proj.get("current_step", 2)
                step_names = {2: "创意/大纲", 3: "大纲", 4: "角色定妆", 5: "小说创作", 6: "分镜脚本", 7: "AI生图", 8: "AI视频", 9: "合成", 10: "导出"}
                ctx_parts.append(f"当前步骤：{step_names.get(step, f'步骤{step}')}")
                system_prompt += "\n\n项目上下文：\n" + "\n".join(ctx_parts)
            except Exception:
                pass  # Project not found, continue without context

        # Build messages array: system + history + current user message
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        if msg:
            messages.append({"role": "user", "content": msg})

        # 检测画风意图：关键词匹配（支持正则）
        import re
        style_keywords = ["画风", "风格", "style", ".*风$", "帮我.*画", "生成.*画", "机甲", "水墨", "赛博", "蒸汽朋克", "中国", "古代", "穿越", "霓虹", "暗黑", "奇幻", "仙侠", "武侠", "科幻", "废土", "像素", "吉卜力", "写实", "唯美", "哥特", "波普"]
        is_style_request = any(re.search(kw, msg) for kw in style_keywords)

        try:
            # 画风意图：非流式生成画风JSON
            if is_style_request:
                style_sys = (
                    "You are an art style designer. Given a user description, generate a visual art style.\n"
                    "【最高指令：零废话】你必须【立即且仅输出】JSON对象，严禁输出任何前言、过渡句、客套话、解释。\n"
                    "Output STRICTLY a JSON object with these fields:\n"
                    "- id: lowercase_english snake_case identifier (max 30 chars)\n"
                    "- name: Chinese name (max 12 chars)\n"
                    "- name_en: English name (max 30 chars)\n"
                    "- prompt: English visual style prompt, 50-65 words. Must describe visual elements only (colors, textures, lighting, composition). Do NOT include scene content.\n"
                    "- tone: one of cool/warm/neutral\n"
                    "- lighting: one of natural/neon/dramatic/cinematic\n"
                    "NO explanation, NO markdown, ONLY the JSON object."
                )
                style_msgs = [
                    {"role": "system", "content": style_sys},
                    {"role": "user", "content": msg}
                ]

                result_text = llm_engine.call_llm(llm_cfg, style_msgs, temperature=0.0, max_tokens=4096)
                style_json = llm_engine._parse_json_response(result_text)
                if style_json and isinstance(style_json, dict) and "id" in style_json:
                    style_json["name"] = style_json.get("name", "")[:12]
                    style_json["name_en"] = style_json.get("name_en", "")[:30]
                    style_json["prompt"] = style_json.get("prompt", "")[:500]
                    return {
                        "response": f"已为你生成「{style_json['name']}」画风。",
                        "style_generated": style_json
                    }
                else:
                    return {
                        "response": "画风生成失败，请重试。",
                        "style_generated": None
                    }
            else:
                # 普通对话：非流式
                result_text = llm_engine.call_llm(llm_cfg, messages, temperature=0.7, max_tokens=2048)
                return {"response": result_text}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


    @app.post("/api/browse-folder")
    async def api_browse_folder(request: Request):
        """Open a native folder picker dialog."""
        import tkinter as tk
        from tkinter import filedialog
        data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
        initial = data.get("initial_dir", "")

        def _pick():
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory(initialdir=initial or None, title="选择导出目录")
            root.destroy()
            return folder

        try:
            import asyncio
            folder = await asyncio.get_event_loop().run_in_executor(None, _pick)
            if folder:
                return {"success": True, "path": folder}
            return {"success": False, "message": "未选择目录"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/open-folder")
    async def api_open_folder(request: Request):
        """Open a folder in the system file explorer."""
        data = await request.json()
        path = data.get("path", "")
        if not path or not os.path.exists(path):
            return JSONResponse(status_code=400, content={"success": False, "message": "路径不存在"})
        try:
            if os.path.isfile(path):
                path = os.path.dirname(path)
            import subprocess
            subprocess.Popen(["explorer", path])
            return {"success": True}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})

    @app.post("/api/projects/{project_id}/export/browse")
    async def api_export_browse(project_id: str, request: Request):
        """Browse for export save path (file save dialog)."""
        import tkinter as tk
        from tkinter import filedialog
        output_dir = project_manager.get_project_path(project_id, "output")

        def _pick():
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.asksaveasfilename(
                initialdir=output_dir,
                initialfile="漫剧成品.mp4",
                defaultextension=".mp4",
                filetypes=[("MP4视频", "*.mp4"), ("所有文件", "*.*")],
                title="选择导出路径",
            )
            root.destroy()
            return path

        try:
            import asyncio
            path = await asyncio.get_event_loop().run_in_executor(None, _pick)
            if path:
                return {"success": True, "path": path}
            return {"success": False, "message": "未选择路径"}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


    # ════════════════════════════════════════
    #  文件服务
    # ════════════════════════════════════════

    @app.get("/api/file")
    async def api_get_file(path: str):
        """获取项目文件（图片/视频）"""
        if not project_manager.is_project_file(path):
            raise HTTPException(404, "文件不存在")
        return FileResponse(path)

    @app.get("/api/download-file")
    async def api_download_file(path: str, filename: str = ""):
        """下载文件（带Content-Disposition: attachment）"""
        if not project_manager.is_project_file(path):
            raise HTTPException(404, "文件不存在")
        if not filename:
            filename = os.path.basename(path)
        return FileResponse(path, filename=filename, media_type="application/octet-stream")

    # ════════════════════════════════════════
    #  根路由
    # ════════════════════════════════════════

    @app.get("/")
    async def root():
        index_path = os.path.join(APP_DIR, "static", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Synapse API Server", "version": "1.0.0"}

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "ffmpeg": ffmpeg_utils.check_ffmpeg(),
            "version": "1.0.0",
        }

    return app


# ── 内部工具函数 ──


def _build_b_track_prompt(clip, characters, prev_bgm=None, prev_clip_id=None, clip_index=0, has_ref_image=True):
    """构建完整的B轨提示词，适配首帧+参考图+尾帧三图模型"""
    b_track = clip.get("b_track", {})

    # 构建 IMAGE REFERENCE 语义说明（替代旧的 CHARACTER REFERENCE）
    if clip_index == 0:
        image_ref_text = (
            "IMAGE REFERENCE — HARD CONSTRAINTS:\n"
            "- Image 1 (Starting Frame): This IS your first frame. The video MUST begin from this exact visual state — same pose, same lighting, same composition. Do NOT deviate from this image at the start.\n"
            "- Image 2 (Ending Frame): This IS your final frame. The video MUST end on this exact visual state — same pose, same composition, same lighting. The entire animation must transition from Image 1 to Image 2, with Image 2 as the definitive ending.\n"
        )
    else:
        image_ref_text = (
            "IMAGE REFERENCE — HARD CONSTRAINTS:\n"
            "- Image 1 (Starting Frame): This IS your first frame. The video MUST begin from this exact visual state — same pose, same lighting, same composition. Do NOT deviate from this image at the start.\n"
            "- Image 2 (Style Reference): Maintain this exact visual style, color palette, lighting quality, and artistic atmosphere throughout the entire video.\n"
            "- Image 3 (Ending Frame): This IS your final frame. The video MUST end on this exact visual state — same pose, same composition, same lighting. The entire animation must transition from Image 1 to Image 3, with Image 3 as the definitive ending.\n"
        )

    # 构建完整提示词
    parts = [image_ref_text, ""]

    # Video Action
    parts.append(f"VIDEO ACTION:\n{b_track.get('video_action', '')}")
    parts.append("")

    # Dialogue
    dialogues = b_track.get("dialogue", [])
    if dialogues and not (len(dialogues) == 1 and "No dialogue" in str(dialogues[0])):
        dialogue_text = "DIALOGUE:\n"
        for d in dialogues:
            if isinstance(d, dict):
                delivery = d.get("delivery", {})
                gender = delivery.get("gender", d.get("gender", ""))
                age = delivery.get("age", d.get("age", ""))
                tone = delivery.get("tone", d.get("tone_description", ""))
                volume = delivery.get("volume", d.get("volume", "normal"))
                speed = delivery.get("speed", d.get("speed", "normal"))
                dialogue_text += (
                    f"\"{d.get('character', '')}\" ({gender}, "
                    f"age {age}, {d.get('emotion', '')}, "
                    f"{volume}, {speed}, "
                    f"{tone}): \"{d.get('line', '')}\"\n"
                )
            else:
                dialogue_text += str(d) + "\n"
        parts.append(dialogue_text)
    else:
        parts.append("DIALOGUE:\nNo dialogue, pure visual storytelling with ambient sounds only")
    parts.append("")

    # Sound Design (tag-based, no volume/timing/duration)
    sound_effects = b_track.get("sound_effects", [])
    bgm = b_track.get("background_music", {})

    sound_text = "SOUND EFFECTS:\n"
    for se in sound_effects:
        if isinstance(se, dict):
            name = se.get('type', se.get('name', ''))
            desc = se.get('description', '')
            sound_text += f"- {name}: {desc}\n"
    parts.append(sound_text)

    if bgm and isinstance(bgm, dict):
        style = bgm.get('style_and_instruments', bgm.get('style', ''))
        instruments = ''
        if not bgm.get('style_and_instruments'):
            instruments = bgm.get('instruments', '')

        mood = bgm.get('mood_and_key', bgm.get('mood', ''))
        tempo = bgm.get('tempo', bgm.get('tempo_bpm', ''))

        bgm_text = (
            f"BACKGROUND MUSIC:\n"
            f"- Style: {style}\n"
        )
        if instruments:
            bgm_text += f"- Instruments: {instruments}\n"
        bgm_text += f"- Mood: {mood}\n"
        if tempo:
            bgm_text += f"- Tempo: {tempo}\n"
        if bgm.get('key') and not bgm.get('mood_and_key'):
            bgm_text += f"- Key: {bgm.get('key')}\n"
        if bgm.get('dynamic_layers'):
            bgm_text += f"- Dynamic Layers: {bgm.get('dynamic_layers')}\n"

        parts.append(bgm_text)

    # 末尾强化约束
    parts.append("")
    parts.append(
        "CRITICAL REMINDER: Your video MUST start exactly from Image 1 and MUST end exactly on the final Image. "
        "These are non-negotiable frame constraints. Failure to match these frames means the video is incorrect."
    )

    return "\n".join(parts)
