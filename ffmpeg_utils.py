# -*- coding: utf-8 -*-
"""Synapse — FFmpeg 工具（拼接+字幕+转码）"""

import os
import subprocess
import json
import config
from datetime import datetime as _dt

def _debug_log(msg):
    """写调试日志到文件（PyInstaller noconsole下print丢失）"""
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{_dt.now().strftime('%H:%M:%S')}] {msg}\n")
    except:
        pass

# ════════════════════════════════════════
#  渲染管线预设（防绕过：后端强制覆盖）
# ════════════════════════════════════════

RENDER_PRESETS = {
    "draft": {
        "name": "快速预览",
        "desc": "速度优先，适合快速检查内容",
        "codec": "libx264",
        "preset_speed": "ultrafast",
        "crf": "23",
        "resolution": "1280:720",
        "fps": 24,
        "audio_bitrate": "128k",
        "audio_sample_rate": 44100,
    },
    "standard": {
        "name": "标准品质",
        "desc": "画质与速度平衡，适合网络发布",
        "codec": "libx264",
        "preset_speed": "medium",
        "crf": "18",
        "resolution": "1920:1080",
        "fps": 30,
        "audio_bitrate": "192k",
        "audio_sample_rate": 44100,
    },
    "professional": {
        "name": "专业品质",
        "desc": "商业级画质，编码时间较长",
        "codec": "libx265",
        "preset_speed": "slow",
        "crf": "15",
        "resolution": "1920:1080",
        "fps": 30,
        "audio_bitrate": "256k",
        "audio_sample_rate": 48000,
    },
}

ALLOWED_PRESETS = set(RENDER_PRESETS.keys())

def get_render_preset(preset_name="standard"):
    """获取渲染预设参数。无效名称强制回退standard（防绕过）"""
    if preset_name not in ALLOWED_PRESETS:
        return RENDER_PRESETS["standard"]
    return dict(RENDER_PRESETS[preset_name])



def get_video_info(video_path):
    """获取视频信息"""
    cmd = [
        config.FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout)
    except Exception:
        return None


