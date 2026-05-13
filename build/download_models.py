"""預先下載 PaddleOCR 模型 — 給 build script 呼叫用。"""
import os
import sys

os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

use_gpu = "--gpu" in sys.argv

try:
    import paddle
    device = "gpu" if (use_gpu and paddle.is_compiled_with_cuda()) else "cpu"
except ImportError:
    device = "cpu"

print(f"[download_models] device = {device}")

from paddleocr import PaddleOCR
import numpy as np

engine = PaddleOCR(
    device=device,
    engine="paddle_static",
    enable_mkldnn=False,
    text_detection_model_name="PP-OCRv5_mobile_det",
    text_recognition_model_name="en_PP-OCRv5_mobile_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
engine.predict(np.zeros((128, 256, 3), dtype=np.uint8))
print("[download_models] 完成")
