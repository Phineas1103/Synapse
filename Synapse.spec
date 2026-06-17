# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['D:\\Phineas\\Synapse\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('static', 'static'), ('tools', 'tools'), ('style_presets.json', '.'), ('style_modifiers.json', '.')],
    hiddenimports=['uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'lifespan', 'multipart', 'multipart.multipart', 'python_multipart', 'python_multipart.multipart', 'python_multipart.decoders', 'python_multipart.exceptions', 'api_server', 'llm_engine', 'image_engine', 'video_engine', 'ffmpeg_utils', 'project_manager', 'task_queue', 'config', 'license_client'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Synapse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\Phineas\\Synapse\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Synapse',
)
