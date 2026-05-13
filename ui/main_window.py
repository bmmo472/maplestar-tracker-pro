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
APP_VERSION = "1.1.0"
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
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, window_info: capture.WindowInfo,
                 roi: tuple[int, int, int, int], interval: float):
        super().__init__()
        self._win = window_info
        self._roi = roi
        self._interval = interval
        self._running = False

    def set_interval(self, seconds: float) -> None:
        self._interval = float(seconds)

    def set_roi(self, roi: tuple[int, int, int, int]) -> None:
        self._roi = roi

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
                except Exception as e:
                    self.error_occurred.emit(str(e))
                wait_until = start + self._interval
                while self._running and time.time() < wait_until:
                    time.sleep(min(0.05, wait_until - time.time()))


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
        self._interval = 1.0
        self._settings = settings_mod.load()
        self._session_start: Optional[float] = None
        self._use_gpu: bool = bool(self._settings.get("use_gpu", False))
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
        tabs.addTab(self._build_diag_tab(), "OCR 診斷")
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
        subtitle = QLabel(f"v{APP_VERSION}  ·  即時辨識經驗值、追蹤效率與升等進度")
        subtitle.setObjectName("subtitle")
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
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)

        ctrl_card, ctrl_layout = _make_card(page, "")
        ctrl_layout.setSpacing(8)
        ctrl_row = QHBoxLayout()
        self._start_btn = QPushButton("開始追蹤")
        self._start_btn.setObjectName("primary")
        self._start_btn.clicked.connect(self._start_tracking)
        self._stop_btn = QPushButton("停止")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop_tracking)
        self._reset_btn = QPushButton("重置")
        self._reset_btn.clicked.connect(self._reset_tracking)
        ctrl_row.addWidget(self._start_btn)
        ctrl_row.addWidget(self._stop_btn)
        ctrl_row.addWidget(self._reset_btn)
        ctrl_row.addStretch(1)
        ctrl_layout.addLayout(ctrl_row)
        layout.addWidget(ctrl_card, 0, 0, 1, 2)

        cur_card, cur_layout = _make_card(page, "目前狀態")
        cur_grid = QGridLayout()
        cur_grid.setSpacing(8)
        cur_value_box = QVBoxLayout()
        l1 = QLabel("目前 EXP")
        l1.setObjectName("metric_label")
        self._cur_exp_lbl = QLabel("—")
        self._cur_exp_lbl.setObjectName("metric_value")
        cur_value_box.addWidget(l1)
        cur_value_box.addWidget(self._cur_exp_lbl)
        cur_grid.addLayout(cur_value_box, 0, 0, 1, 4)

        lvl_container, self._level_value = _make_metric(page, "目前等級")
        pct_container, self._pct_value = _make_metric(page, "進度")
        elapsed_container, self._elapsed_value = _make_metric(page, "累計時間")
        total_container, self._total_value = _make_metric(page, "本次累積 EXP")
        cur_grid.addWidget(lvl_container, 1, 0)
        cur_grid.addWidget(pct_container, 1, 1)
        cur_grid.addWidget(elapsed_container, 1, 2)
        cur_grid.addWidget(total_container, 1, 3)
        cur_layout.addLayout(cur_grid)
        layout.addWidget(cur_card, 1, 0, 1, 2)

        rate_card, rate_layout = _make_card(page, "經驗速率")
        rate_grid = QGridLayout()
        rate_grid.setSpacing(10)
        primary_box = QVBoxLayout()
        l_primary = QLabel("近 1 分速率（即時）")
        l_primary.setObjectName("metric_label")
        self._rate_1m_lbl = QLabel("—")
        self._rate_1m_lbl.setObjectName("rate_primary")
        primary_box.addWidget(l_primary)
        primary_box.addWidget(self._rate_1m_lbl)
        rate_grid.addLayout(primary_box, 0, 0, 1, 3)

        rate5_container, self._rate_5m_lbl = _make_metric(page, "近 5 分速率")
        rate10_container, self._rate_10m_lbl = _make_metric(page, "近 10 分速率")
        rate30_container, self._rate_30m_lbl = _make_metric(page, "近 30 分速率")
        rateavg_container, self._rate_avg_lbl = _make_metric(page, "本次平均")
        rate_grid.addWidget(rate5_container, 1, 0)
        rate_grid.addWidget(rate10_container, 1, 1)
        rate_grid.addWidget(rate30_container, 1, 2)
        rate_grid.addWidget(rateavg_container, 2, 0)
        rate_layout.addLayout(rate_grid)
        layout.addWidget(rate_card, 2, 0, 1, 2)

        eta_card, eta_layout = _make_card(page, "升級預估")
        eta_grid = QGridLayout()
        eta_grid.setSpacing(10)
        eta_container, self._eta_level_lbl = _make_metric(page, "升下一級")
        self._eta_level_lbl.setObjectName("metric_value")
        rem_container, self._remaining_exp_lbl = _make_metric(page, "剩餘 EXP")
        state_container, self._sample_state_lbl = _make_metric(page, "辨識狀態")
        eta_grid.addWidget(eta_container, 0, 0)
        eta_grid.addWidget(rem_container, 1, 0)
        eta_grid.addWidget(state_container, 2, 0)
        eta_layout.addLayout(eta_grid)
        eta_layout.addStretch(1)
        layout.addWidget(eta_card, 0, 2, 3, 1)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)
        layout.setRowStretch(2, 1)
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
        self._engine_gpu_btn = QPushButton("GPU（需 paddlepaddle-gpu）")
        self._engine_gpu_btn.setObjectName("segment")
        self._engine_gpu_btn.setCheckable(True)
        self._engine_group.addButton(self._engine_cpu_btn)
        self._engine_group.addButton(self._engine_gpu_btn)
        self._engine_cpu_btn.clicked.connect(lambda: self._set_use_gpu(False))
        self._engine_gpu_btn.clicked.connect(lambda: self._set_use_gpu(True))
        engine_row.addWidget(self._engine_cpu_btn)
        engine_row.addWidget(self._engine_gpu_btn)
        engine_row.addStretch(1)
        engine_layout.addLayout(engine_row)
        engine_hint = QLabel(
            "GPU 推論約 30ms/張、CPU 約 150–400ms。GPU 版需安裝 paddlepaddle-gpu 與對應 CUDA。"
            "若 GPU 啟動失敗會自動回退 CPU。"
        )
        engine_hint.setObjectName("subtitle")
        engine_hint.setWordWrap(True)
        engine_layout.addWidget(engine_hint)
        layout.addWidget(engine_card)

        layout.addStretch(1)
        return page

    def _build_diag_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(12)

        stat_card, stat_layout = _make_card(page, "統計")
        stat_grid = QGridLayout()
        stat_grid.setSpacing(10)
        c1, self._stat_capture_lbl = _make_metric(page, "取樣次數")
        c2, self._stat_ok_lbl = _make_metric(page, "成功辨識")
        c3, self._stat_ignored_lbl = _make_metric(page, "已忽略")
        c4, self._stat_levelup_lbl = _make_metric(page, "升級次數")
        stat_grid.addWidget(c1, 0, 0)
        stat_grid.addWidget(c2, 0, 1)
        stat_grid.addWidget(c3, 0, 2)
        stat_grid.addWidget(c4, 0, 3)
        stat_layout.addLayout(stat_grid)
        layout.addWidget(stat_card)

        last_card, last_layout = _make_card(page, "最後一次 OCR")
        self._last_ocr_text = QTextEdit()
        self._last_ocr_text.setReadOnly(True)
        self._last_ocr_text.setMaximumHeight(180)
        self._last_ocr_text.setPlaceholderText("尚未取樣")
        last_layout.addWidget(self._last_ocr_text)
        layout.addWidget(last_card)

        corr_card, corr_layout = _make_card(page, "修正記錄")
        self._corrections_text = QTextEdit()
        self._corrections_text.setReadOnly(True)
        self._corrections_text.setPlaceholderText("尚無修正")
        corr_layout.addWidget(self._corrections_text)
        layout.addWidget(corr_card, 1)
        return page

    # ===== 控制邏輯 =====
    def _refresh_windows(self) -> None:
        self._windows = capture.list_windows()
        self._window_combo.clear()
        if not self._windows:
            self._window_combo.addItem("（無可用視窗）", None)
            return
        for w in self._windows:
            self._window_combo.addItem(w.display, w)
        last = self._settings.get("window_title")
        if last:
            for i, w in enumerate(self._windows):
                if w.title == last:
                    self._window_combo.setCurrentIndex(i)
                    break

    def _on_window_selected(self, index: int) -> None:
        if index < 0 or not self._windows:
            self._selected_window = None
            return
        self._selected_window = self._window_combo.itemData(index)
        if self._selected_window:
            self._settings["window_title"] = self._selected_window.title
            settings_mod.save(self._settings)
            roi_key = f"roi:{self._selected_window.title}"
            saved_roi = self._settings.get(roi_key)
            if saved_roi and len(saved_roi) == 4:
                self._roi = tuple(int(v) for v in saved_roi)
                self._update_roi_label()
            else:
                self._roi = None
                self._roi_label.setText("尚未設定")

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
        self._session_start = time.time()
        self._tracker.rate_engine.start_session()
        self._worker = _Worker(self._selected_window, self._roi, self._interval)
        self._worker.result_ready.connect(self._on_ocr_result)
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

    def _on_ocr_result(self, result) -> None:
        self._tracker.note_capture()
        self._tracker.submit(result)

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
            pos = self._settings.get("floating_pos")
            if pos and len(pos) == 2:
                self._floating_window.move(int(pos[0]), int(pos[1]))
            opacity = self._settings.get("floating_opacity")
            if opacity is not None:
                self._floating_window.set_opacity(float(opacity))
        self._floating_window.show()
        self._float_btn.setChecked(True)
        self._settings["floating_visible"] = True
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
        lvl = self._tracker.manual_level
        if lvl is not None:
            auto = " (自動)" if self._tracker.level_auto_detected else ""
            self._level_value.setText(f"Lv {lvl}{auto}")
        else:
            self._level_value.setText("偵測中…")
        self._total_value.setText(_format_num(self._tracker.rate_engine.total_gained))

        elapsed_seconds = 0.0
        if self._session_start:
            elapsed_seconds = time.time() - self._session_start
            hh, rem = divmod(int(elapsed_seconds), 3600)
            mm, ss = divmod(rem, 60)
            self._elapsed_value.setText(f"{hh:02}:{mm:02}:{ss:02}")
        else:
            self._elapsed_value.setText("00:00:00")

        snap = self._tracker.rate_engine.snapshot()

        def fmt_rate(window_s: int) -> str:
            s = snap.get(window_s)
            if not s or s.rate_per_min is None or s.rate_per_min <= 0:
                return "—"
            suffix = "" if s.saturated else " *"
            return f"{int(s.rate_per_min):,}/分{suffix}"

        self._rate_1m_lbl.setText(fmt_rate(60))
        self._rate_5m_lbl.setText(fmt_rate(300))
        self._rate_10m_lbl.setText(fmt_rate(600))
        self._rate_30m_lbl.setText(fmt_rate(1800))
        avg = self._tracker.rate_engine.session_average()
        self._rate_avg_lbl.setText(f"{int(avg):,}/分" if avg else "—")

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

        self._stat_capture_lbl.setText(_format_num(self._tracker.capture_count))
        self._stat_ok_lbl.setText(_format_num(self._tracker.recognized_count))
        self._stat_ignored_lbl.setText(_format_num(self._tracker.ignored_count))
        self._stat_levelup_lbl.setText(_format_num(self._tracker.level_up_count))

        ocr_res = self._tracker.last_ocr
        if ocr_res:
            lines = [
                f"來源：{ocr_res.source or 'N/A'}",
                f"OCR 原文：{ocr_res.raw_text}",
                f"raw = {ocr_res.raw}   pct = {ocr_res.pct}",
                f"視覺 pct = {ocr_res.visual_pct:.2f}%" if ocr_res.visual_pct else "視覺 pct = —",
                f"信心 = {ocr_res.confidence:.2f}   共識 = {ocr_res.consensus}/{ocr_res.total_votes}",
            ]
            if ocr_res.error:
                lines.append(f"錯誤：{ocr_res.error}")
            self._last_ocr_text.setPlainText("\n".join(lines))

        if status.corrections:
            self._corrections_text.append(
                f"[{time.strftime('%H:%M:%S')}] {' / '.join(status.corrections)}"
            )

        # 同步懸浮視窗
        if self._floating_window and self._floating_window.isVisible():
            self._floating_window.update_data(
                level=lvl,
                level_auto=self._tracker.level_auto_detected,
                pct=last_pct,
                rate_1m=snap.get(60).rate_per_min if snap.get(60) else None,
                rate_5m=snap.get(300).rate_per_min if snap.get(300) else None,
                rate_10m=snap.get(600).rate_per_min if snap.get(600) else None,
                eta_seconds=eta_seconds,
                elapsed_seconds=elapsed_seconds,
                total_gained=self._tracker.rate_engine.total_gained,
                tracking=self._worker is not None,
            )

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
