"""主視窗 — Tokyo Night PySide6 介面。"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Optional

import mss
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QStatusBar, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from tracker import capture, ocr, settings as settings_mod
from tracker.exp_table import MAX_LEVEL, MIN_LEVEL, cap_for_level
from tracker.tracker import Tracker

from .about_dialog import AboutDialog
from .floating_window import FloatingWindow
from .region_picker import RegionPickerDialog
from .styles import COLORS, stylesheet


SAMPLE_INTERVAL_OPTIONS: tuple[float, ...] = (0.5, 1, 2, 3, 5, 10)
APP_TITLE = "MapleStar Tracker Pro"
APP_VERSION = "1.3.3"
AUTHOR = "土豆地雷"
COPYRIGHT = f"© 2026 {AUTHOR}"


def _asset_path(filename: str) -> Path:
    """回傳 asset 檔案的絕對路徑（適用於開發與打包後環境）。"""
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "assets" / filename


class _Worker(QObject):
    """背景擷取 + OCR 執行緒；用 signal 把結果送回 UI thread。"""
    result_ready = Signal(object)            # OCRResult (EXP)
    level_result_ready = Signal(object)      # Optional[int] (Level OCR)
    error_occurred = Signal(str)

    def __init__(self, window_info: capture.WindowInfo,
                 roi: tuple[int, int, int, int], interval: float,
                 level_roi: Optional[tuple[int, int, int, int]] = None):
        super().__init__()
        self._win = window_info
        self._roi = roi
        self._level_roi = level_roi
        self._interval = interval
        self._running = False
        self._tick = 0

    def set_interval(self, seconds: float) -> None:
        self._interval = float(seconds)

    def set_roi(self, roi: tuple[int, int, int, int]) -> None:
        self._roi = roi

    def set_level_roi(self, level_roi: Optional[tuple[int, int, int, int]]) -> None:
        self._level_roi = level_roi

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        with mss.mss() as sct:
            while self._running:
                start = time.time()
                try:
                    img = capture.grab_window_roi(self._win, *self._roi, sct=sct)
                    if img is None:
                        self.error_occurred.emit("無法擷取視窗")
                    else:
                        result = ocr.recognize(img)
                        self.result_ready.emit(result)

                    # 等級 OCR — 每 3 個 tick 才跑一次省 CPU
                    if self._level_roi is not None and self._tick % 3 == 0:
                        lvl_img = capture.grab_window_roi(self._win, *self._level_roi, sct=sct)
                        if lvl_img is not None:
                            lvl = ocr.recognize_level(lvl_img)
                            self.level_result_ready.emit(lvl)
                    self._tick += 1
                except Exception as e:
                    self.error_occurred.emit(str(e))

                # 等待下一次 — 分大塊 sleep 比連續小 sleep 省 CPU
                # 大段 sleep 讓 OS 真的進入 idle，不會 busy poll
                remaining = (start + self._interval) - time.time()
                while self._running and remaining > 0:
                    chunk = 0.2 if remaining > 0.2 else remaining
                    time.sleep(chunk)
                    remaining = (start + self._interval) - time.time()


def _make_card(parent: QWidget, title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("section_label")
        layout.addWidget(lbl)
    return card, layout


def _make_metric(parent: QWidget, label_text: str,
                 value_obj: str = "metric_value_small") -> tuple[QWidget, QLabel]:
    container = QWidget(parent)
    v = QVBoxLayout(container)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    lbl = QLabel(label_text)
    lbl.setObjectName("metric_label")
    value = QLabel("—")
    value.setObjectName(value_obj)
    v.addWidget(lbl)
    v.addWidget(value)
    return container, value


def _make_stat(parent: QWidget, label_text: str,
               value_obj: str = "stat_value") -> tuple[QWidget, QLabel]:
    """新版資訊條的單位元 — label 在上、value 在下，緊湊垂直布局。"""
    container = QWidget(parent)
    v = QVBoxLayout(container)
    v.setContentsMargins(14, 12, 14, 12)
    v.setSpacing(4)
    lbl = QLabel(label_text.upper())
    lbl.setObjectName("stat_label")
    value = QLabel("—")
    value.setObjectName(value_obj)
    v.addWidget(lbl)
    v.addWidget(value)
    return container, value


def _format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{int(seconds)} 秒"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m} 分 {s:02d} 秒"
    h, rem = divmod(int(seconds), 3600)
    m, _ = divmod(rem, 60)
    return f"{h} 小時 {m} 分"


def _format_num(n: Optional[int | float]) -> str:
    if n is None:
        return "—"
    return f"{int(n):,}"


def _format_compact(n: Optional[int | float]) -> str:
    """大數字精簡格式化 — K / M / B。"""
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:,}"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.resize(1180, 760)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(stylesheet())

        icon_path = _asset_path("app_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        capture.enable_dpi_awareness()

        self._tracker = Tracker()
        self._worker: Optional[_Worker] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._windows: list[capture.WindowInfo] = []
        self._selected_window: Optional[capture.WindowInfo] = None
        self._roi: Optional[tuple[int, int, int, int]] = None
        self._level_roi: Optional[tuple[int, int, int, int]] = None
        self._interval = 1.0
        self._settings = settings_mod.load()
        self._session_start: Optional[float] = None  # 本次開始追蹤的時間（每次 start 重設）
        self._accumulated_elapsed: float = 0.0       # 之前已累積的追蹤秒數（跨 pause/resume 保留）
        # GPU 偏好：從 settings 讀，但若當前環境不支援 GPU 自動降回 CPU
        wants_gpu = bool(self._settings.get("use_gpu", False))
        self._use_gpu: bool = wants_gpu and ocr.gpu_available()
        if wants_gpu and not self._use_gpu:
            # 之前設定過 GPU 但當前環境（CPU 版 EXE）不支援，校正回 CPU
            self._settings["use_gpu"] = False
            settings_mod.save(self._settings)
        self._floating_window: Optional[FloatingWindow] = None

        manual_level = self._settings.get("manual_level")
        if isinstance(manual_level, int) and MIN_LEVEL <= manual_level <= MAX_LEVEL:
            self._tracker.set_manual_level(manual_level)
        default_interval = 0.5 if self._use_gpu else 1.0
        self._interval = float(self._settings.get("interval", default_interval))

        self._build_ui()
        self._refresh_windows()
        self._refresh_level_display()
        self._refresh_interval_buttons()
        self._refresh_engine_buttons()

        # 還原懸浮視窗狀態
        if self._settings.get("floating_visible", False):
            QTimer.singleShot(100, self._show_floating_window)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(500)
        self._ui_timer.timeout.connect(self._tick_ui)
        self._ui_timer.start()

        # 啟動 3 秒後背景檢查更新（避免阻塞啟動）
        QTimer.singleShot(3000, self._check_for_updates)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)

        root.addLayout(self._build_header())

        tabs = QTabWidget()
        tabs.addTab(self._build_tracker_tab(), "即時追蹤")
        tabs.addTab(self._build_setup_tab(), "設定")
        tabs.addTab(self._build_help_tab(), "使用說明")
        root.addWidget(tabs, 1)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._status_label = QLabel("待命")
        status_bar.addWidget(self._status_label, 1)

        # 版權聲明 — 右下角小字
        copyright_label = QLabel(COPYRIGHT)
        copyright_label.setStyleSheet(f"color: {COLORS['fg_dim']}; font-size: 11px;")
        status_bar.addPermanentWidget(copyright_label)

        self._device_label = QLabel("OCR 未啟動")
        self._device_label.setStyleSheet(f"color: {COLORS['fg_muted']};")
        status_bar.addPermanentWidget(self._device_label)

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        # 左側：icon + 標題
        icon_path = _asset_path("app_icon_64.png")
        if icon_path.exists():
            icon_label = QLabel()
            icon_label.setPixmap(QPixmap(str(icon_path)).scaled(
                48, 48, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel(APP_TITLE)
        title.setObjectName("title")
        subtitle = QLabel(f"v{APP_VERSION}  ·  {AUTHOR} 出品")
        subtitle.setObjectName("version_line")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box, 1)

        # 右側：懸浮視窗 / 打賞 / 關於 / 狀態徽章
        right_box = QHBoxLayout()
        right_box.setSpacing(8)

        self._float_btn = QPushButton("懸浮視窗")
        self._float_btn.setCheckable(True)
        self._float_btn.clicked.connect(self._toggle_floating_window)
        right_box.addWidget(self._float_btn)

        donate_btn = QPushButton("贊助作者")
        donate_btn.clicked.connect(self._show_donate_dialog)
        right_box.addWidget(donate_btn)

        about_btn = QPushButton("關於")
        about_btn.clicked.connect(self._show_about_dialog)
        right_box.addWidget(about_btn)

        self._live_badge = QLabel("待命")
        self._live_badge.setObjectName("badge")
        right_box.addWidget(self._live_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(right_box)
        return layout

    def _build_tracker_tab(self) -> QWidget:
        from PySide6.QtWidgets import QProgressBar  # 延後 import 維持原本 imports 整潔
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 控制列（緊貼頂部、無邊框）──
        ctrl_strip = QFrame(page)
        ctrl_strip.setObjectName("strip_thin")
        ctrl_layout = QHBoxLayout(ctrl_strip)
        ctrl_layout.setContentsMargins(14, 10, 14, 10)
        ctrl_layout.setSpacing(8)
        self._start_btn = QPushButton("開始追蹤")
        self._start_btn.setObjectName("primary")
        self._start_btn.clicked.connect(self._start_tracking)
        self._stop_btn = QPushButton("停止")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_tracking)
        self._reset_btn = QPushButton("重置")
        self._reset_btn.setObjectName("danger")
        self._reset_btn.clicked.connect(self._reset_tracking)
        ctrl_layout.addWidget(self._start_btn)
        ctrl_layout.addWidget(self._stop_btn)
        ctrl_layout.addWidget(self._reset_btn)
        ctrl_layout.addStretch(1)
        layout.addWidget(ctrl_strip)

        # ── 等級 + 進度 strip ──
        lv_strip = QFrame(page)
        lv_strip.setObjectName("strip")
        lv_box = QVBoxLayout(lv_strip)
        lv_box.setContentsMargins(20, 16, 20, 14)
        lv_box.setSpacing(6)

        # 上排：Lv | pct
        top_row = QHBoxLayout()
        lv_label_box = QVBoxLayout()
        lv_label_box.setSpacing(2)
        lv_l1 = QLabel("LEVEL")
        lv_l1.setObjectName("stat_label")
        self._level_value = QLabel("—")
        self._level_value.setObjectName("level_value")
        lv_label_box.addWidget(lv_l1)
        lv_label_box.addWidget(self._level_value)
        top_row.addLayout(lv_label_box)

        top_row.addStretch(1)

        pct_label_box = QVBoxLayout()
        pct_label_box.setSpacing(2)
        pct_l1 = QLabel("PROGRESS")
        pct_l1.setObjectName("stat_label")
        pct_l1.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._pct_value = QLabel("—")
        self._pct_value.setObjectName("pct_value")
        self._pct_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        pct_label_box.addWidget(pct_l1)
        pct_label_box.addWidget(self._pct_value)
        top_row.addLayout(pct_label_box)
        lv_box.addLayout(top_row)

        # 細進度條
        self._hero_bar = QProgressBar()
        self._hero_bar.setObjectName("hero_bar")
        self._hero_bar.setRange(0, 10000)
        self._hero_bar.setValue(0)
        self._hero_bar.setTextVisible(False)
        lv_box.addWidget(self._hero_bar)
        layout.addWidget(lv_strip)

        # ── HERO：目前 EXP 巨大字 ──
        hero_strip = QFrame(page)
        hero_strip.setObjectName("strip_hero")
        hero_layout = QVBoxLayout(hero_strip)
        hero_layout.setContentsMargins(20, 28, 20, 28)
        hero_layout.setSpacing(4)
        hero_label = QLabel("CURRENT EXP")
        hero_label.setObjectName("hero_label")
        hero_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cur_exp_lbl = QLabel("—")
        self._cur_exp_lbl.setObjectName("hero_value")
        self._cur_exp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(hero_label)
        hero_layout.addWidget(self._cur_exp_lbl)
        layout.addWidget(hero_strip)

        # ── 二級資訊條（5 個欄位橫向）──
        stats_strip = QFrame(page)
        stats_strip.setObjectName("strip")
        stats_layout = QHBoxLayout(stats_strip)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(0)

        elapsed_c, self._elapsed_value = _make_stat(page, "累計時間")
        total_c, self._total_value = _make_stat(page, "本次累積", "stat_value_accent")
        eta_c, self._eta_level_lbl = _make_stat(page, "升下一級", "stat_value_warn")
        rem_c, self._remaining_exp_lbl = _make_stat(page, "剩餘 EXP")
        state_c, self._sample_state_lbl = _make_stat(page, "辨識狀態")

        for w in (elapsed_c, total_c, eta_c, rem_c, state_c):
            stats_layout.addWidget(w, 1)
        layout.addWidget(stats_strip)

        # ── 速率資訊條（第二行）──
        rates_strip = QFrame(page)
        rates_strip.setObjectName("strip_thin")
        rates_layout = QHBoxLayout(rates_strip)
        rates_layout.setContentsMargins(0, 0, 0, 0)
        rates_layout.setSpacing(0)

        rate1_c, self._rate_1m_lbl = _make_stat(page, "1 分速率", "stat_value_accent")
        rate5r_c, self._rate_5m_real_lbl = _make_stat(page, "5 分累積", "stat_value_accent")
        rate5p_c, self._rate_5m_proj_lbl = _make_stat(page, "5 分推估")
        rate10r_c, self._rate_10m_real_lbl = _make_stat(page, "10 分累積", "stat_value_accent")
        rate10p_c, self._rate_10m_proj_lbl = _make_stat(page, "10 分推估")

        for w in (rate1_c, rate5r_c, rate5p_c, rate10r_c, rate10p_c):
            rates_layout.addWidget(w, 1)
        layout.addWidget(rates_strip)

        layout.addStretch(1)
        return page

    def _build_setup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        win_card, win_layout = _make_card(page, "目標視窗")
        row = QHBoxLayout()
        self._window_combo = QComboBox()
        self._window_combo.setMinimumWidth(360)
        self._window_combo.currentIndexChanged.connect(self._on_window_selected)
        refresh_btn = QPushButton("重新整理")
        refresh_btn.clicked.connect(self._refresh_windows)
        row.addWidget(self._window_combo, 1)
        row.addWidget(refresh_btn)
        win_layout.addLayout(row)
        layout.addWidget(win_card)

        roi_card, roi_layout = _make_card(page, "EXP 區域")
        self._roi_label = QLabel("尚未設定")
        self._roi_label.setStyleSheet(f"color: {COLORS['fg_muted']};")
        roi_row = QHBoxLayout()
        roi_row.addWidget(self._roi_label, 1)
        pick_btn = QPushButton("框選 EXP 區域")
        pick_btn.setObjectName("primary")
        pick_btn.clicked.connect(self._pick_region)
        roi_row.addWidget(pick_btn)
        roi_layout.addLayout(roi_row)
        layout.addWidget(roi_card)

        lvl_roi_card, lvl_roi_layout = _make_card(page, "等級區域（OCR 自動辨識）")
        self._level_roi_label = QLabel("尚未設定（保留則用手動 / 自動推算）")
        self._level_roi_label.setStyleSheet(f"color: {COLORS['fg_muted']};")
        lvl_roi_row = QHBoxLayout()
        lvl_roi_row.addWidget(self._level_roi_label, 1)
        lvl_pick_btn = QPushButton("框選等級區域")
        lvl_pick_btn.setObjectName("primary")
        lvl_pick_btn.clicked.connect(self._pick_level_region)
        lvl_roi_row.addWidget(lvl_pick_btn)
        lvl_roi_layout.addLayout(lvl_roi_row)
        layout.addWidget(lvl_roi_card)

        calib_card, calib_layout = _make_card(page, "校正")
        calib_row = QHBoxLayout()
        level_btn = QPushButton("校正目前等級")
        level_btn.clicked.connect(self._calibrate_level)
        exp_btn = QPushButton("校正目前 EXP")
        exp_btn.clicked.connect(self._calibrate_exp)
        clear_btn = QPushButton("清除所有設定")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(self._clear_settings)
        calib_row.addWidget(level_btn)
        calib_row.addWidget(exp_btn)
        calib_row.addStretch(1)
        calib_row.addWidget(clear_btn)
        calib_layout.addLayout(calib_row)
        layout.addWidget(calib_card)

        interval_card, interval_layout = _make_card(page, "取樣間隔")
        interval_row = QHBoxLayout()
        self._interval_group = QButtonGroup(self)
        self._interval_buttons: dict[float, QPushButton] = {}
        for sec in SAMPLE_INTERVAL_OPTIONS:
            label = f"{sec:g} 秒"
            btn = QPushButton(label)
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, s=sec: self._set_interval(s))
            self._interval_buttons[sec] = btn
            self._interval_group.addButton(btn)
            interval_row.addWidget(btn)
        interval_row.addStretch(1)
        interval_layout.addLayout(interval_row)
        layout.addWidget(interval_card)

        engine_card, engine_layout = _make_card(page, "OCR 引擎")
        engine_row = QHBoxLayout()
        self._engine_group = QButtonGroup(self)
        self._engine_group.setExclusive(True)
        self._engine_cpu_btn = QPushButton("CPU")
        self._engine_cpu_btn.setObjectName("segment")
        self._engine_cpu_btn.setCheckable(True)

        # GPU 按鈕智慧偵測 — 編譯有 CUDA 支援才啟用
        gpu_ok = ocr.gpu_available()
        if gpu_ok:
            self._engine_gpu_btn = QPushButton("GPU")
        else:
            self._engine_gpu_btn = QPushButton("GPU（本版本不支援）")
        self._engine_gpu_btn.setObjectName("segment")
        self._engine_gpu_btn.setCheckable(gpu_ok)
        self._engine_gpu_btn.setEnabled(gpu_ok)

        self._engine_group.addButton(self._engine_cpu_btn)
        if gpu_ok:
            self._engine_group.addButton(self._engine_gpu_btn)
        self._engine_cpu_btn.clicked.connect(lambda: self._set_use_gpu(False))
        if gpu_ok:
            self._engine_gpu_btn.clicked.connect(lambda: self._set_use_gpu(True))
        # 設定當前狀態（受 settings 跟 gpu_ok 影響）
        if self._use_gpu and gpu_ok:
            self._engine_gpu_btn.setChecked(True)
        else:
            self._engine_cpu_btn.setChecked(True)
        engine_row.addWidget(self._engine_cpu_btn)
        engine_row.addWidget(self._engine_gpu_btn)
        engine_row.addStretch(1)
        engine_layout.addLayout(engine_row)
        if gpu_ok:
            engine_hint = QLabel(
                "GPU 推論約 20-40 ms / 張，比 CPU 快 5-10 倍。"
                "切換 GPU 後取樣間隔可調 0.5 秒體驗更即時。"
            )
        else:
            engine_hint = QLabel(
                "本版本只內建 CPU 推論。如需 GPU 版本請另外下載 GPU 打包版（需 NVIDIA 顯卡）。\n"
                "CPU 推論 150-400ms，對楓星 1Hz 取樣完全足夠。"
            )
        engine_hint.setObjectName("subtitle")
        engine_hint.setWordWrap(True)
        engine_layout.addWidget(engine_hint)
        layout.addWidget(engine_card)

        layout.addStretch(1)
        return page

    def _build_help_tab(self) -> QWidget:
        """使用說明分頁 — 完整步驟＋常見問題，內嵌不需另外開檔。"""
        from PySide6.QtWidgets import QScrollArea, QTextBrowser
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {COLORS['panel']};
                color: {COLORS['fg']};
                border: none;
                padding: 20px 28px;
                font-size: 13px;
                line-height: 1.6;
            }}
        """)
        browser.setHtml(self._help_html())
        outer.addWidget(browser)
        return page

    def _help_html(self) -> str:
        """使用說明 HTML — 給內嵌 QTextBrowser 用。"""
        c = COLORS
        return f"""
        <style>
            h2 {{ color: {c['accent']}; font-size: 18px; margin-top: 24px; margin-bottom: 8px; }}
            h3 {{ color: {c['success']}; font-size: 14px; margin-top: 16px; }}
            p, li {{ color: {c['fg']}; font-size: 13px; }}
            .key {{ color: {c['accent']}; font-weight: bold; }}
            .warn {{ color: {c['warning']}; font-weight: bold; }}
            .bad {{ color: {c['danger']}; }}
            .ok {{ color: {c['success']}; }}
            ul {{ margin-left: 0; padding-left: 20px; }}
            code {{ background: {c['panel_2']}; padding: 2px 6px; border-radius: 3px; color: {c['accent']}; }}
        </style>

        <h2>快速開始</h2>
        <p><span class="key">第一次使用</span>，按順序做：</p>
        <ul>
            <li>1. 先把楓星開起來（任何畫面都可以）</li>
            <li>2. 切到「設定」分頁</li>
            <li>3. 上面「目標視窗」會自動帶 <span class="ok">★</span> 標記選好楓星</li>
            <li>4. 點「框選 EXP 區域」</li>
            <li>5. 框出 EXP 那一條 — <span class="warn">含進度條 + 數字一起框</span></li>
            <li>6. 點「框選等級區域」（可選），框出「Lv 158」那塊</li>
            <li>7. 切回「即時追蹤」→ 點「開始追蹤」</li>
        </ul>

        <h2>EXP 區域怎麼框</h2>
        <p><span class="ok">✓ 正確</span>：框整個 EXP 列，含左邊進度條 + 右邊數字</p>
        <p><span class="bad">✗ 錯誤</span>：只框數字緊貼 — paddle OCR 反而會偵測失敗</p>
        <p>上下留 2-5 px 邊，不要框到 HP/MP 那兩列。</p>
        <p>合理 ROI 尺寸大約 <code>500×35</code>，太緊（高度 &lt; 25px）會讀不到。</p>

        <h2>楓星解析度建議</h2>
        <p>建議 <span class="key">1600×900 以上</span>，最好 1920×1080。</p>
        <p>1280×720 EXP 字體太小，OCR 會頻繁失敗（顯示「樣本驗證中」）。</p>

        <h2>狀態欄看不懂？</h2>
        <p>「即時追蹤」分頁右下「資料更新」欄位會顯示工具當下在做什麼：</p>
        <ul>
            <li><b>收集樣本 N/5</b> → 正常，工具在累積 OCR 樣本</li>
            <li><b>同步完成</b> → 正常，剛採用一筆共識結果</li>
            <li><b>起始基準設定</b> → 正常，第一次校準</li>
            <li><b>樣本驗證中</b> → OCR 結果還不穩，工具在等更穩定的取樣（多等幾秒就好）</li>
            <li><b>等待下一筆</b> → 這一筆讀不到，下一筆會繼續</li>
            <li><b>等級切換</b> → 偵測到升級</li>
            <li><b>確認中</b> → 看到數字大跳，等下一筆確認</li>
        </ul>
        <p><span class="key">看到「樣本驗證中」不是壞了</span>，是工具在挑乾淨的樣本。
        慢一點但準是設計目的。</p>

        <h2>速率欄位意思</h2>
        <ul>
            <li><b>1 分速率</b> = 上一個完整 60 秒打的（每分鐘更新一次）</li>
            <li><b>5 分累積</b> = 上一個完整 5 分鐘打的（鎖定值，新區間打完才更新）</li>
            <li><b>10 分累積</b> = 同上但 10 分鐘</li>
            <li><b>5/10 分推估</b> = 用目前速率推估能打多少（~ 代表是預估）</li>
        </ul>

        <h2>懸浮視窗</h2>
        <p>主視窗右上「懸浮視窗」按鈕 → 跳出小視窗</p>
        <ul>
            <li>永遠在最上層、半透明可拖動</li>
            <li>右下角拖拉調整大小</li>
            <li>右鍵選單調透明度、預設尺寸、關閉</li>
        </ul>

        <h2>常見問題</h2>
        <h3>累積 EXP 一直 0</h3>
        <p>看「資料更新」狀態：</p>
        <ul>
            <li>一直「等待下一筆」→ EXP 框錯位置，重框</li>
            <li>一直「樣本驗證中」→ 楓星解析度太小，拉到 1600×900 以上</li>
            <li>「同步完成」但累積還是 0 → 確認你真的在打怪</li>
        </ul>

        <h3>等級顯示錯誤</h3>
        <p>重新「框選等級區域」，框含整個 Lv 數字（不要切太緊）。</p>
        <p>或回「即時追蹤」分頁，「校正目前等級」手動輸入。</p>

        <h3>升下一級時間不準</h3>
        <p>剛開始前 5 分鐘速率還沒穩，跑 10 分鐘後就準。</p>

        <h3>OCR 引擎只能選 CPU？</h3>
        <p>本版本暫時只支援 CPU 推論。CPU 150-400ms 對楓星 1 秒取樣完全夠用。</p>

        <h3>可以同時追蹤多個角色嗎</h3>
        <p>可以。再開一個 EXE 選不同視窗就好。</p>

        <h2>設定檔位置</h2>
        <p>存在 <code>%APPDATA%\\MapleStarTrackerPro\\settings.json</code></p>
        <p>包含視窗選擇、ROI、等級、浮窗位置/大小/透明度。</p>
        <p>要重置所有設定就刪掉這個檔。</p>

        <h2>問題回報</h2>
        <p>截圖 + 「資料更新」狀態 + 操作步驟 → 私訊或 GitHub Issue：</p>
        <p><a href="https://github.com/bmmo472/maplestar-tracker-pro/issues">
            https://github.com/bmmo472/maplestar-tracker-pro/issues
        </a></p>

        <p style="margin-top: 40px; color: {c['fg_dim']}; font-size: 11px;">
            v{APP_VERSION} · 土豆地雷 出品
        </p>
        """

    # ===== 控制邏輯 =====
    def _refresh_windows(self) -> None:
        all_wins = capture.list_windows()
        # 楓星優先：is_maple_window 為 True 的排最上
        maple_wins = [w for w in all_wins if capture.is_maple_window(w.title)]
        other_wins = [w for w in all_wins if not capture.is_maple_window(w.title)]
        self._windows = maple_wins + other_wins

        self._window_combo.clear()
        if not self._windows:
            self._window_combo.addItem("（未偵測到視窗，請先開啟楓星）", None)
            return

        for w in self._windows:
            label = f"★ {w.display}" if capture.is_maple_window(w.title) else w.display
            self._window_combo.addItem(label, w)

        # 優先順序：之前選過的視窗 > 自動選第一個楓星 > 第一個視窗
        last = self._settings.get("window_title")
        chosen_idx = -1
        if last:
            for i, w in enumerate(self._windows):
                if w.title == last:
                    chosen_idx = i
                    break
        if chosen_idx < 0 and maple_wins:
            chosen_idx = 0  # 第一個楓星
        if chosen_idx >= 0:
            self._window_combo.setCurrentIndex(chosen_idx)

    def _on_window_selected(self, index: int) -> None:
        if index < 0 or not self._windows:
            self._selected_window = None
            return
        self._selected_window = self._window_combo.itemData(index)
        if self._selected_window:
            self._settings["window_title"] = self._selected_window.title
            settings_mod.save(self._settings)
            # EXP ROI
            roi_key = f"roi:{self._selected_window.title}"
            saved_roi = self._settings.get(roi_key)
            if saved_roi and len(saved_roi) == 4:
                self._roi = tuple(int(v) for v in saved_roi)
                self._update_roi_label()
            else:
                self._roi = None
                self._roi_label.setText("尚未設定")
            # Level ROI
            level_roi_key = f"level_roi:{self._selected_window.title}"
            saved_lvl_roi = self._settings.get(level_roi_key)
            if saved_lvl_roi and len(saved_lvl_roi) == 4:
                self._level_roi = tuple(int(v) for v in saved_lvl_roi)
            else:
                self._level_roi = None
            self._update_level_roi_label()

    def _pick_region(self) -> None:
        if self._selected_window is None:
            QMessageBox.warning(self, "需要視窗", "請先選擇目標視窗")
            return
        img = capture.grab_window(self._selected_window)
        if img is None:
            QMessageBox.warning(self, "擷取失敗", "無法擷取視窗畫面")
            return
        dlg = RegionPickerDialog(img, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_region:
            self._roi = dlg.result_region
            self._update_roi_label()
            roi_key = f"roi:{self._selected_window.title}"
            self._settings[roi_key] = list(self._roi)
            settings_mod.save(self._settings)

    def _update_roi_label(self) -> None:
        if self._roi:
            x, y, w, h = self._roi
            self._roi_label.setText(f"已設定：{w}×{h} @ ({x}, {y})")
            self._roi_label.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self._roi_label.setText("尚未設定")
            self._roi_label.setStyleSheet(f"color: {COLORS['fg_muted']};")

    def _pick_level_region(self) -> None:
        if self._selected_window is None:
            QMessageBox.warning(self, "需要視窗", "請先選擇目標視窗")
            return
        img = capture.grab_window(self._selected_window)
        if img is None:
            QMessageBox.warning(self, "擷取失敗", "無法擷取視窗畫面")
            return
        dlg = RegionPickerDialog(img, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_region:
            self._level_roi = dlg.result_region
            self._update_level_roi_label()
            key = f"level_roi:{self._selected_window.title}"
            self._settings[key] = list(self._level_roi)
            settings_mod.save(self._settings)
            # 若 worker 在跑，立即套用
            if self._worker:
                self._worker.set_level_roi(self._level_roi)

    def _update_level_roi_label(self) -> None:
        if self._level_roi:
            x, y, w, h = self._level_roi
            self._level_roi_label.setText(f"已設定：{w}×{h} @ ({x}, {y})")
            self._level_roi_label.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self._level_roi_label.setText("尚未設定（保留則用手動 / 自動推算）")
            self._level_roi_label.setStyleSheet(f"color: {COLORS['fg_muted']};")

    def _set_interval(self, seconds: float) -> None:
        self._interval = float(seconds)
        self._settings["interval"] = seconds
        settings_mod.save(self._settings)
        if self._worker:
            self._worker.set_interval(seconds)
        self._refresh_interval_buttons()

    def _refresh_interval_buttons(self) -> None:
        for sec, btn in self._interval_buttons.items():
            btn.setChecked(abs(sec - self._interval) < 1e-3)

    def _set_use_gpu(self, use_gpu: bool) -> None:
        self._use_gpu = use_gpu
        self._settings["use_gpu"] = use_gpu
        settings_mod.save(self._settings)
        self._refresh_engine_buttons()
        if use_gpu and self._interval > 0.5:
            self._set_interval(0.5)
            self.statusBar().showMessage("GPU 模式：取樣間隔自動調為 0.5 秒", 3000)
        elif not use_gpu and self._interval < 1:
            self._set_interval(1)
            self.statusBar().showMessage("CPU 模式：取樣間隔自動調為 1 秒", 4000)
        if self._worker is not None:
            self.statusBar().showMessage(
                "OCR 引擎切換需停止後重啟追蹤才會生效", 4000,
            )

    def _refresh_engine_buttons(self) -> None:
        self._engine_cpu_btn.setChecked(not self._use_gpu)
        self._engine_gpu_btn.setChecked(self._use_gpu)

    def _calibrate_level(self) -> None:
        current = self._tracker.manual_level or 100
        level, ok = QInputDialog.getInt(
            self, "校正等級",
            f"請輸入目前角色等級（{MIN_LEVEL}–{MAX_LEVEL}）：",
            current, MIN_LEVEL, MAX_LEVEL,
        )
        if not ok:
            return
        self._tracker.set_manual_level(level)
        self._settings["manual_level"] = level
        settings_mod.save(self._settings)
        self._refresh_level_display()
        self.statusBar().showMessage(f"已校正等級為 Lv {level}", 3000)

    def _calibrate_exp(self) -> None:
        text, ok = QInputDialog.getText(
            self, "校正目前 EXP",
            "請輸入畫面上目前 EXP（數字，可含逗號）：",
        )
        if not ok or not text.strip():
            return
        try:
            raw = int("".join(ch for ch in text if ch.isdigit()))
        except ValueError:
            QMessageBox.warning(self, "格式錯誤", "請輸入純數字")
            return
        self._tracker.set_manual_exp(raw)
        self.statusBar().showMessage(f"已校正目前 EXP 為 {raw:,}", 3000)

    def _clear_settings(self) -> None:
        confirm = QMessageBox.question(
            self, "清除設定",
            "確定要清除所有儲存的設定嗎？\n（視窗、ROI、等級都會被清掉）",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._settings = {}
        settings_mod.save({})
        self._tracker.set_manual_level(None)
        self._roi = None
        self._update_roi_label()
        self._refresh_level_display()

    def _refresh_level_display(self) -> None:
        lvl = self._tracker.manual_level
        if lvl is None:
            self._level_value.setText("—")
        else:
            auto = " (自動)" if self._tracker.level_auto_detected else ""
            self._level_value.setText(f"Lv {lvl}{auto}")

    # ===== 追蹤啟動 / 停止 =====
    def _start_tracking(self) -> None:
        if self._selected_window is None or self._roi is None:
            QMessageBox.warning(self, "無法啟動", "請先選擇視窗並框選 EXP 區域")
            return
        engine_label = "GPU" if self._use_gpu else "CPU"
        self.statusBar().showMessage(f"正在啟動 OCR 引擎（{engine_label}），請稍候…")
        QApplication.processEvents()
        if not ocr.init_engine(use_gpu=self._use_gpu):
            if self._use_gpu:
                self.statusBar().showMessage("GPU 啟動失敗，自動回退 CPU…")
                QApplication.processEvents()
                if ocr.init_engine(use_gpu=False):
                    QMessageBox.information(
                        self, "已回退 CPU",
                        "GPU 啟動失敗，已自動切換為 CPU。\n"
                        "請確認已安裝 paddlepaddle-gpu 與對應 CUDA。",
                    )
                    self._use_gpu = False
                    self._settings["use_gpu"] = False
                    settings_mod.save(self._settings)
                    self._refresh_engine_buttons()
                else:
                    QMessageBox.critical(self, "OCR 啟動失敗", ocr.last_error() or "未知錯誤")
                    return
            else:
                QMessageBox.critical(self, "OCR 啟動失敗", ocr.last_error() or "未知錯誤")
                return
        self._device_label.setText(ocr.device_status())
        # 第一次 start：重置累積時間並啟動 rate engine session
        # 後續 resume：累積時間不動，只更新 session_start 開始計算這一段
        is_first_start = (self._session_start is None and self._accumulated_elapsed == 0.0)
        if is_first_start:
            self._tracker.rate_engine.start_session()
        else:
            # 從暫停恢復 — 通知 rate engine 把這次暫停時長補進累計
            self._tracker.rate_engine.resume()
        self._session_start = time.time()
        self._worker = _Worker(self._selected_window, self._roi, self._interval,
                               level_roi=self._level_roi)
        self._worker.result_ready.connect(self._on_ocr_result)
        self._worker.level_result_ready.connect(self._on_level_ocr_result)
        self._worker.error_occurred.connect(self._on_ocr_error)
        self._worker_thread = threading.Thread(
            target=self._worker.run, daemon=True, name="TrackerWorker",
        )
        self._worker_thread.start()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._live_badge.setText("追蹤中")
        self._live_badge.setObjectName("badge_live")
        self._live_badge.setStyleSheet(stylesheet())
        self.statusBar().showMessage("追蹤中…")

    def _stop_tracking(self) -> None:
        # 凍結這一段的累積時間
        if self._session_start is not None:
            self._accumulated_elapsed += time.time() - self._session_start
            self._session_start = None
        # 通知 rate engine 進入暫停（停止期間不算進有效追蹤時長）
        self._tracker.rate_engine.pause()
        if self._worker:
            self._worker.stop()
            self._worker = None
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._live_badge.setText("待命")
        self._live_badge.setObjectName("badge")
        self._live_badge.setStyleSheet(stylesheet())
        self.statusBar().showMessage("已停止")

    def _reset_tracking(self) -> None:
        was_running = bool(self._worker)
        if was_running:
            self._stop_tracking()
        self._tracker.reset()
        self._session_start = None
        self._accumulated_elapsed = 0.0

    def _on_ocr_result(self, result) -> None:
        self._tracker.note_capture()
        self._tracker.submit(result)

    def _on_level_ocr_result(self, level) -> None:
        """從等級 ROI OCR 收到結果。連 3 筆同等級才採用。"""
        if self._tracker.submit_level_ocr(level):
            # 採用了新等級 — 同步 UI
            self._refresh_level_display()
            self._settings["manual_level"] = level
            settings_mod.save(self._settings)

    def _on_ocr_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"擷取錯誤：{msg}", 3000)

    # ===== 懸浮視窗 / 對話框 =====
    def _toggle_floating_window(self) -> None:
        if self._floating_window is None or not self._floating_window.isVisible():
            self._show_floating_window()
        else:
            self._hide_floating_window()

    def _show_floating_window(self) -> None:
        if self._floating_window is None:
            self._floating_window = FloatingWindow()
            # 還原上次大小
            size = self._settings.get("floating_size")
            if size and len(size) == 2:
                self._floating_window.resize(int(size[0]), int(size[1]))
            pos = self._settings.get("floating_pos")
            if pos and len(pos) == 2:
                self._floating_window.move(int(pos[0]), int(pos[1]))
            opacity = self._settings.get("floating_opacity")
            if opacity is not None:
                self._floating_window.set_opacity(float(opacity))
            # 接收 resize signal 存 settings
            self._floating_window.resized.connect(self._on_floating_resized)
        self._floating_window.show()
        self._float_btn.setChecked(True)
        self._settings["floating_visible"] = True
        settings_mod.save(self._settings)

    def _on_floating_resized(self, w: int, h: int) -> None:
        self._settings["floating_size"] = [w, h]
        settings_mod.save(self._settings)

    def _hide_floating_window(self) -> None:
        if self._floating_window:
            pos = self._floating_window.pos()
            self._settings["floating_pos"] = [pos.x(), pos.y()]
            self._settings["floating_opacity"] = self._floating_window.opacity()
            self._floating_window.hide()
        self._float_btn.setChecked(False)
        self._settings["floating_visible"] = False
        settings_mod.save(self._settings)

    def _show_about_dialog(self) -> None:
        dlg = AboutDialog(self, version=APP_VERSION, author=AUTHOR)
        dlg.exec()

    def _show_donate_dialog(self) -> None:
        from .about_dialog import DonateDialog
        dlg = DonateDialog(self, author=AUTHOR)
        dlg.exec()

    # ===== UI 刷新 =====
    def _tick_ui(self) -> None:
        last_raw = self._tracker.last_raw
        last_pct = self._tracker.last_pct
        self._cur_exp_lbl.setText(_format_num(last_raw))
        self._pct_value.setText(f"{last_pct:.2f}%" if last_pct is not None else "—")
        if last_pct is not None:
            self._hero_bar.setValue(int(last_pct * 100))
        lvl = self._tracker.manual_level
        if lvl is not None:
            auto = " (自動)" if self._tracker.level_auto_detected else ""
            self._level_value.setText(f"Lv {lvl}{auto}")
        else:
            self._level_value.setText("—")
        self._total_value.setText(_format_num(self._tracker.rate_engine.total_gained))

        elapsed_seconds = self._accumulated_elapsed
        if self._session_start is not None:
            elapsed_seconds += time.time() - self._session_start
        if elapsed_seconds > 0:
            hh, rem = divmod(int(elapsed_seconds), 3600)
            mm, ss = divmod(rem, 60)
            self._elapsed_value.setText(f"{hh:02}:{mm:02}:{ss:02}")
        else:
            self._elapsed_value.setText("00:00:00")

        snap = self._tracker.rate_engine.snapshot()
        rate_1m_snap = snap.get(60)
        rate_1m_rolling = (rate_1m_snap.rate_per_min
                           if rate_1m_snap and rate_1m_snap.rate_per_min and rate_1m_snap.rate_per_min > 0
                           else None)

        # 1 分 / 5 分 / 10 分「實際累積」（跨界鎖定）
        engine = self._tracker.rate_engine
        acc_1m = engine.interval_accumulated(60)
        acc_5m = engine.interval_accumulated(300)
        acc_10m = engine.interval_accumulated(600)

        self._rate_1m_lbl.setText(_format_num(acc_1m))
        self._rate_5m_real_lbl.setText(_format_num(acc_5m))
        self._rate_10m_real_lbl.setText(_format_num(acc_10m))

        # 5 / 10 分推估（用滾動 1m 速率推估，跟累積並列）
        def fmt_proj(minutes: int) -> str:
            if not rate_1m_rolling:
                return "—"
            return f"~{_format_compact(rate_1m_rolling * minutes)}"

        self._rate_5m_proj_lbl.setText(fmt_proj(5))
        self._rate_10m_proj_lbl.setText(fmt_proj(10))

        cap = self._tracker.level_cap
        eta_seconds = None
        remaining = 0
        if cap and last_raw is not None:
            remaining = max(0, cap - last_raw)
            self._remaining_exp_lbl.setText(_format_num(remaining))
            eta_seconds = self._tracker.rate_engine.eta_to_level(remaining)
            self._eta_level_lbl.setText(_format_eta(eta_seconds))
        else:
            self._remaining_exp_lbl.setText("—")
            self._eta_level_lbl.setText("—")

        status = self._tracker.last_status
        self._sample_state_lbl.setText(status.state or "—")

        # 同步懸浮視窗
        if self._floating_window and self._floating_window.isVisible():
            self._floating_window.update_data(
                level=lvl,
                level_auto=self._tracker.level_auto_detected,
                pct=last_pct,
                rate_1m=rate_1m_rolling,
                acc_5m=acc_5m,
                acc_10m=acc_10m,
                eta_seconds=eta_seconds,
                elapsed_seconds=elapsed_seconds,
                total_gained=self._tracker.rate_engine.total_gained,
                tracking=self._worker is not None,
            )

    def _check_for_updates(self) -> None:
        """背景檢查 GitHub 最新 release，有新版彈通知對話框。"""
        # 在另一個 thread 跑網路請求，避免阻塞 UI
        from PySide6.QtCore import QThread, QObject as _QObj, Signal as _Sig
        from tracker import updater

        class _UpdateWorker(_QObj):
            done = _Sig(object)  # UpdateInfo or None

            def __init__(self, version: str):
                super().__init__()
                self._version = version

            def run(self):
                info = updater.check_for_updates(self._version, timeout=5.0)
                self.done.emit(info)

        # 跳過：用戶設定過「不再提醒這個版本」
        skip_version = self._settings.get("update_skip_version")

        thread = QThread(self)
        worker = _UpdateWorker(APP_VERSION)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def on_done(info):
            thread.quit()
            if info is None:
                return  # 網路失敗或解析失敗 — 靜默跳過
            if not info.is_newer:
                return
            if skip_version == info.latest_version:
                return
            self._show_update_dialog(info)

        worker.done.connect(on_done)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # 保留 thread 參考避免 GC
        self._update_thread = thread
        self._update_worker = worker
        thread.start()

    def _show_update_dialog(self, info) -> None:
        """彈出更新通知對話框。"""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QPlainTextEdit
        import webbrowser

        dlg = QDialog(self)
        dlg.setWindowTitle("發現新版本")
        dlg.setMinimumSize(480, 360)
        dlg.setStyleSheet(stylesheet())

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel(f"新版本可用：v{info.latest_version}")
        title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {COLORS['accent']};")
        layout.addWidget(title)

        info_lbl = QLabel(f"目前版本：v{info.current_version}")
        info_lbl.setStyleSheet(f"color: {COLORS['fg_muted']}; font-size: 12px;")
        layout.addWidget(info_lbl)

        notes_lbl = QLabel("更新內容：")
        notes_lbl.setStyleSheet(f"color: {COLORS['fg']}; font-size: 12px; margin-top: 8px;")
        layout.addWidget(notes_lbl)

        notes = QPlainTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(info.release_notes or "（無說明）")
        notes.setStyleSheet(f"""
            background: {COLORS['panel_2']};
            color: {COLORS['fg']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: 10px;
            font-size: 12px;
        """)
        layout.addWidget(notes, 1)

        btn_box = QDialogButtonBox()
        download_btn = btn_box.addButton("前往下載", QDialogButtonBox.ButtonRole.AcceptRole)
        download_btn.setObjectName("primary")
        skip_btn = btn_box.addButton("略過此版本", QDialogButtonBox.ButtonRole.DestructiveRole)
        later_btn = btn_box.addButton("稍後提醒", QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(btn_box)

        def on_download():
            webbrowser.open(info.release_url)
            dlg.accept()

        def on_skip():
            self._settings["update_skip_version"] = info.latest_version
            settings_mod.save(self._settings)
            dlg.reject()

        def on_later():
            dlg.reject()

        download_btn.clicked.connect(on_download)
        skip_btn.clicked.connect(on_skip)
        later_btn.clicked.connect(on_later)
        dlg.exec()

    def closeEvent(self, event):
        if self._worker:
            self._worker.stop()
        if self._floating_window:
            pos = self._floating_window.pos()
            self._settings["floating_pos"] = [pos.x(), pos.y()]
            self._settings["floating_opacity"] = self._floating_window.opacity()
            settings_mod.save(self._settings)
            self._floating_window.close()
        super().closeEvent(event)
