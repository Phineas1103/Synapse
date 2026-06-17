import subprocess, os, sys, time, shutil

PROJ = r"D:\Phineas\Synapse"
WIN_PYTHON = os.environ.get("SYNAPSE_PYTHON", sys.executable)
DIST_DIR = os.path.join(PROJ, "dist", "Synapse")
CONFIG_FILE = os.path.join(DIST_DIR, "user_config.json")
LICENSE_CACHE_FILES = [
    os.path.join(DIST_DIR, "license_cache.json"),
    os.path.join(DIST_DIR, "_internal", "license_cache.json"),
]

# Backup config before build
config_backup = None
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config_backup = f.read()
    print("Config backed up ({} bytes)".format(len(config_backup)))
else:
    print("No config to backup")

print("Building...")
r = subprocess.run([
    WIN_PYTHON, "-m", "PyInstaller",
    "--onedir", "--noconfirm", "--noconsole",
    "--icon", os.path.join(PROJ, "icon.ico"),
    "--name", "Synapse",
    "--add-data", "static;static",
    "--add-data", "tools;tools",
    "--add-data", "style_presets.json;.",
    "--add-data", "style_modifiers.json;.",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "lifespan",
    "--hidden-import", "multipart",
    "--hidden-import", "multipart.multipart",
    "--hidden-import", "python_multipart",
    "--hidden-import", "python_multipart.multipart",
    "--hidden-import", "python_multipart.decoders",
    "--hidden-import", "python_multipart.exceptions",
    "--hidden-import", "api_server",
    "--hidden-import", "llm_engine",
    "--hidden-import", "image_engine",
    "--hidden-import", "video_engine",
    "--hidden-import", "ffmpeg_utils",
    "--hidden-import", "project_manager",
    "--hidden-import", "task_queue",
    "--hidden-import", "config",
    "--hidden-import", "license_client",
    os.path.join(PROJ, "main.py")
], capture_output=True, text=True, cwd=PROJ)

if r.returncode == 0:
    exe_path = os.path.join(DIST_DIR, "Synapse.exe")
    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    print("BUILD OK ({}MB)".format(int(size_mb)))
else:
    print("BUILD FAILED")
    print(r.stderr[-1000:] if r.stderr else "no stderr")
    sys.exit(1)

# Restore config after build
if config_backup:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(config_backup)
    print("Config restored")
else:
    print("No config to restore (first build)")

# License cache belongs to the local user machine. Never ship it.
for cache_file in LICENSE_CACHE_FILES:
    if os.path.exists(cache_file):
        os.remove(cache_file)
        print("Removed local license cache: {}".format(cache_file))

# Copy prompt_templates
subprocess.run(
    'xcopy /E /I /Y "{}" "{}"'.format(
        PROJ + "\\prompt_templates",
        DIST_DIR + "\\_internal\\prompt_templates"
    ),
    shell=True, capture_output=True
)
print("prompt_templates copied")

# Copy icon.ico
icon_src = os.path.join(PROJ, "icon.ico")
icon_dst = os.path.join(DIST_DIR, "icon.ico")
if os.path.exists(icon_src):
    shutil.copy2(icon_src, icon_dst)
    print("icon.ico copied")
else:
    print("WARNING: icon.ico not found")

if "--no-start" not in sys.argv:
    subprocess.run(
        'powershell -Command "Start-Process {}"'.format(DIST_DIR + "\\Synapse.exe"),
        shell=True, capture_output=True
    )
    print("Started")
else:
    print("Skipped start")
