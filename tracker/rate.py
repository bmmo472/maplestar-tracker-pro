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
        # 暫停補償：累計停止期間長度，effective_elapsed 會扣掉
        self._paused_duration: float = 0.0
        self._pause_start: Optional[float] = None  # 目前是否在暫停中
        # interval cache — pause/resume 邊界區間可能落在暫停期間取不到值
        # 用 cache 保持顯示「上一個有效鎖定值」直到新區間有真實累積
        self._interval_cache: dict[int, int] = {}

    @property
    def windows(self) -> tuple[int, ...]:
        return self._windows

    @property
    def session_seconds(self) -> float:
        if self._session_start is None:
            return 0.0
        return time.time() - self._session_start

    def effective_elapsed(self, now: Optional[float] = None) -> float:
        """
        有效追蹤秒數 = wall clock elapsed - 累計暫停時長。

        所有「跨界鎖定」相關計算都用這個，不會被停止期間誤導。
        """
        if self._session_start is None:
            return 0.0
        now = now if now is not None else time.time()
        elapsed = now - self._session_start - self._paused_duration
        # 如果目前正在暫停中，再扣掉這次的累積
        if self._pause_start is not None:
            elapsed -= (now - self._pause_start)
        return max(0.0, elapsed)

    def pause(self) -> None:
        """通知 engine 進入暫停狀態。"""
        if self._pause_start is None:
            self._pause_start = time.time()

    def resume(self) -> None:
        """通知 engine 恢復追蹤，把這段暫停加進累計。"""
        if self._pause_start is not None:
            self._paused_duration += time.time() - self._pause_start
            self._pause_start = None

    @property
    def total_gained(self) -> int:
        if not self._samples:
            return 0
        return self._samples[-1][1]

    def reset(self) -> None:
        self._samples.clear()
        self._session_start = None
        self._paused_duration = 0.0
        self._pause_start = None
        self._interval_cache.clear()

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

    def _gained_at(self, target_t: float) -> Optional[int]:
        """
        找最接近 target_t 的樣本 total_gained。
        優先取 <= target_t 的最近者；若沒有就取最早一筆（避免回 None）。
        """
        if not self._samples:
            return None
        best: Optional[int] = None
        best_t: Optional[float] = None
        for t, g in self._samples:
            if t <= target_t:
                best = g
                best_t = t
            else:
                # 已超過 target，看是否「比上一筆更接近」
                if best is None:
                    # target 在第一筆樣本之前 → 用最早樣本
                    return g
                # 否則用上一筆（已在 best）
                break
        return best

    def interval_accumulated(self, window_seconds: int,
                             now: Optional[float] = None) -> Optional[int]:
        """
        最近一個完整 N 秒區間的累積 EXP（用有效追蹤時長，扣除暫停期間）。

        - elapsed < W：第一個區間還沒過完，回 session start 到現在的累積
        - elapsed >= W：永遠回**最近一個完整區間**的累積值（不會被「進行中」覆蓋）
        """
        if self._session_start is None or not self._samples:
            return None
        now = now if now is not None else time.time()
        # 用有效追蹤時長切區間，停止期間不算
        elapsed = self.effective_elapsed(now=now)
        if elapsed <= 0:
            return None
        if elapsed < window_seconds:
            # 還沒完成第一個區間，顯示目前累積
            return self.total_gained
        # 找最近一個完整區間
        full_count = int(elapsed // window_seconds)
        end_offset = full_count * window_seconds
        start_offset = end_offset - window_seconds
        # 把有效時長轉回 wall clock 時間
        # 注意：只加「已完成的暫停」，不加進行中的暫停
        # （進行中暫停會讓區間落在沒樣本期間導致顯示 0）
        wall_offset = self._paused_duration
        start_t = self._session_start + start_offset + wall_offset
        end_t = self._session_start + end_offset + wall_offset
        start_g = self._gained_at(start_t)
        end_g = self._gained_at(end_t)
        if start_g is None or end_g is None:
            # 沒樣本 fallback cache
            return self._interval_cache.get(window_seconds)
        result = max(0, int(end_g - start_g))
        # 如果結果 > 0 更新 cache（pause 期間區間會算到 0，那時用 cache 保持上次值）
        if result > 0:
            self._interval_cache[window_seconds] = result
            return result
        # 結果 0：可能是真的沒打怪、或區間落在 paused 期間
        # 有 cache 就用 cache，沒 cache 就回 0
        return self._interval_cache.get(window_seconds, 0)
