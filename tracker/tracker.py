"""
主追蹤器：接收 OCR 結果 → 套修正 → 加入樣本 → 維護升級狀態機。

跟原作者比的關鍵改進：
1. 不再有 12 個 _pending_* 變數 — 全部包進 PendingState dataclass
2. 升級確認、跳動確認、回退處理 → 三個獨立、可測的方法
3. corrector 跑一遍就好（不再重複呼叫 3 次）
4. samples 緩衝獨立到 RateEngine，這層只管狀態機
5. 加 threading.Lock，UI 跟 worker thread 同時存取也安全
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from . import corrector, exp_table
from .ocr import OCRResult
from .rate import RateEngine


# === 常數 ===
MAX_OVER_CAP_RATIO = 1.02
MIN_DELTA_TOLERANCE = 50_000
DELTA_TOLERANCE_RATIO = 4.0
PROGRESS_TOLERANCE_RATIO = 0.025
LEVEL_RESET_CONFIRM_SAMPLES = 2
PCT_VISUAL_MISMATCH_TOLERANCE = 3.0
BASELINE_CONFIRM_DIGIT_MATCH = True


@dataclass
class PendingState:
    """暫存狀態 — 把原作者散落的 12 個 _pending_* 變數收進來。"""
    # 第一筆基準確認
    baseline_raw: Optional[int] = None
    baseline_pct: Optional[float] = None
    baseline_at: Optional[float] = None

    # 跳動確認（一筆異常大的 +delta 要不要採用）
    jump_raw: Optional[int] = None
    jump_at: Optional[float] = None

    # 升級確認（疑似升級的歸零）
    reset_raw: Optional[int] = None
    reset_pct: Optional[float] = None
    reset_previous_raw: Optional[int] = None
    reset_previous_pct: Optional[float] = None
    reset_at: Optional[float] = None
    reset_count: int = 0

    def clear_jump(self) -> None:
        self.jump_raw = None
        self.jump_at = None

    def clear_reset(self) -> None:
        self.reset_raw = None
        self.reset_pct = None
        self.reset_previous_raw = None
        self.reset_previous_pct = None
        self.reset_at = None
        self.reset_count = 0


@dataclass
class SampleStatus:
    """每次 _add_sample 的結果狀態，給 UI 顯示用。"""
    accepted: bool = False
    state: str = ""              # 「已採用」「待確認」「已忽略」等
    reason: str = ""             # 詳細原因
    corrections: list[str] = field(default_factory=list)
    raw_after: Optional[int] = None
    pct_after: Optional[float] = None


class Tracker:
    def __init__(self):
        self._lock = threading.RLock()
        self.rate_engine = RateEngine()
        self.pending = PendingState()
        self._last_raw: Optional[int] = None
        self._last_pct: Optional[float] = None
        self._manual_level: Optional[int] = None
        self._level_cap: Optional[int] = None
        self._level_auto_detected: bool = False  # 該等級是自動偵測的
        self._level_votes: list[int] = []        # 自動偵測投票緩衝
        self._capture_count = 0
        self._recognized_count = 0
        self._ignored_count = 0
        self._level_up_count = 0
        self._last_status: SampleStatus = SampleStatus()
        self._last_ocr: Optional[OCRResult] = None

    # ===== 公開 read-only properties =====
    @property
    def capture_count(self) -> int:
        with self._lock:
            return self._capture_count

    @property
    def recognized_count(self) -> int:
        with self._lock:
            return self._recognized_count

    @property
    def ignored_count(self) -> int:
        with self._lock:
            return self._ignored_count

    @property
    def level_up_count(self) -> int:
        with self._lock:
            return self._level_up_count

    @property
    def manual_level(self) -> Optional[int]:
        with self._lock:
            return self._manual_level

    @property
    def last_raw(self) -> Optional[int]:
        with self._lock:
            return self._last_raw

    @property
    def last_pct(self) -> Optional[float]:
        with self._lock:
            return self._last_pct

    @property
    def last_status(self) -> SampleStatus:
        with self._lock:
            return self._last_status

    @property
    def last_ocr(self) -> Optional[OCRResult]:
        with self._lock:
            return self._last_ocr

    @property
    def level_cap(self) -> Optional[int]:
        with self._lock:
            return self._level_cap

    @property
    def level_auto_detected(self) -> bool:
        with self._lock:
            return self._level_auto_detected

    # ===== 控制 =====
    def reset(self) -> None:
        with self._lock:
            self.rate_engine.reset()
            self.pending = PendingState()
            self._last_raw = None
            self._last_pct = None
            # reset 後保留手動等級設定；自動偵測的清掉
            if self._level_auto_detected:
                self._manual_level = None
                self._level_cap = None
                self._level_auto_detected = False
            self._level_votes = []
            self._capture_count = 0
            self._recognized_count = 0
            self._ignored_count = 0
            self._level_up_count = 0
            self._last_status = SampleStatus()
            self._last_ocr = None

    def set_manual_level(self, level: Optional[int]) -> None:
        with self._lock:
            self._manual_level = level
            self._level_auto_detected = False
            self._level_votes = []
            if level is not None:
                self._level_cap = exp_table.cap_for_level(level)
            else:
                self._level_cap = None

    def set_manual_exp(self, raw: int, pct: Optional[float] = None) -> None:
        """手動校正目前 EXP — 重設 last_raw/last_pct 並清掉 pending 狀態。"""
        with self._lock:
            self._last_raw = raw
            if pct is not None:
                self._last_pct = pct
            elif self._level_cap is not None:
                self._last_pct = raw / self._level_cap * 100
            self.pending = PendingState()

    def note_capture(self) -> None:
        with self._lock:
            self._capture_count += 1

    # ===== 核心：加入一筆 OCR 樣本 =====
    def submit(self, ocr_result: OCRResult, t: Optional[float] = None) -> SampleStatus:
        """接收一筆 OCR 結果，跑 corrector + 狀態機，回 SampleStatus。"""
        t = t if t is not None else time.time()
        status = SampleStatus()
        with self._lock:
            self._last_ocr = ocr_result
            if not ocr_result.ok or ocr_result.raw is None:
                self._ignored_count += 1
                status.state = "未讀到 EXP" if not ocr_result.ok else "只讀到百分比"
                status.reason = ocr_result.error or status.state
                self._last_status = status
                return status

            # 跑修正 pipeline
            ctx = corrector.Context(
                manual_level=self._manual_level,
                last_raw=self._last_raw,
                last_pct=self._last_pct,
                visual_pct=ocr_result.visual_pct,
            )
            corr = corrector.apply(ocr_result.raw, ocr_result.pct, ctx)
            raw, pct = corr.raw, corr.pct
            status.corrections = corr.reasons

            # 自動偵測等級（每筆都跑直到確認）
            self._try_auto_detect_level(raw, pct)

            # 視覺百分比交叉驗證 — 不一致就忽略
            if not self._matches_visual(pct, ocr_result.visual_pct):
                self._ignored_count += 1
                status.state = "已忽略"
                status.reason = (
                    f"OCR pct={pct} 與進度條 {ocr_result.visual_pct:.1f}% 差距過大"
                    if pct is not None and ocr_result.visual_pct is not None
                    else "進度條與 OCR 不一致"
                )
                self._last_status = status
                return status

            # 基準確認：第一筆 / 重置後
            if self._last_raw is None:
                if not self._confirm_baseline(raw, pct, t, status):
                    self._last_status = status
                    return status
                self._adopt_first(raw, pct, t)
                self._recognized_count += 1
                status.accepted = True
                status.state = "已採用（基準）"
                status.raw_after, status.pct_after = raw, pct
                self._last_status = status
                return status

            # 與上一筆比對
            delta = raw - self._last_raw
            level_reset = self._is_level_reset(self._last_raw, self._last_pct, raw, pct)

            if level_reset:
                if not self._confirm_level_reset(raw, pct, t, status):
                    self._last_status = status
                    return status
                # 補算升級前剩餘 + 新等級已得
                remaining = max(0, (self._level_cap or 0) - self._last_raw)
                gained = remaining + raw
                self._level_up_count += 1
                self._advance_level_after_reset()
                self._commit(t, raw, pct, gained)
                self._recognized_count += 1
                status.accepted = True
                status.state = "已採用（升級）"
                status.reason = f"補算 {remaining:,} + 新等 {raw:,}"
                status.raw_after, status.pct_after = raw, pct
                self._last_status = status
                return status

            if delta > 0:
                # 異常跳動檢查
                if self._is_suspicious_jump(delta, raw, pct, ocr_result.visual_pct):
                    if not self._confirm_jump(raw, t):
                        self._ignored_count += 1
                        status.state = "待確認（跳動）"
                        status.reason = f"+{delta:,} 等下一筆確認"
                        self._last_status = status
                        return status
                self.pending.clear_jump()
                self.pending.clear_reset()
                self._commit(t, raw, pct, delta)
                self._recognized_count += 1
                status.accepted = True
                status.state = "已採用"
                status.raw_after, status.pct_after = raw, pct
                self._last_status = status
                return status

            if delta == 0:
                # 沒變化 — 直接記錄但不增加總獲得
                self._commit(t, raw, pct, 0)
                self._recognized_count += 1
                status.accepted = True
                status.state = "無變化"
                status.raw_after, status.pct_after = raw, pct
                self._last_status = status
                return status

            # delta < 0：可能是 OCR 錯，也可能是合理回補；視覺百分比一致就接受
            if (ocr_result.visual_pct is not None and pct is not None
                    and abs(pct - ocr_result.visual_pct) <= PCT_VISUAL_MISMATCH_TOLERANCE
                    and pct < (self._last_pct or 100)):
                # 是 OCR 低讀回補，但 delta 仍 < 0 — 替換 last_raw 但不變動 total
                self._last_raw = raw
                self._last_pct = pct
                self.rate_engine.add(t, self.rate_engine.total_gained)
                status.accepted = True
                status.state = "已採用（回補修正）"
                status.raw_after, status.pct_after = raw, pct
                self._recognized_count += 1
                self._last_status = status
                return status

            self._ignored_count += 1
            status.state = "已忽略"
            status.reason = f"EXP 回退 {self._last_raw:,} → {raw:,}"
            self._last_status = status
            return status

    # ===== 內部輔助 =====
    def _matches_visual(self, pct: Optional[float], visual_pct: Optional[float]) -> bool:
        if pct is None or visual_pct is None:
            return True  # 缺一個訊號就不擋
        return abs(pct - visual_pct) <= PCT_VISUAL_MISMATCH_TOLERANCE * 2  # 寬鬆些

    def _confirm_baseline(self, raw: int, pct: Optional[float], t: float, status: SampleStatus) -> bool:
        p = self.pending
        if p.baseline_raw is None:
            p.baseline_raw = raw
            p.baseline_pct = pct
            p.baseline_at = t
            status.state = "校準中"
            status.reason = "等待第二筆確認"
            return False
        same_digits = len(str(raw)) == len(str(p.baseline_raw))
        plausible_delta = abs(raw - p.baseline_raw) <= max(MIN_DELTA_TOLERANCE,
                                                           max(raw, p.baseline_raw) * 0.25)
        if not (same_digits and plausible_delta):
            p.baseline_raw = raw
            p.baseline_pct = pct
            p.baseline_at = t
            status.state = "校準中"
            status.reason = "讀值不穩定，重新校準"
            self._ignored_count += 1
            return False
        return True

    def _adopt_first(self, raw: int, pct: Optional[float], t: float) -> None:
        self._last_raw = raw
        self._last_pct = pct
        self.rate_engine.add(t, 0)
        # 自動偵測由 submit 裡的 _try_auto_detect_level 處理（每筆都跑）
        self.pending = PendingState()

    def _try_auto_detect_level(self, raw: int, pct: Optional[float]) -> None:
        """
        嘗試從 (raw, pct) 自動推斷等級。
        需要連續 3 筆樣本投出同一個等級才採用，避免單筆 OCR 錯讀污染。
        手動已設等級或已自動確認則跳過。
        """
        if self._manual_level is not None or pct is None:
            return
        est = exp_table.estimate_level(raw, pct, max_error=0.005)
        if est is None:
            # 這筆估不出 → 清空投票重來
            self._level_votes = []
            return
        self._level_votes.append(est[0])
        # 只保留最近 5 筆
        if len(self._level_votes) > 5:
            self._level_votes = self._level_votes[-5:]
        # 最近 3 筆都一樣 → 確認
        if len(self._level_votes) >= 3 and len(set(self._level_votes[-3:])) == 1:
            level = self._level_votes[-1]
            self._manual_level = level
            self._level_cap = exp_table.cap_for_level(level)
            self._level_auto_detected = True
            self._level_votes = []

    def _is_level_reset(self, prev_raw: Optional[int], prev_pct: Optional[float],
                        raw: int, pct: Optional[float]) -> bool:
        if prev_raw is None or prev_pct is None or pct is None:
            return False
        return prev_pct >= 90 and pct <= 20 and raw < prev_raw

    def _confirm_level_reset(self, raw: int, pct: Optional[float], t: float, status: SampleStatus) -> bool:
        p = self.pending
        if p.reset_raw is None:
            p.reset_raw = raw
            p.reset_pct = pct
            p.reset_previous_raw = self._last_raw
            p.reset_previous_pct = self._last_pct
            p.reset_at = t
            p.reset_count = 1
            status.state = "升級確認中"
            return False
        # 連續同方向 reset 才確認
        if abs(raw - (p.reset_raw or 0)) <= max(MIN_DELTA_TOLERANCE, raw * 0.3):
            p.reset_count += 1
        else:
            p.reset_raw = raw
            p.reset_count = 1
            status.state = "升級確認中"
            return False
        if p.reset_count < LEVEL_RESET_CONFIRM_SAMPLES:
            status.state = "升級確認中"
            return False
        return True

    def _advance_level_after_reset(self) -> None:
        # 不論是手動還是自動偵測，只要有等級就升一級
        if self._manual_level is not None:
            next_level = self._manual_level + 1
            cap = exp_table.cap_for_level(next_level)
            if cap is not None:
                self._manual_level = next_level
                self._level_cap = cap
                # 升級後重新驗證一遍
                self._level_votes = []

    def _is_suspicious_jump(self, delta: int, raw: int, pct: Optional[float],
                            visual_pct: Optional[float]) -> bool:
        if self._level_cap is None:
            return False
        cap = self._level_cap
        if delta > cap * 0.5:  # 一筆跳超過 50% 等級
            return True
        # pct 變化跟 delta 對不上
        if pct is not None and self._last_pct is not None:
            expected_pct_delta = delta / cap * 100
            actual_pct_delta = pct - self._last_pct
            if abs(actual_pct_delta - expected_pct_delta) > 5.0:
                return True
        return False

    def _confirm_jump(self, raw: int, t: float) -> bool:
        p = self.pending
        if p.jump_raw is None:
            p.jump_raw = raw
            p.jump_at = t
            return False
        if abs(raw - p.jump_raw) <= max(MIN_DELTA_TOLERANCE, raw * 0.05):
            return True
        p.jump_raw = raw
        p.jump_at = t
        return False

    def _commit(self, t: float, raw: int, pct: Optional[float], delta_gained: int) -> None:
        self._last_raw = raw
        self._last_pct = pct
        new_total = self.rate_engine.total_gained + max(0, delta_gained)
        self.rate_engine.add(t, new_total)
