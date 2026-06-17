import argparse
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

PROJ = r"D:\Phineas\Synapse"
WIN_PYTHON = os.environ.get("SYNAPSE_PYTHON", sys.executable)
APP_NAME = "Synapse"
VERSION = "1.0.0"
INSTALLER_NAME = "Synapse_Setup_v{}.exe".format(VERSION)
INSTALLER_PATH = os.path.join(PROJ, "installer_output", INSTALLER_NAME)
RELEASE_DIR = os.path.join(PROJ, "release", "web-download")
DOWNLOADS_DIR = os.path.join(RELEASE_DIR, "downloads")
DEFAULT_BASE_URL = "http://124.221.179.140:8788/downloads/synapse/"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def build_installer():
    subprocess.check_call(
        [WIN_PYTHON, os.path.join(PROJ, "build_installer.py"), "--skip-web"],
        cwd=PROJ,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-installer", action="store_true")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SYNAPSE_DOWNLOAD_BASE_URL", DEFAULT_BASE_URL),
        help="Public URL where release/web-download will be hosted.",
    )
    args = parser.parse_args()

    if not args.skip_installer:
        build_installer()

    if not os.path.exists(INSTALLER_PATH):
        raise FileNotFoundError(INSTALLER_PATH)

    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

    release_installer = os.path.join(DOWNLOADS_DIR, INSTALLER_NAME)
    shutil.copy2(INSTALLER_PATH, release_installer)

    size = os.path.getsize(release_installer)
    digest = sha256_file(release_installer)
    generated_at = datetime.now().isoformat(timespec="seconds")
    base_url = args.base_url.rstrip("/") + "/"
    download_url = base_url + "downloads/" + INSTALLER_NAME

    latest = {
        "app": APP_NAME,
        "version": VERSION,
        "filename": INSTALLER_NAME,
        "size": size,
        "sha256": digest,
        "download_url": download_url,
        "generated_at": generated_at,
    }
    write_text(
        os.path.join(RELEASE_DIR, "latest.json"),
        json.dumps(latest, ensure_ascii=False, indent=2),
    )

    size_mb = size / 1024 / 1024
    index_html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Synapse 下载</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #f7f3ff;
      background: #07050d;
    }}
    main {{
      width: min(520px, calc(100vw - 40px));
      padding: 36px;
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 18px;
      background: linear-gradient(145deg, rgba(44, 31, 68, .82), rgba(14, 13, 24, .95));
      box-shadow: 0 24px 80px rgba(0,0,0,.45);
    }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    p {{ color: #c9c0d8; line-height: 1.7; }}
    a.button {{
      display: block;
      margin: 26px 0 18px;
      padding: 16px 18px;
      border-radius: 12px;
      color: #fff;
      text-align: center;
      text-decoration: none;
      font-weight: 700;
      background: linear-gradient(135deg, #6f86e8, #8b5ac6);
    }}
    .meta {{
      font-size: 13px;
      color: #9e94ad;
      word-break: break-all;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Synapse</h1>
    <p>AI 漫剧创作平台 Windows 安装包。下载后双击安装，可选择安装路径，并默认创建桌面快捷方式。</p>
    <a class="button" href="downloads/{filename}">下载安装包</a>
    <div class="meta">版本：{version}</div>
    <div class="meta">大小：{size_mb:.1f} MB</div>
    <div class="meta">SHA256：{sha256}</div>
    <div class="meta">生成时间：{generated_at}</div>
  </main>
</body>
</html>
""".format(
        filename=html.escape(INSTALLER_NAME),
        version=html.escape(VERSION),
        size_mb=size_mb,
        sha256=html.escape(digest),
        generated_at=html.escape(generated_at),
    )
    write_text(os.path.join(RELEASE_DIR, "index.html"), index_html)

    readme = """# Synapse 下载页发布目录

把本目录 `release/web-download` 里的全部内容上传到服务器静态目录即可。

推荐服务器路径：

`/downloads/synapse/`

对应下载页：

`http://124.221.179.140:8788/downloads/synapse/index.html`

直接安装包：

`http://124.221.179.140:8788/downloads/synapse/downloads/{filename}`

本目录包含：

- `index.html`：用户打开的下载页
- `latest.json`：版本、文件大小、SHA256 和下载地址
- `downloads/{filename}`：完整 Windows 安装包
""".format(filename=INSTALLER_NAME)
    write_text(os.path.join(RELEASE_DIR, "README.md"), readme)

    print("Web release OK: {}".format(RELEASE_DIR))
    print("Download page: {}".format(base_url + "index.html"))
    print("Installer URL: {}".format(download_url))


if __name__ == "__main__":
    main()
