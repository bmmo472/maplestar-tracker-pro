"""MapleStar 經驗表 — 從 JSON 載入，可在不改 code 的情況下更新。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional


def _resource_dir() -> Path:
    """PyInstaller 打包後 data/ 會在 sys._MEIPASS；開發環境用專案根目錄。"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def _load() -> dict[int, int]:
    path = _resource_dir() / "data" / "maplestar_exp.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(k): int(v) for k, v in raw.items()}


EXP_BY_LEVEL: dict[int, int] = _load()
MIN_LEVEL = min(EXP_BY_LEVEL)
MAX_LEVEL = max(EXP_BY_LEVEL)


def cap_for_level(level: int) -> Optional[int]:
    """該等級升下一級所需總經驗。超出表範圍回 None。"""
    return EXP_BY_LEVEL.get(int(level))


def estimate_level(raw: int, pct: float,
                   max_error: float = 0.005) -> Optional[tuple[int, float]]:
    """
    用 (raw, pct) 反推等級。
    回 (level, error)，error 越小越像。
    誤差超過 max_error（預設 0.5%）回 None — 表示沒有夠信任的等級。
    """
    if raw is None or pct is None or pct <= 0 or pct >= 100:
        return None
    estimated_cap = raw / (pct / 100)
    best: Optional[tuple[int, float]] = None
    for level, cap in EXP_BY_LEVEL.items():
        err = abs(estimated_cap - cap) / cap
        if best is None or err < best[1]:
            best = (level, err)
    if best is None or best[1] > max_error:
        return None
    return best