def normalize_clip_video(video_path, output_path=None, preset_name="standard"):
    """
    规范化单个clip视频（下载后立即调用）。
    解决两个问题：
    1. VFR→CFR：Grok生成的AI视频是可变帧率，时间戳不均匀
    2. 视频轨短于音频轨：用tpad克隆最后一帧填补，-shortest对齐音频
    """
    if output_path is None:
        output_path = video_path  # 覆盖原文件
    preset = get_render_preset(preset_name)
    fps = str(preset["fps"])

    # 临时输出文件（避免覆盖输入）
    tmp_path = output_path + ".norm.mp4"

    video_filter = f"fps={fps},tpad=stop_mode=clone:stop_duration=60"

    cmd = [
        config.FFMPEG_PATH, "-y",
        "-i", video_path,
        "-vf", video_filter,
        "-fps_mode", "cfr",
        "-c:v", preset["codec"],
        "-preset", "fast",
        "-crf", preset["crf"],
        "-c:a", "aac",
        "-b:a", preset["audio_bitrate"],
        "-ar", str(preset["audio_sample_rate"]),
        "-shortest",
        "-movflags", "+faststart",
        tmp_path,
    ]
    _debug_log(f"[NORMALIZE] cmd: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        _debug_log(f"[NORMALIZE] FAILED: {result.stderr[-300:]}")
        # 失败时不覆盖原文件，静默返回原路径
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return video_path

    # 替换原文件
    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(tmp_path, output_path)
    return output_path


def concat_videos(video_paths, output_path, transition="none", transition_duration=0.5, preset_name="standard"):
    _debug_log(f"[CONCAT] called: {len(video_paths)} clips, transition={transition}, td={transition_duration}, preset={preset_name}")
    _debug_log(f"[CONCAT] output={output_path}")
    """
    拼接视频片段。
    video_paths: list of str（视频文件路径，按顺序）
    output_path: 输出文件路径
    transition: "none" / "fade" / "fadeblack" / "fadewhite" / "dissolve" / "wipeleft" / "slideright"
    transition_duration: 转场时长（秒）
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    preset = get_render_preset(preset_name)
    vcodec = preset["codec"]
    pspeed = preset["preset_speed"]
    crf = preset["crf"]
    abitrate = preset["audio_bitrate"]
    fps = str(preset["fps"])

    if not video_paths:
        raise ValueError("没有视频文件")

    if len(video_paths) == 1:
        import shutil
        _debug_log(f"[CONCAT] single video, copying: {video_paths[0]}")
        shutil.copy2(video_paths[0], output_path)
        return output_path

    # 创建文件列表
    list_path = output_path + ".filelist.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for vp in video_paths:
            # FFmpeg concat 需要转义路径中的特殊字符
            escaped = vp.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    if transition == "none":
        # 两步法：先零拷贝拼接（保留原始时长），再重编码应用渲染预设
        # 直接 concat demuxer + 重编码会导致 VFR 视频丢帧丢时长
        temp_concat = output_path + ".tmp_concat.mp4"
        cmd_copy = [
            config.FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-movflags", "+faststart",
            temp_concat,
        ]
        result_copy = subprocess.run(cmd_copy, capture_output=True, text=True, timeout=600)
        if result_copy.returncode != 0:
            raise RuntimeError(f"FFmpeg concat copy 失败: {result_copy.stderr[-500:]}")

        # 第二步：重编码应用渲染预设
        cmd = [
            config.FFMPEG_PATH, "-y", "-i", temp_concat,
            "-c:v", vcodec, "-preset", pspeed, "-crf", crf,
            "-c:a", "aac", "-b:a", abitrate,
            "-movflags", "+faststart",
            output_path,
        ]
        _debug_log(f"[CONCAT] step1 done: {temp_concat}")
        # 验证step1时长
        try:
            _p = subprocess.run([config.FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", temp_concat], capture_output=True, text=True, timeout=30)
            _debug_log(f"[CONCAT] step1 duration: {_p.stdout.strip()}s")
        except Exception as _e:
            _debug_log(f"[CONCAT] step1 probe failed: {_e}")
        _debug_log(f"[CONCAT] step2 cmd: {' '.join(cmd)}")
        _debug_log(f"[CONCAT] preset={preset_name}, resolution={preset['resolution']}, fps={fps}")
    else:
        # 带淡入淡出转场的拼接（使用xfade滤镜）
        # 先统一参数再拼接
        normalized = []
        durations = []  # 收集每个clip的真实时长，避免_build_xfade_chain重新probe
        for i, vp in enumerate(video_paths):
            norm_path = f"{output_path}.norm_{i}.mp4"
            fps_val = preset["fps"]

            # 强制CFR + 分辨率对齐 + 尾部补帧防xfade饿死
            norm_filter = (
                f"fps={fps_val},"
                f"scale={preset['resolution']}:force_original_aspect_ratio=decrease,"
                f"pad={preset['resolution']}:(ow-iw)/2:(oh-ih)/2,"
                f"tpad=stop_mode=clone:stop_duration=0.5"
            )

            cmd_norm = [
                config.FFMPEG_PATH, "-y", "-i", vp,
                "-map", "0:v:0", "-map", "0:a:0",
                "-vf", norm_filter,
                "-c:v", vcodec, "-preset", pspeed, "-crf", crf,
                "-af", "apad",
                "-c:a", "aac", "-b:a", abitrate, "-ar", str(preset["audio_sample_rate"]), "-ac", "2",
                "-video_track_timescale", "90000",
                "-vsync", "cfr",
                "-shortest",
                norm_path,
            ]
            _debug_log(f"[CONCAT] normalizing clip {i}: {vp} -> {norm_path}")
            subprocess.run(cmd_norm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
            if os.path.exists(norm_path):
                try:
                    _np = subprocess.run([config.FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", norm_path], capture_output=True, text=True, timeout=30)
                    _dur = float(_np.stdout.strip())
                    durations.append(_dur)
                    _debug_log(f"[CONCAT] norm_{i} duration: {_dur}s")
                except:
                    durations.append(5.0)
            else:
                _debug_log(f"[CONCAT] norm_{i} FAILED: file not created")
                durations.append(5.0)
            normalized.append(norm_path)

        # 使用xfade拼接
        cmd = [config.FFMPEG_PATH, "-y"]
        for np in normalized:
            cmd.extend(["-i", np])

        if len(normalized) == 2:
            # 计算偏移量（用已知时长，避免重新probe失败）
            dur0 = durations[0] if durations else 5.0
            offset = max(0, dur0 - transition_duration)
            cmd.extend([
                "-filter_complex",
                f"[0:v][1:v]xfade=transition={transition}:duration={transition_duration}:offset={offset:.2f}[v];"
                f"[0:a][1:a]acrossfade=d={transition_duration}[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", vcodec, "-preset", pspeed, "-crf", crf,
                "-movflags", "+faststart",
                output_path,
            ])
        else:
            # 多片段xfade链式拼接
            _chain = _build_xfade_chain(normalized, transition_duration, transition, durations=durations)
            _debug_log(f"[CONCAT] xfade chain: {_chain[:200]}...")
            cmd.extend([
                "-filter_complex", _chain,
                "-map", f"[v{len(normalized)-1}]", "-map", f"[a{len(normalized)-1}]",
                "-c:v", vcodec, "-preset", pspeed, "-crf", crf,
                "-movflags", "+faststart",
                output_path,
            ])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800
        )
        _debug_log(f"[CONCAT] ffmpeg exit={result.returncode}")
        if result.returncode != 0:
            _debug_log(f"[CONCAT] ffmpeg stderr: {result.stderr[-500:]}")
            raise RuntimeError(f"FFmpeg concat 失败: {result.stderr[-500:]}")
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)
        # 清理临时文件
        temp_concat = output_path + ".tmp_concat.mp4"
        if os.path.exists(temp_concat):
            os.remove(temp_concat)
        for np in normalized if transition != "none" else []:
            if os.path.exists(np):
                os.remove(np)

    return output_path


def burn_subtitles(video_path, subtitle_data, output_path, font_size=24,
                   font_color="#ffffff", outline_color="black", outline_width=2,
                   position="bottom", font_name="Microsoft YaHei", preset_name="standard"):
    """
    烧录字幕到视频。
    subtitle_data: list of dict {start, end, text, character}
    font_color: #RRGGBB hex color string
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    preset = get_render_preset(preset_name)

    # 生成 .srt 文件
    srt_path = output_path + ".srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, sub in enumerate(subtitle_data, 1):
            start_ts = _seconds_to_srt_time(sub["start"])
            end_ts = _seconds_to_srt_time(sub["end"])
            text = sub["text"]
            f.write(f"{i}\n{start_ts} --> {end_ts}\n{text}\n\n")

    # 构建字幕滤镜
    if position == "bottom":
        margin_v = 30
        position_expr = f"MarginV={margin_v}"
    elif position == "top":
        margin_v = 30
        position_expr = f"MarginV={margin_v},Alignment=8"
    else:
        position_expr = ""

    # 颜色转换: #RRGGBB → ASS &H00BBGGRR (注意BGR顺序)
    ass_color = _hex_to_ass_color(font_color)

    # 使用subtitles滤镜
    srt_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
    subtitle_filter = (
        f"subtitles='{srt_escaped}'"
        f":force_style='FontSize={font_size},"
        f"PrimaryColour={ass_color},"
        f"OutlineColour=&H00000000,"
        f"Outline={outline_width},"
        f"FontName={font_name},"
        f"{position_expr}'"
    )

    cmd = [
        config.FFMPEG_PATH, "-y", "-i", video_path,
        "-vf", subtitle_filter,
        "-c:v", preset["codec"], "-preset", preset["preset_speed"], "-crf", preset["crf"],
        "-c:a", "aac", "-b:a", preset["audio_bitrate"],
        "-movflags", "+faststart",
        output_path,
    ]
    _debug_log(f"[SUBTITLE] cmd: {' '.join(cmd[:10])}...")
    _debug_log(f"[SUBTITLE] preset={preset_name}, resolution={preset['resolution']}, fps={preset['fps']}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0:
        raise RuntimeError(f"字幕烧录失败: {result.stderr[-500:]}")

    return output_path


def _hex_to_ass_color(hex_color):
    """将 #RRGGBB 转为 ASS 格式 &H00BBGGRR"""
    h = hex_color.lstrip('#')
    if len(h) != 6:
        return "&H00FFFFFF"  # 默认白色
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def normalize_video(input_path, output_path, width=1920, height=1080, fps=30):
    """统一视频参数（分辨率、帧率）"""
    cmd = [
        config.FFMPEG_PATH, "-y", "-i", input_path,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"视频标准化失败: {result.stderr[-300:]}")
    return output_path


def encode_final(input_path, output_path, resolution="1080p", fps=30,
                 codec="h264", bitrate="high"):
    """
    最终编码输出。
    resolution: "720p" / "1080p" / "4k"
    codec: "h264" / "h265"
    bitrate: "standard" / "high" / "custom"
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    res_map = {"720p": "1280:720", "1080p": "1920:1080", "4k": "3840:2160"}
    res = res_map.get(resolution, "1920:1080")

    crf_map = {"standard": "23", "high": "18", "ultra": "15"}
    crf = crf_map.get(bitrate, "18")

    codec_map = {"h264": "libx264", "h265": "libx265"}
    vcodec = codec_map.get(codec, "libx264")

    w, h = res.split(":")

    cmd = [
        config.FFMPEG_PATH, "-y", "-i", input_path,
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2",
        "-r", str(fps),
        "-c:v", vcodec, "-preset", "medium", "-crf", crf,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"最终编码失败: {result.stderr[-500:]}")
    return output_path


def check_ffmpeg():
    """检查 FFmpeg 是否可用"""
    try:
        result = subprocess.run([config.FFMPEG_PATH, "-version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


# ── 内部工具函数 ──


def _seconds_to_srt_time(seconds):
    """秒数转 SRT 时间格式 (HH:MM:SS,mmm)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_xfade_chain(normalized_paths, duration, transition="fade", durations=None):
    """构建多片段xfade滤镜链。修正级联offset计算：动态追踪合成视频总长度"""
    n = len(normalized_paths)
    if n < 2:
        return ""

    offsets = []
    v_length = 0  # 追踪当前累积的视频流总时长

    for i, p in enumerate(normalized_paths):
        dur = durations[i] if (durations and i < len(durations)) else 5.0
        _debug_log(f"[XFADE] clip {i}: dur={dur:.3f}s, v_length_before={v_length:.3f}s")
        if i == 0:
            v_length = dur
        else:
            # offset = 当前合成视频总长 - 转场时长
            offset = max(0, v_length - duration)
            offsets.append(offset)
            # 更新累积长度：新clip加入后，扣除重叠部分
            v_length = offset + dur

    filters = []
    # 第一对
    filters.append(
        f"[0:v][1:v]xfade=transition={transition}:duration={duration}:offset={offsets[0]:.2f}[v1]"
    )
    filters.append(
        f"[0:a][1:a]acrossfade=d={duration}[a1]"
    )

    for i in range(2, n):
        prev_v = f"v{i-1}"
        prev_a = f"a{i-1}"
        filters.append(
            f"[{prev_v}][{i}:v]xfade=transition={transition}:duration={duration}:offset={offsets[i-1]:.2f}[v{i}]"
        )
        filters.append(
            f"[{prev_a}][{i}:a]acrossfade=d={duration}[a{i}]"
        )

    return ";".join(filters)
