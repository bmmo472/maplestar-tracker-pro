"""
OCR 結果修正 pipeline。

原作者把 8 個 corrector 寫成 method 串接呼叫，順序敏感、互相蓋來蓋去、
還有 3 個函式被重複呼叫 2–3 次。

這裡重構成「pipeline pattern」：每個 corrector 是純函式，
拿 (raw, pct) 進來，回新的 (raw, pct, reason)。失敗回 None，原值繼續走。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Callable, Optional

from . import exp_table


CONFUSED_DIGITS = "689"
MAX_OVER_CAP_RATIO = 1.02
MIN_DELTA = 50_000
PROGRESS_TOLERANCE_RATIO = 0.025


@dataclass
class Context:
    """corrector 共用的上下文。"""
    manual_level: Optional[int] = None
    last_raw: Optional[int] = None
    last_pct: Optional[float] = None
    visual_pct: Optional[float] = None

    @property
    def reference_cap(self) -> Optional[int]:
        if self.manual_level is None:
            return None
        return exp_table.cap_for_level(self.manual_level)


# Corrector 介面：(raw, pct, ctx) -> (raw', pct', reason) or None
Corrector = Callable[[int, Optional[float], Context], Optional[tuple[int, Optional[float], str]]]


def _expected_raw(ctx: Context, pct: float) -> Optional[float]:
    cap = ctx.reference_cap
    if cap is None or pct is None:
        return None
    return cap * pct / 100


def correct_confused_689(raw: int, pct: Optional[float], ctx: Context):
    """6/8/9 混淆修正 — 用 manual_level + pct 找最合理的位數翻轉。"""
    if pct is None or ctx.reference_cap is None:
        return None
    cap = ctx.reference_cap
    expected = _expected_raw(ctx, pct)
    if expected is None:
        return None
    tolerance = max(MIN_DELTA, cap * PROGRESS_TOLERANCE_RATIO)
    current_distance = abs(raw - expected)
    if current_distance <= tolerance * 0.4:
        return None  # 本來就夠近，不必修

    raw_digits = list(str(raw))
    positions = [i for i, ch in enumerate(raw_digits) if ch in CONFUSED_DIGITS]
    if not positions:
        return None

    # 偏好少改位數的 bias：每多改 1 位，distance 加上 tolerance * 0.3 的懲罰
    flip_penalty = tolerance * 0.3

    best = None  # (score, distance, candidate, changes)
    for flip_count in (1, 2):
        if flip_count > len(positions):
            break
        for flip_positions in itertools.combinations(positions, flip_count):
            options = [
                [d for d in CONFUSED_DIGITS if d != raw_digits[i]]
                for i in flip_positions
            ]
            for replacements in itertools.product(*options):
                new_digits = raw_digits.copy()
                changes = []
                for idx, new in zip(flip_positions, replacements):
                    changes.append(f"第{idx+1}位{new_digits[idx]}→{new}")
                    new_digits[idx] = new
                candidate = int("".join(new_digits))
                if candidate > cap * MAX_OVER_CAP_RATIO:
                    continue
                distance = abs(candidate - expected)
                score = distance + flip_count * flip_penalty
                if distance < current_distance - tolerance * 0.2:
                    if best is None or score < best[0]:
                        best = (score, distance, candidate, changes)

    if best is None:
        return None
    return best[2], pct, f"6/8/9 修正（{', '.join(best[3])}）"


def correct_inserted_digit(raw: int, pct: Optional[float], ctx: Context):
    """OCR 多塞一位數字 — raw 超 cap 過多時，嘗試刪除任一位看哪個最合理。"""
    if ctx.reference_cap is None:
        return None
    cap = ctx.reference_cap
    if raw <= cap * MAX_OVER_CAP_RATIO:
        return None
    raw_str = str(raw)
    if len(raw_str) < 2:
        return None
    expected = _expected_raw(ctx, pct) if pct is not None else None
    tolerance = max(MIN_DELTA, cap * PROGRESS_TOLERANCE_RATIO)
    best = None
    for i in range(len(raw_str)):
        trimmed_str = raw_str[:i] + raw_str[i+1:]
        if not trimmed_str:
            continue
        trimmed = int(trimmed_str)
        if trimmed > cap * MAX_OVER_CAP_RATIO:
            continue
        if expected is not None:
            distance = abs(trimmed - expected)
            if distance > tolerance * 2:
                continue
            if best is None or distance < best[0]:
                best = (distance, trimmed, i)
        else:
            # 沒 pct 時，取「最接近 cap 的合理值」
            score = abs(trimmed - cap * 0.5)
            if best is None or score < best[0]:
                best = (score, trimmed, i)
    if best is None:
        return None
    return best[1], pct, f"刪除第{best[2]+1}位多餘數字"


def correct_missing_prefix(raw: int, pct: Optional[float], ctx: Context):
    """OCR 漏掉首位 — pct 對得上但 raw 比預期小很多。"""
    if pct is None or ctx.reference_cap is None:
        return None
    cap = ctx.reference_cap
    expected = _expected_raw(ctx, pct)
    if expected is None or expected <= 0:
        return None
    if raw >= expected * 0.5:
        return None  # 不算「缺很多」
    tolerance = max(MIN_DELTA, cap * PROGRESS_TOLERANCE_RATIO)
    # 嘗試在前面補 1–9
    best = None
    raw_str = str(raw)
    for prefix in range(1, 10):
        candidate = int(f"{prefix}{raw_str}")
        if candidate > cap * MAX_OVER_CAP_RATIO:
            continue
        distance = abs(candidate - expected)
        if distance <= tolerance and (best is None or distance < best[0]):
            best = (distance, candidate, prefix)
    if best is None:
        return None
    return best[1], pct, f"補回缺失首位 {best[2]}"


def correct_backward(raw: int, pct: Optional[float], ctx: Context):
    """
    上一筆比這筆大但其實是 OCR 誤判 — 用 visual_pct 判斷
    新值是否「真的」比舊值高。回退情況讓 tracker 處理升級判定，這裡不修。
    """
    return None  # 預留位置；複雜的回退邏輯放 tracker 層


DEFAULT_PIPELINE: list[Corrector] = [
    correct_inserted_digit,
    correct_missing_prefix,
    correct_confused_689,
]


@dataclass
class CorrectionResult:
    raw: int
    pct: Optional[float]
    reasons: list[str]
    changed: bool

    @property
    def summary(self) -> str:
        return "；".join(self.reasons) if self.reasons else ""


def apply(raw: Optional[int], pct: Optional[float], ctx: Context,
          pipeline: Optional[list[Corrector]] = None) -> CorrectionResult:
    """套用整條 pipeline。每個 corrector 跑一次（不重複），有改才繼續。"""
    if raw is None:
        return CorrectionResult(raw=raw, pct=pct, reasons=[], changed=False)
    pipeline = pipeline or DEFAULT_PIPELINE
    cur_raw, cur_pct = raw, pct
    reasons: list[str] = []
    for fn in pipeline:
        out = fn(cur_raw, cur_pct, ctx)
        if out is None:
            continue
        new_raw, new_pct, reason = out
        if new_raw != cur_raw or new_pct != cur_pct:
            reasons.append(reason)
            cur_raw, cur_pct = new_raw, new_pct
    return CorrectionResult(
        raw=cur_raw, pct=cur_pct, reasons=reasons,
        changed=(cur_raw != raw or cur_pct != pct),
    )
