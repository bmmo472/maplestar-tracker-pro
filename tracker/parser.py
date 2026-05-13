"""OCR 文字 → (raw, pct) 解析 — 從原作者的 parse_ocr_text 簡化整理。"""
from __future__ import annotations

import re
from typing import Optional

# 常見 OCR 把 [ ] 看成別的字元，先全部標準化
_NORMALIZE_MAP = {
    "{": "[", "}": "]", "（": "[", "）": "]", "〔": "[", "〕": "]",
    "【": "[", "】": "]", "「": "[", "」": "]",
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "l": "1", "I": "1", "|": "1",
    "S": "5", "s": "5",
    "B": "8",
    "，": ",", "。": ".",
    # 注意：不移除空格 — 空格是 raw 跟 pct 的重要分隔符
}

# raw 跟 pct 之間至少 1 個非數字字元（避免 "9,924,083 31.97%" 被當成連續數字）
_EXP_RE = re.compile(r"([\d,]+)\D{1,8}(\d{1,3}\.\d{1,2})\s*%?")
_PCT_RE = re.compile(r"(\d{1,3}\.\d{1,2})\s*%?")


def normalize(text: str) -> str:
    if not text:
        return ""
    return "".join(_NORMALIZE_MAP.get(ch, ch) for ch in text)


def parse(text: str) -> tuple[Optional[int], Optional[float]]:
    """從 OCR 文字抓出 (raw_exp, pct)。任一抓不到回 None。"""
    if not text:
        return None, None
    t = normalize(text)
    m = _EXP_RE.search(t)
    if m:
        raw_str, pct_str = m.groups()
        try:
            raw = int(raw_str.replace(",", ""))
            pct = float(pct_str)
            if 0 <= pct <= 100 and raw >= 0:
                return raw, pct
        except ValueError:
            pass
    # 退一步：只抓百分比
    m2 = _PCT_RE.search(t)
    if m2:
        try:
            pct = float(m2.group(1))
            if 0 <= pct <= 100:
                return None, pct
        except ValueError:
            pass
    return None, None
