# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — Windows CPU build (onedir mode)

整合了完整 fix 集：
- collect_all paddle + paddleocr + paddlex + numpy
- copy_metadata 給 ocr-core deps（讓 paddlex 認得 deps）
- setuptools vendor data（Lorem ipsum.txt 等）
- runtime hook 預載 numpy 避免 dispatcher tracer 衝突
- assets/ 跟 data/ 都進 bundle

執行：
    pyinstaller build/tracker_windows.spec --clean

輸出：dist/MapleStarTrackerPro/
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

PROJECT_ROOT = Path(SPECPATH).parent
block_cipher = None


# === 資料檔（包含 icon、QR Code 等 assets）===
datas = [
    (str(PROJECT_ROOT / "data"), "data"),
    (str(PROJECT_ROOT / "assets"), "assets"),
]
paddlex_models_dir = PROJECT_ROOT / "paddlex_models"
if paddlex_models_dir.exists():
    datas.append((str(paddlex_models_dir), "paddlex_models"))

# setuptools 的 vendor 資料（paddle 載入時需要 Lorem ipsum.txt 等）
try:
    datas += collect_data_files("setuptools", include_py_files=False)
except Exception as e:
    print(f"[warn] setuptools data collect failed: {e}", file=sys.stderr)


# === Hidden imports ===
hiddenimports = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "paddleocr", "paddle", "paddle.inference", "paddle.base",
    "scipy.special", "scipy.special.cython_special",
    "skimage.io", "skimage.color", "skimage.morphology",
    "skimage.transform", "skimage.exposure", "skimage.measure",
    "shapely.geometry", "pyclipper", "imghdr",
]


# === 排除（瘦身）===
excludes = [
    "tkinter", "matplotlib", "notebook", "jupyter",
    "pytest", "tornado", "IPython",
]


# === collect_all paddle 生態系 + numpy ===
collected_datas, collected_binaries, collected_hiddenimports = [], [], []
for pkg in ("paddleocr", "paddle", "paddlex", "numpy"):
    try:
        d, b, h = collect_all(pkg)
        collected_datas += d
        collected_binaries += b
        collected_hiddenimports += h
    except Exception as e:
        print(f"[warn] collect_all({pkg!r}) failed: {e}", file=sys.stderr)

# === copy_metadata — paddlex 用 importlib.metadata.version() 檢查 deps ===
for pkg in ("paddleocr", "paddlepaddle", "paddlex",
            "imagesize", "opencv-contrib-python", "pyclipper",
            "pypdfium2", "python-bidi", "shapely", "numpy", "Pillow"):
    try:
        collected_datas += copy_metadata(pkg)
    except Exception as e:
        print(f"[warn] copy_metadata({pkg!r}) failed: {e}", file=sys.stderr)


a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=collected_binaries,
    datas=datas + collected_datas,
    hiddenimports=hiddenimports + collected_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PROJECT_ROOT / "build" / "runtime_hook.py")],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir 模式
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MapleStarTrackerPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT_ROOT / "assets" / "app_icon.ico")
        if (PROJECT_ROOT / "assets" / "app_icon.ico").exists() else None,
    version=str(PROJECT_ROOT / "build" / "version_info.txt")
        if (PROJECT_ROOT / "build" / "version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MapleStarTrackerPro",
)
