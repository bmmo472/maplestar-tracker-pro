"""影像前處理 — numpy 向量化版（比原作者的 pixel loop 快 10–50 倍）。"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PIL import Image


# 楓星 EXP 條綠色判斷：g 明顯大於 b、紅綠相近、整體偏亮
def _green_mask(arr: np.ndarray, strict: bool = True) -> np.ndarray:
    r = arr[..., 0].astype(np.int16)
    g = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)
    bright = np.maximum.reduce([r, g, b])
    if strict:
        return (g > 120) & (r > 65) & (b < 150) & (g >= r) & ((g - b) > 35) & (bright > 130)
    return (g > 105) & (r > 55) & (b < 165) & (g >= r) & ((g - b) > 24) & (bright > 105)


def neutralize_green_bar(image: Image.Image) -> Image.Image:
    """把綠色進度條塗成固定深灰，讓白字 OCR 背景穩定。"""
    rgb = image.convert("RGB")
    if rgb.width < 20 or rgb.height < 8:
        return rgb
    arr = np.array(rgb)
    strong = _green_mask(arr, strict=True)
    soft = _green_mask(arr, strict=False)

    # 判斷進度條的 y 範圍：強綠色密集的列
    h, w, _ = arr.shape
    row_hits = strong.sum(axis=1)
    green_rows = np.where(row_hits >= max(3, int(w * 0.08)))[0]
    if green_rows.size == 0:
        return rgb

    y0 = max(0, int(green_rows.min()) - 1)
    y1 = min(h, int(green_rows.max()) + 2)
    band = np.zeros_like(strong)
    band[y0:y1, :] = True

    # 白字判斷：很亮 + 色彩不分散
    bright = arr.max(axis=2).astype(np.int16)
    spread = bright - arr.min(axis=2).astype(np.int16)
    text_like = (bright > 150) & (spread < 88) & (~strong)

    mask = band & soft & (~text_like)
    if not mask.any():
        return rgb
    out = arr.copy()
    out[mask] = (46, 49, 52)  # 固定深灰
    return Image.fromarray(out, "RGB")


def estimate_bar_percent(image: Image.Image) -> Optional[float]:
    """掃綠色像素估算進度條 % — 作為 OCR 之外的第二訊號來源。"""
    rgb = image.convert("RGB")
    w, h = rgb.size
    if w < 80 or h < 8:
        return None
    arr = np.array(rgb)
    y_lo = max(0, int(h * 0.18))
    y_hi = min(h, int(h * 0.82))
    if y_hi - y_lo < 2:
        return None
    band = arr[y_lo:y_hi]
    green = _green_mask(band, strict=True)
    col_hits = green.sum(axis=0)
    threshold = max(2, int((y_hi - y_lo) * 0.30))

    cols_with_green = np.where(col_hits >= threshold)[0]
    if cols_with_green.size < 2:
        return None
    left = int(cols_with_green.min())

    # 右邊界：找灰色 or 綠色像素的最右一行（避開百分比文字）
    r = band[..., 0].astype(np.int16)
    g = band[..., 1].astype(np.int16)
    b = band[..., 2].astype(np.int16)
    gray = (
        (r >= 45) & (r <= 150) & (g >= 45) & (g <= 150) & (b >= 45) & (b <= 150)
        & (np.abs(r - g) < 35) & (np.abs(g - b) < 35)
    )
    soft_green = _green_mask(band, strict=False)
    bar_cols = np.where((gray | soft_green).sum(axis=0) >= threshold)[0]
    right = int(bar_cols.max()) if bar_cols.size else (w - 1)

    width = right - left + 1
    if width < 80:
        return None

    filled = cols_with_green[(cols_with_green >= left) & (cols_with_green <= right)]
    if filled.size == 0:
        return None
    filled_right = int(filled.max())
    pct = (filled_right - left + 1) / width * 100
    return float(pct) if 0 <= pct <= 100 else None


def upscale_for_ocr(image: Image.Image, min_height: int = 96, max_factor: int = 4) -> Image.Image:
    """字太小時等比放大 — PaddleOCR 對 < 96px 字高辨識率掉得快。"""
    if image.height <= 0 or image.height >= min_height:
        return image
    scale = min(max_factor, max(1, math.ceil(min_height / image.height)))
    if scale <= 1:
        return image
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)


def make_candidates(image: Image.Image) -> list[tuple[str, Image.Image]]:
    """產生多張前處理變體 — 給多候選圖投票用。"""
    rgb = image.convert("RGB")
    candidates = [("原圖", rgb)]
    processed = neutralize_green_bar(rgb)
    if processed.tobytes() != rgb.tobytes():
        candidates.append(("去綠條", processed))
    if rgb.height < 96:
        candidates.append(("放大2x", rgb.resize((rgb.width * 2, rgb.height * 2), Image.LANCZOS)))
    return candidates
