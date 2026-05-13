"""PaddleOCR 引擎封裝 — 單例、多候選圖投票、視覺進度條交叉驗證。"""
from __future__ import annotations

import math
import os
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 必須在 import paddleocr 之前
os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import numpy as np
from PIL import Image

try:
    from paddleocr import PaddleOCR
    _IMPORT_ERROR = ""
except Exception as e:
    PaddleOCR = None  # type: ignore[assignment]
    _IMPORT_ERROR = f"{e}\n\n{traceback.format_exc()}"

from . import parser as ocr_parser
from .preprocess import (
    estimate_bar_percent,
    make_candidates,
    upscale_for_ocr,
)


@dataclass
class OCRResult:
    """一次 OCR 的完整結果 — 包含投票過程，UI 可以顯示。"""
    raw: Optional[int] = None
    pct: Optional[float] = None
    visual_pct: Optional[float] = None
    confidence: float = 0.0
    consensus: int = 0          # 共識票數
    total_votes: int = 0        # 總候選讀值數
    raw_text: str = ""
    source: str = ""            # 哪張候選圖中標
    error: str = ""             # 錯誤訊息

    @property
    def ok(self) -> bool:
        return self.raw is not None or self.pct is not None


@dataclass
class _EngineState:
    engine: Optional[object] = None
    error: str = ""
    device_label: str = "未初始化"


_STATE = _EngineState()


def _cpu_threads() -> int:
    n = os.cpu_count() or 4
    return max(2, min(8, n))


def _resource_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _bundled_model_dir(model_name: str) -> Optional[str]:
    bundled = _resource_dir() / "paddlex_models" / model_name
    if bundled.exists():
        return str(bundled)
    cached = Path.home() / ".paddlex" / "official_models" / model_name
    if cached.exists():
        return str(cached)
    return None


def device_status() -> str:
    return _STATE.device_label


def last_error() -> str:
    return _STATE.error


def init_engine(use_gpu: bool = False) -> bool:
    """顯式初始化引擎。首次呼叫會載模型，可能耗 3–8 秒。"""
    if _STATE.engine is not None:
        return True
    if PaddleOCR is None:
        _STATE.error = _IMPORT_ERROR or "PaddleOCR 未安裝"
        _STATE.device_label = "不可用"
        return False

    threads = _cpu_threads()
    kwargs = {
        "device": "gpu" if use_gpu else "cpu",
        "engine": "paddle_static",
        "enable_mkldnn": False,
        "cpu_threads": threads,
        "text_detection_model_name": "PP-OCRv5_mobile_det",
        "text_recognition_model_name": "en_PP-OCRv5_mobile_rec",
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "text_rec_score_thresh": 0.0,
        "text_det_thresh": 0.1,
        "text_det_box_thresh": 0.1,
        "text_det_unclip_ratio": 1.5,
        "text_det_limit_side_len": 1920,
        "text_det_limit_type": "max",
    }
    # 如果有 bundle 模型就指定路徑，避免首次啟動下載
    for key, name in (
        ("text_detection_model_dir", "PP-OCRv5_mobile_det"),
        ("text_recognition_model_dir", "en_PP-OCRv5_mobile_rec"),
    ):
        d = _bundled_model_dir(name)
        if d:
            kwargs[key] = d

    try:
        _STATE.engine = PaddleOCR(**kwargs)
        _STATE.error = ""
        _STATE.device_label = f"{'GPU' if use_gpu else 'CPU'}（PP-OCRv5，{threads} 執行緒）"
        return True
    except Exception as e:
        _STATE.error = f"{e}\n\n{traceback.format_exc()}"
        _STATE.device_label = "初始化失敗"
        return False


def _raw_predict(image: Image.Image) -> list[tuple[str, float]]:
    """單次 PaddleOCR 呼叫，回 [(text, confidence)]。"""
    if _STATE.engine is None and not init_engine():
        return []
    prepared = upscale_for_ocr(image)
    try:
        result = _STATE.engine.predict(np.array(prepared))  # type: ignore[union-attr]
    except Exception as e:
        _STATE.error = str(e)
        return []

    out: list[tuple[str, float]] = []
    for page in (result or []):
        try:
            data = dict(page)
        except Exception:
            continue
        ocr_res = data.get("overall_ocr_res") or data
        texts = list(ocr_res.get("rec_texts") or [])
        scores = list(ocr_res.get("rec_scores") or [])
        if len(texts) > 1:
            joined = "".join(str(t).strip() for t in texts if str(t).strip())
            if joined:
                conf = sum(float(s) for s in scores) / len(scores) if scores else 0.0
                out.append((joined, conf))
        for i, t in enumerate(texts):
            t = str(t).strip()
            if not t:
                continue
            c = float(scores[i]) if i < len(scores) else 0.0
            out.append((t, c))
    # 去重
    seen = set()
    unique = []
    for t, c in out:
        if t in seen:
            continue
        seen.add(t)
        unique.append((t, c))
    return unique


def recognize(image: Image.Image) -> OCRResult:
    """
    主入口：對單張 ROI 截圖做多候選圖投票辨識。
    流程：產生 N 張前處理變體 → 各跑 OCR → 收集所有 (raw, pct, conf) → 投票。
    """
    result = OCRResult()
    visual_pct = estimate_bar_percent(image)
    result.visual_pct = visual_pct

    candidates = make_candidates(image)
    votes: list[tuple[Optional[int], Optional[float], float, str, str]] = []
    # (raw, pct, conf, source_label, raw_text)

    for label, img in candidates:
        for text, conf in _raw_predict(img):
            raw, pct = ocr_parser.parse(text)
            if raw is None and pct is None:
                continue
            votes.append((raw, pct, conf, label, text))

    result.total_votes = len(votes)
    if not votes:
        if _STATE.error:
            result.error = _STATE.error
        elif not _STATE.engine:
            result.error = "OCR 引擎未啟動"
        else:
            result.error = "未讀到 EXP"
        return result

    # 投票策略：raw 出現次數最多者勝；同票取信心最高；再同票就跟 visual_pct 對齊
    raw_counter = Counter(v[0] for v in votes if v[0] is not None)
    if raw_counter:
        most_common_raw, count = raw_counter.most_common(1)[0]
        matching = [v for v in votes if v[0] == most_common_raw]
        # 信心最高的那筆裡面取
        best = max(matching, key=lambda v: v[2])
        result.raw = best[0]
        result.pct = best[1]
        result.confidence = best[2]
        result.consensus = count
        result.source = best[3]
        result.raw_text = best[4]
    else:
        # 只有百分比的情況
        best = max(votes, key=lambda v: v[2])
        result.pct = best[1]
        result.confidence = best[2]
        result.consensus = 1
        result.source = best[3]
        result.raw_text = best[4]

    # 用視覺百分比交叉驗證 OCR 百分比；明顯不一致就降信心
    if result.pct is not None and visual_pct is not None:
        if abs(result.pct - visual_pct) > 3.0:
            result.confidence *= 0.7

    return result
