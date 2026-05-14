"""懸浮視窗 — 顯示即時速率與升級 ETA。

特性：
- 永遠最上層
- 無邊框可拖動
- 右下角 size grip 拖拉調整大小
- 右鍵選單調整透明度 / 預設尺寸 / 關閉
- 性能優化：狀態用 dynamic property 切換避免每秒 restyle
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QCursor, QMouseEvent, QResizeEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar, QSizeGrip,
    QVBoxLayout, QWidget,
)

from .styles import COLORS


def _format_eta(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        m, s = divmod(int(seconds), 60)
        return f"{m}m {s:02d}s"
    h, rem = divmod(int(seconds), 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h {m:02d}m"


def _format_elapsed(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02}:{m:02}:{s:02}"


def _format_rate(rate: Optional[float]) -> str:
    if rate is None or rate <= 0:
        return "—"
    return f"{int(rate):,}/m"


def _format_num(n: Optional[int | float]) -> str:
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


class FloatingWindow(QWidget):
    """精簡浮動視窗，可調大小，性能優化。"""

    resized = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # 可調大小
        self.setMinimumSize(180, 220)
        self.setMaximumSize(600, 800)
        self.resize(240, 380)

        self._opacity = 0.92
        self.setWindowOpacity(self._opacity)
        self._drag_offset: Optional[QPoint] = None
        self._last_tracking: Optional[bool] = None  # 狀態切換 cache，避免重複 polish

        self._build_ui()

    def _build_ui(self) -> None:
        c = COLORS
        # 用 dynamic property [live=true/false] 切換顏色，不改 objectName
        self.setStyleSheet(f"""
            QWidget#float_root {{
                background-color: {c['panel']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
            QLabel {{
                color: {c['fg']};
                background: transparent;
                font-family: "Microsoft JhengHei UI", "PingFang TC", sans-serif;
            }}
            QLabel#float_title {{
                color: {c['fg_muted']};
                font-size: 10px;
                letter-spacing: 1px;
            }}
            QLabel#float_status[live="false"] {{
                color: {c['fg_muted']};
                font-size: 10px;
            }}
            QLabel#float_status[live="true"] {{
                color: {c['success']};
                font-size: 10px;
                font-weight: bold;
            }}
            QLabel#float_lvl {{
                color: {c['fg']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 15px;
                font-weight: bold;
            }}
            QLabel#float_pct {{
                color: {c['accent']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 15px;
                font-weight: bold;
            }}
            QLabel#float_rate_label {{
                color: {c['fg_dim']};
                font-size: 10px;
            }}
            QLabel#float_rate_value {{
                color: {c['success']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
                font-weight: bold;
            }}
            QLabel#float_rate_value_primary {{
                color: {c['accent']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 14px;
                font-weight: bold;
            }}
            QLabel#float_eta_value {{
                color: {c['warning']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px;
                font-weight: bold;
            }}
            QLabel#float_total_value {{
                color: {c['purple']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 13px;
                font-weight: bold;
            }}
            QLabel#float_elapsed_value {{
                color: {c['fg']};
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 12px;
            }}
            QProgressBar {{
                background-color: {c['panel_2']};
                border: 1px solid {c['border']};
                border-radius: 3px;
                max-height: 6px;
                text-align: center;
                color: transparent;
            }}
            QProgressBar::chunk {{
                background-color: {c['accent']};
                border-radius: 2px;
            }}
            QSizeGrip {{
                background: transparent;
                width: 14px;
                height: 14px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        root = QFrame(self)
        root.setObjectName("float_root")
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel("MapleStar")
        title_lbl.setObjectName("float_title")
        self._status_lbl = QLabel("待命")
        self._status_lbl.setObjectName("float_status")
        self._status_lbl.setProperty("live", "false")
        header.addWidget(title_lbl)
        header.addStretch(1)
        header.addWidget(self._status_lbl)
        layout.addLayout(header)

        # 等級 + 百分比
        lv_row = QHBoxLayout()
        self._lvl_lbl = QLabel("Lv —")
        self._lvl_lbl.setObjectName("float_lvl")
        self._pct_lbl = QLabel("—")
        self._pct_lbl.setObjectName("float_pct")
        self._pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lv_row.addWidget(self._lvl_lbl)
        lv_row.addStretch(1)
        lv_row.addWidget(self._pct_lbl)
        layout.addLayout(lv_row)

        # 進度條
        self._progress = QProgressBar()
        self._progress.setRange(0, 10000)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        # 速率
        layout.addSpacing(2)
        self._rate_1m_lbl = self._add_row(layout, "1 分速率", primary=True)
        self._rate_5m_lbl = self._add_row(layout, "5 分預估")
        self._rate_10m_lbl = self._add_row(layout, "10 分預估")

        layout.addSpacing(2)
        self._eta_lbl = self._add_row(layout, "升下一級", value_object="float_eta_value")
        self._elapsed_lbl = self._add_row(layout, "累計", value_object="float_elapsed_value")
        self._total_lbl = self._add_row(layout, "累積 EXP", value_object="float_total_value")

        layout.addStretch(1)

        # Size Grip
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        self._size_grip = QSizeGrip(root)
        grip_row.addWidget(
            self._size_grip, 0,
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
        )
        layout.addLayout(grip_row)

    def _add_row(self, layout: QVBoxLayout, label_text: str, *,
                 primary: bool = False,
                 value_object: Optional[str] = None) -> QLabel:
        row = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setObjectName("float_rate_label")
        value = QLabel("—")
        if value_object:
            value.setObjectName(value_object)
        elif primary:
            value.setObjectName("float_rate_value_primary")
        else:
            value.setObjectName("float_rate_value")
        value.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(lbl)
        row.addStretch(1)
        row.addWidget(value)
        layout.addLayout(row)
        return value

    # ===== 拖動 =====
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.resized.emit(self.width(), self.height())

    # ===== 右鍵選單 =====
    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['panel_2']};
                color: {COLORS['fg']};
                border: 1px solid {COLORS['border']};
                padding: 4px;
            }}
            QMenu::item {{ padding: 6px 18px; }}
            QMenu::item:selected {{ background-color: {COLORS['accent']}; color: {COLORS['bg']}; }}
        """)

        opacity_menu = menu.addMenu("透明度")
        for pct in (100, 92, 80, 70):
            act = QAction(f"{pct}%", self)
            act.triggered.connect(lambda _checked=False, p=pct: self.set_opacity(p / 100.0))
            opacity_menu.addAction(act)

        size_menu = menu.addMenu("尺寸預設")
        for label, w, h in (
            ("迷你 (200×280)", 200, 280),
            ("小 (240×380)", 240, 380),
            ("中 (320×460)", 320, 460),
            ("大 (420×560)", 420, 560),
        ):
            act = QAction(label, self)
            act.triggered.connect(
                lambda _checked=False, ww=w, hh=h: self.resize(ww, hh)
            )
            size_menu.addAction(act)

        menu.addSeparator()
        close_action = menu.addAction("關閉懸浮視窗")
        close_action.triggered.connect(self.hide)

        menu.exec(QCursor.pos())

    # ===== Public API =====
    def set_opacity(self, opacity: float) -> None:
        opacity = max(0.4, min(1.0, opacity))
        self._opacity = opacity
        self.setWindowOpacity(opacity)

    def opacity(self) -> float:
        return self._opacity

    def update_data(self, *,
                    level: Optional[int],
                    level_auto: bool,
                    pct: Optional[float],
                    rate_1m: Optional[float],
                    rate_5m: Optional[float],
                    rate_10m: Optional[float],
                    eta_seconds: Optional[float],
                    elapsed_seconds: float,
                    total_gained: Optional[int],
                    tracking: bool) -> None:
        # 狀態：只在變化時 polish，不每秒重 polish
        if tracking != self._last_tracking:
            self._last_tracking = tracking
            if tracking:
                self._status_lbl.setText("追蹤中")
                self._status_lbl.setProperty("live", "true")
            else:
                self._status_lbl.setText("待命")
                self._status_lbl.setProperty("live", "false")
            self._status_lbl.style().unpolish(self._status_lbl)
            self._status_lbl.style().polish(self._status_lbl)

        # 等級
        if level is None:
            self._lvl_lbl.setText("Lv —")
        else:
            suffix = " (自動)" if level_auto else ""
            self._lvl_lbl.setText(f"Lv {level}{suffix}")

        # 百分比 + 進度條
        if pct is not None:
            self._pct_lbl.setText(f"{pct:.2f}%")
            self._progress.setValue(int(pct * 100))
        else:
            self._pct_lbl.setText("—")
            self._progress.setValue(0)

        # 1 分速率（即時，由 main_window 傳入滾動值）
        self._rate_1m_lbl.setText(_format_rate(rate_1m))

        # 5 / 10 分推估（用 1m 推估累積總量）
        if rate_1m and rate_1m > 0:
            self._rate_5m_lbl.setText(f"~{_format_num(rate_1m * 5)}")
            self._rate_10m_lbl.setText(f"~{_format_num(rate_1m * 10)}")
        else:
            self._rate_5m_lbl.setText("—")
            self._rate_10m_lbl.setText("—")

        # ETA / 累計 / 累積
        self._eta_lbl.setText(_format_eta(eta_seconds))
        self._elapsed_lbl.setText(_format_elapsed(elapsed_seconds))
        self._total_lbl.setText(_format_num(total_gained))
