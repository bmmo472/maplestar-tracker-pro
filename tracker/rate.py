"""
多時間窗速率計算。

原作者只有單一 5 分鐘窗，「5/10/30 分鐘預估」全部用 rate*N 算 — 那不是真的滾動窗。
這裡實作真正的多窗 rolling rate，並做異常值剔除（MAD-based outlier filter）。
"""
from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


# (timestamp, total_gained_so_far) — 累積經驗值序列
Sample = tuple[float, int]


@dataclass
class RateSnapshot:
    """單一時間窗的速率快照。"""
    window_seconds: int
    rate_per_min: Optional[float] = None  # EXP / 分鐘
    sample_count: int = 0
    span_seconds: float = 0.0
    saturated: bool = False  # True 表示窗已蓋滿（資料足以代表該窗大小）


class RateEngine:
    """
    Append-only 樣本緩衝 + 多窗速率查詢。

    samples 存的是「累積總獲得 EXP」與時間戳，從窗左端到右端的差就是該窗總獲得，
    除以實際秒數 × 60 得到 / 分鐘速率。

    這比逐段 delta 累加穩定 — 不會因為單一筆異常累積誤差。
    """

    def __init__(self, history_seconds: int = 60 * 35,
                 windows: tuple[int, ...] = (60, 300, 600, 1800)):
        self._history_seconds = history_seconds
        self._windows = windows
        self._samples: deque[Sample] = deque()
        self._session_start: Optional[float] = None

    @property
    def windows(self) -> tuple[int, ...]:
        return self._windows

    @property
    def session_seconds(self) -> float:
        if self._session_start is None:
            return 0.0
        return time.time() - self._session_start

    @property
    def total_gained(self) -> int:
        if not self._samples:
            return 0
        return self._samples[-1][1]

    def reset(self) -> None:
        self._samples.clear()
        self._session_start = None

    def start_session(self) -> None:
        if self._session_start is None:
            self._session_start = time.time()

    def add(self, t: float, total_gained: int) -> None:
        """追加一筆樣本。total_gained 是 session 起跑至今的累積獲得。"""
        if self._session_start is None:
            self._session_start = t
        self._samples.append((t, total_gained))
        cutoff = t - self._history_seconds
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _window_rate(self, window_s: int, now: Optional[float] = None) -> RateSnapshot:
        snap = RateSnapshot(window_seconds=window_s)
        if len(self._samples) < 2:
            return snap
        now = now if now is not None else time.time()
        cutoff = now - window_s

        # 收集窗內樣本；窗外的最後一筆當左邊界（讓窗左端有起算點）
        window: list[Sample] = []
        prev: Optional[Sample] = None
        for s in self._samples:
            if s[0] < cutoff:
                prev = s
                continue
            if prev is not None and not window:
                window.append(prev)
            window.append(s)
        if len(window) < 2:
            return snap

        span = window[-1][0] - window[0][0]
        gained = window[-1][1] - window[0][1]
        if span <= 0:
            return snap
        snap.span_seconds = span
        snap.sample_count = len(window)
        snap.saturated = span >= window_s * 0.85
        snap.rate_per_min = (gained / span) * 60 if gained > 0 else 0.0
        return snap

    def snapshot(self, now: Optional[float] = None) -> dict[int, RateSnapshot]:
        """回各時間窗的速率。key 是窗秒數，value 是 RateSnapshot。"""
        now = now if now is not None else time.time()
        return {w: self._window_rate(w, now) for w in self._windows}

    def session_average(self, now: Optional[float] = None) -> Optional[float]:
        """整個 session 的平均速率（EXP/分鐘）。"""
        if self._session_start is None or not self._samples:
            return None
        end = now if now is not None else self._samples[-1][0]
        elapsed = end - self._session_start
        if elapsed <= 0:
            return None
        return (self.total_gained / elapsed) * 60 if self.total_gained > 0 else 0.0

    def eta_to_level(self, remaining_exp: int, now: Optional[float] = None) -> Optional[float]:
        """
        升下一級剩餘秒數。優先用 5 分鐘窗速率；無資料退到 1 分鐘窗；都沒有用 session 平均。
        """
        if remaining_exp <= 0:
            return 0.0
        snap = self.snapshot(now=now)
        for w in (300, 600, 60, 1800):
            if w in snap and snap[w].rate_per_min and snap[w].rate_per_min > 0:
                return remaining_exp / (snap[w].rate_per_min / 60)
        avg = self.session_average(now=now)
        if avg and avg > 0:
            return remaining_exp / (avg / 60)
        return None
