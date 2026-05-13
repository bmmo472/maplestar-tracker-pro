# -*- mode: python ; coding: utf-8 -*-
"""GPU 版 spec — 同 CPU 版差在輸出名稱與檔案大小。"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

PROJECT_ROOT = Path(SPECPATH).parent
block_cipher = None

datas = [
    (str(PROJECT_ROOT / "data"), "data"),
    (str(PROJECT_ROOT / "assets"), "assets"),
]
paddlex_models_dir = PROJECT_ROOT / "paddlex_models"
if paddlex_models_dir.exists():
    datas.append((str(paddlex_models_dir), "paddlex_models"))

try:
    datas += collect_data_files("setuptools", include_py_files=False)
except Exception as e:
    print(f"[warn] setuptools data collect failed: {e}", file=sys.stderr)

hiddenimports = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
    "paddleocr", "paddle", "paddle.inference", "paddle.base",
    "scipy.special", "scipy.special.cython_special",
    "skimage.io", "skimage.color", "skimage.morphology",
    "skimage.transform", "skimage.exposure", "skimage.measure",
    "shapely.geometry", "pyclipper", "imghdr",
]

excludes = ["tkinter", "matplotlib", "notebook", "jupyter", "pytest", "tornado", "IPython"]

collected_datas, collected_binaries, collected_hiddenimports = [], [], []
for pkg in ("paddleocr", "paddle", "paddlex", "numpy"):
    try:
        d, b, h = collect_all(pkg)
        collected_datas += d
        collected_binaries += b
        collected_hiddenimports += h
    except Exception as e:
        print(f"[warn] collect_all({pkg!r}) failed: {e}", file=sys.stderr)

for pkg in ("paddleocr", "paddlepaddle-gpu", "paddlex",
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
    runtime_hooks=[str(PROJECT_ROOT / "build" / "runtime_hook.py")],
    excludes=excludes,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MapleStarTrackerPro_GPU",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    target_arch=None,
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
    name="MapleStarTrackerPro_GPU",
)
