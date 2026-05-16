"""
PyInstaller runtime hook

主要工作：
1. 設定 paddle 預設關閉 MKLDNN（避免某些環境 crash）
2. 修正 PyInstaller frozen 模式下 DLL 子目錄路徑問題
   （特別是 paddle GPU 版的 phi.dll / libpaddle.dll 在 paddle\libs\ 子目錄）
3. 處理 numpy 2.x 跟 PyInstaller bundle 的 numpy._core / numpy.core alias
4. 觸發 paddle 早期 init 避免後續匯入順序問題
"""
import os
import sys

os.environ.setdefault("FLAGS_use_mkldnn", "False")

# === DLL 路徑修正（GPU build 必須）===
# PyInstaller frozen 模式下 Windows 預設只在 _MEIPASS 根目錄找 DLL，
# 但 paddle GPU 的 native libs 放在 paddle\libs\ 之類子目錄，
# 不加進去會 access violation crash。
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    base = sys._MEIPASS
    dll_dirs = [base]
    for root, _, files in os.walk(base):
        if any(f.endswith(('.dll', '.pyd')) for f in files):
            if root not in dll_dirs:
                dll_dirs.append(root)
    # 加進 PATH 環境變數
    os.environ['PATH'] = os.pathsep.join(dll_dirs) + os.pathsep + os.environ.get('PATH', '')
    # Windows 8+ 明確 AddDllDirectory（更可靠的 DLL 載入機制）
    if hasattr(os, 'add_dll_directory'):
        for d in dll_dirs:
            try:
                os.add_dll_directory(d)
            except (OSError, FileNotFoundError):
                pass

# === numpy + paddle C extension 預載 ===
try:
    import numpy
    import numpy._core._multiarray_umath
    import numpy._core.multiarray
    # 提供 numpy.core alias 給 paddle 舊版相容
    sys.modules.setdefault("numpy.core", sys.modules["numpy._core"])
    sys.modules.setdefault("numpy.core._multiarray_umath", sys.modules["numpy._core._multiarray_umath"])
    sys.modules.setdefault("numpy.core.multiarray", sys.modules["numpy._core.multiarray"])
except Exception:
    pass

# === paddle 觸發 numpy 損傷 cache 避免 ===
try:
    import paddle  # noqa: F401
except Exception:
    pass
