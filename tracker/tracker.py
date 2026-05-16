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
from collections import deque
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
MEDIAN_FILTER_SIZE = 3
CONSENSUS_SAMPLES = 3         # 累積 3 筆 OCR 才檢查共識（從 5 縮短，反應更快）
CONSENSUS_WINDOW_S = 2.0      # 至少 2 秒才 commit 一次（從 3 秒縮短）
CONSENSUS_SPREAD_RATIO = 0.005  # 共識：spread 須 < 0.5% raw 值
CONSENSUS_SPREAD_MIN = 30000  # 絕對下限 30K（從 10K 放寬，配合快打怪每秒 30K+ 增量）
CONSENSUS_MAX_FAILS = 3       # 連續 N 次共識失敗強制 commit median（避免雪崩）


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
        self._last_raw: Optional[int] = None     # 上次 commit 後的 raw（給 delta 計算用）
        self._last_pct: Optional[float] = None
        # UI 顯示用 — 每筆 OCR 都更新（即時反應，不等共識）
        self._display_raw: Optional[int] = None
        self._display_pct: Optional[float] = None
        self._manual_level: Optional[int] = None
        self._level_cap: Optional[int] = None
        self._level_auto_detected: bool = False  # 該等級是自動偵測的
        self._level_votes: list[int] = []        # 自動偵測投票緩衝（從 raw+pct 反推）
        self._level_ocr_votes: list[int] = []    # 等級 OCR 投票緩衝（直接讀 'Lv 158'）
        self._capture_count = 0
        self._recognized_count = 0
        self._ignored_count = 0
        self._level_up_count = 0
        self._last_status: SampleStatus = SampleStatus()
        self._last_ocr: Optional[OCRResult] = None
        # OCR 抖動抑制（單筆雜訊）
        self._raw_filter_buf: deque[int] = deque(maxlen=MEDIAN_FILTER_SIZE)
        # 5 秒共識緩衝（commit 用）— 存 (t, raw, pct, visual_pct)
        self._consensus_buf: deque = deque(maxlen=CONSENSUS_SAMPLES)
        self._last_commit_at: float = 0.0
        self._consensus_fail_count: int = 0      # 連續共識失敗次數

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
        """給 UI 顯示用 — 每筆 OCR 都更新，不等共識。"""
        with self._lock:
            return self._display_raw if self._display_raw is not None else self._last_raw

    @property
    def last_pct(self) -> Optional[float]:
        """給 UI 顯示用 — 每筆 OCR 都更新，不等共識。"""
        with self._lock:
            return self._display_pct if self._display_pct is not None else self._last_pct

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
            self._level_ocr_votes = []
            self._capture_count = 0
            self._recognized_count = 0
            self._ignored_count = 0
            self._level_up_count = 0
            self._last_status = SampleStatus()
            self._last_ocr = None
            self._raw_filter_buf.clear()
            self._consensus_buf.clear()
            self._last_commit_at = 0.0
            self._consensus_fail_count = 0
            self._display_raw = None
            self._display_pct = None

    def set_manual_level(self, level: Optional[int]) -> None:
        with self._lock:
            self._manual_level = level
            self._level_auto_detected = False
            self._level_votes = []
            self._level_ocr_votes = []
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

    def submit_level_ocr(self, level: Optional[int]) -> bool:
        """
        接收等級 OCR 結果。連續 3 筆同等級才採用，避免單筆 OCR 雜訊污染。

        回傳 True 代表這次有更新等級。
        手動已設等級的情況下，OCR 仍可覆蓋（前提是穩定 3 筆）。
        """
        if level is None or not (1 <= level <= 300):
            return False
        with self._lock:
            self._level_ocr_votes.append(level)
            if len(self._level_ocr_votes) > 3:
                self._level_ocr_votes.pop(0)
            if len(self._level_ocr_votes) < 3:
                return False
            # 3 筆都一樣才採用
            if len(set(self._level_ocr_votes)) != 1:
                return False
            confirmed = self._level_ocr_votes[0]
            if self._manual_level == confirmed:
                return False  # 沒變化
            self._manual_level = confirmed
            self._level_cap = exp_table.cap_for_level(confirmed)
            self._level_auto_detected = True  # 視為自動偵測
            return True

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

            # === Bug D 防護：corrector 之後 raw 仍為 None 直接忽略 ===
            if raw is None:
                self._ignored_count += 1
                status.state = "未讀到 EXP"
                status.reason = "OCR 修正後無有效讀值"
                self._last_status = status
                return status

            # === Bug A 修正：UI 顯示立即更新，不等共識 ===
            # 給「目前 EXP」即時反應；共識只控制 commit 累積
            # （之前加 sanity check 反而會 freeze UI，移除）
            self._display_raw = raw
            self._display_pct = pct

            # 自動偵測等級用最新 raw（每筆都跑）
            self._try_auto_detect_level(raw, pct)

            # === 5 秒共識門檻（僅控制 commit，不影響 UI 顯示） ===
            # 累積 5 筆 OCR 後檢查共識，不通過整批丟棄等下輪
            # 寧可慢一點，但累積要準
            self._consensus_buf.append((t, raw, pct, ocr_result.visual_pct))
            need_samples = len(self._consensus_buf) < CONSENSUS_SAMPLES
            need_time = (t - self._last_commit_at) < CONSENSUS_WINDOW_S
            if need_samples or need_time:
                have = min(len(self._consensus_buf), CONSENSUS_SAMPLES)
                status.state = f"收集樣本 {have}/{CONSENSUS_SAMPLES}"
                status.raw_after = raw  # UI 顯示用
                status.pct_after = pct
                self._last_status = status
                return status

            # 取最近 N 筆排序檢查 spread（3 筆時直接 max-min，5+ 筆才去頭去尾）
            recent = list(self._consensus_buf)[-CONSENSUS_SAMPLES:]
            raws_valid = [r[1] for r in recent if r[1] is not None]
            if len(raws_valid) < CONSENSUS_SAMPLES:
                status.state = "OCR 樣本不足"
                self._last_status = status
                return status

            raws_sorted = sorted(raws_valid)
            if len(raws_sorted) >= 5:
                # 5+ 筆：去頭去尾取中央 3 筆 spread（抗離群值更強）
                middle = raws_sorted[1:-1]
                spread = middle[-1] - middle[0]
                median_raw = middle[len(middle) // 2]
            else:
                # 3-4 筆：直接 spread = max - min, median 取中位數
                spread = raws_sorted[-1] - raws_sorted[0]
                median_raw = raws_sorted[len(raws_sorted) // 2]
            spread_threshold = max(int(median_raw * CONSENSUS_SPREAD_RATIO),
                                   CONSENSUS_SPREAD_MIN)

            if spread > spread_threshold:
                # Bug B 修正：連續失敗計數，超過 MAX 強制 commit median 避免雪崩
                self._consensus_fail_count += 1
                if self._consensus_fail_count < CONSENSUS_MAX_FAILS:
                    self._ignored_count += 1
                    status.state = "樣本驗證中"
                    status.reason = (f"{len(raws_sorted)} 筆 spread {spread:,} > 容忍 {spread_threshold:,}"
                                     f" (失敗 {self._consensus_fail_count}/{CONSENSUS_MAX_FAILS})")
                    self._last_status = status
                    return status
                # 連續失敗達上限：強制採用 median + 重置計數 + 清 buffer
                self._consensus_buf.clear()
                # 不 return，往下走採用 median raw

            # 共識成立（或強制採用）— 用 median raw / median pct / median visual_pct
            self._consensus_fail_count = 0
            raw = median_raw
            pcts_sorted = sorted([r[2] for r in recent if r[2] is not None])
            if pcts_sorted:
                pct = pcts_sorted[len(pcts_sorted) // 2]
            visuals_sorted = sorted([r[3] for r in recent if r[3] is not None])
            consensus_visual_pct = (visuals_sorted[len(visuals_sorted) // 2]
                                    if visuals_sorted else ocr_result.visual_pct)
            # 把 ocr_result 的 visual_pct 替換為共識值，後續邏輯沿用
            ocr_result.visual_pct = consensus_visual_pct

            self._last_commit_at = t

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
                status.state = "起始基準設定"
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
                status.state = "等級切換"
                status.reason = f"補算 {remaining:,} + 新等 {raw:,}"
                status.raw_after, status.pct_after = raw, pct
                self._last_status = status
                return status

            if delta > 0:
                # 異常跳動檢查
                if self._is_suspicious_jump(delta, raw, pct, ocr_result.visual_pct):
                    if not self._confirm_jump(raw, t):
                        self._ignored_count += 1
                        status.state = "確認中"
                        status.reason = f"+{delta:,} 等下一筆確認"
                        self._last_status = status
                        return status
                    # 確認過的跳動 → 視為 baseline 校正（OCR 早期讀錯），不加 delta
                    self.pending.clear_jump()
                    self.pending.clear_reset()
                    self._last_raw = raw
                    self._last_pct = pct
                    self.rate_engine.add(t, self.rate_engine.total_gained)
                    self._recognized_count += 1
                    status.accepted = True
                    status.state = "重新校正"
                    status.reason = f"OCR 跳動 +{delta:,} 視為早期讀值錯誤"
                    status.raw_after, status.pct_after = raw, pct
                    self._last_status = status
                    return status
                self.pending.clear_jump()
                self.pending.clear_reset()
                self._commit(t, raw, pct, delta)
                self._recognized_count += 1
                status.accepted = True
                status.state = "同步完成"
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
                status.state = "資料修正"
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
        # 第一道（永遠檢查）：delta 接近 raw 一定是 baseline 早期讀錯
        # 例如 baseline OCR 讀到 1234，下一筆讀到 3,780,000，delta 99% 來自基準偏差
        if raw > 0 and delta > raw * 0.30:
            return True
        # 有等級時加第二、三道
        if self._level_cap is not None:
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
