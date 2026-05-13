"""
PyInstaller runtime hook — 預載 numpy 避免雙重初始化。

問題：numpy 2.x 在 PyInstaller bundle 中有時會被透過 numpy._core 跟 numpy.core
兩條路徑被載入兩次，觸發 "CPU dispatcher tracer already initlized" 錯誤。

修法：在主程式跑之前先 import numpy 並把新舊路徑 alias 起來。
"""
import os
import sys

os.environ.setdefault("FLAGS_use_mkldnn", "False")

# 預載 numpy + 它的 C extension
try:
    import numpy
    import numpy._core._multiarray_umath
    import numpy._core.multiarray
    # 同步 numpy.core 舊路徑（避免 paddle 走舊命名再 init 一次）
    sys.modules.setdefault("numpy.core", sys.modules["numpy._core"])
    sys.modules.setdefault("numpy.core._multiarray_umath", sys.modules["numpy._core._multiarray_umath"])
    sys.modules.setdefault("numpy.core.multiarray", sys.modules["numpy._core.multiarray"])
except Exception:
    pass

# 預載 paddle，這時 numpy 已經 cache 完成
try:
    import paddle  # noqa: F401
except Exception:
    pass
