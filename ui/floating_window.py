"""懸浮視窗 — 顯示即時速率與升級 ETA。

特性：
- 永遠最上層（Qt.WindowStaysOnTopHint）
- 無邊框可拖動
- 可調透明度（70-100%）
- 右鍵選單調整透明度與關閉
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QCursor, QMouseEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar, QVBoxLayout, QWidget,
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
    """精簡浮動視窗：等級 / 進度 / 1m·5m·10m 速率 / ETA / 累計時間 / 累積 EXP。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(240)
        self._opacity = 0.92
        self.setWindowOpacity(self._opacity)
        self._drag_offset: Optional[QPoint] = None

        self._build_ui()

    def _build_ui(self) -> None:
        c = COLORS
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
            QLabel#float_status {{
                color: {c['fg_muted']};
                font-size: 10px;
            }}
            QLabel#float_status_live {{
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
        """)

        root = QFrame(self)
        root.setObjectName("float_root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 標題列
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self._title_lbl = QLabel("MAPLESTAR")
        self._title_lbl.setObjectName("float_title")
        self._status_lbl = QLabel("待命")
        self._status_lbl.setObjectName("float_status")
        title_row.addWidget(self._title_lbl)
        title_row.addStretch(1)
        title_row.addWidget(self._status_lbl)
        layout.addLayout(title_row)

        # 等級 + 百分比
        lvl_row = QHBoxLayout()
        lvl_row.setSpacing(8)
        self._lvl_lbl = QLabel("Lv —")
        self._lvl_lbl.setObjectName("float_lvl")
        self._pct_lbl = QLabel("—")
        self._pct_lbl.setObjectName("float_pct")
        self._pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lvl_row.addWidget(self._lvl_lbl)
        lvl_row.addStretch(1)
        lvl_row.addWidget(self._pct_lbl)
        layout.addLayout(lvl_row)

        # 進度條
        self._progress = QProgressBar()
        self._progress.setRange(0, 10000)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        # 速率區
        layout.addSpacing(2)
        self._rate_1m_lbl = self._add_row(layout, "1 分", primary=True)
        self._rate_5m_lbl = self._add_row(layout, "5 分")
        self._rate_10m_lbl = self._add_row(layout, "10 分")

        # 分隔線
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {COLORS['border']}; background-color: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(line)

        self._eta_lbl = self._add_row(layout, "升下一級", value_obj="float_eta_value")
        self._elapsed_lbl = self._add_row(layout, "本次累計", value_obj="float_elapsed_value")
        self._total_lbl = self._add_row(layout, "累積 EXP", value_obj="float_total_value")

    def _add_row(self, layout: QVBoxLayout, label_text: str,
                 primary: bool = False, value_obj: Optional[str] = None) -> QLabel:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label_text)
        lbl.setObjectName("float_rate_label")
        value = QLabel("—")
        if value_obj:
            value.setObjectName(value_obj)
        else:
            value.setObjectName("float_rate_value_primary" if primary else "float_rate_value")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
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
        # 狀態
        if tracking:
            self._status_lbl.setText("追蹤中")
            self._status_lbl.setObjectName("float_status_live")
        else:
            self._status_lbl.setText("待命")
            self._status_lbl.setObjectName("float_status")
        self._status_lbl.setStyleSheet(self._status_lbl.styleSheet())

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

        # 速率
        self._rate_1m_lbl.setText(_format_rate(rate_1m))
        self._rate_5m_lbl.setText(_format_rate(rate_5m))
        self._rate_10m_lbl.setText(_format_rate(rate_10m))

        # ETA / 累計 / 累積
        self._eta_lbl.setText(_format_eta(eta_seconds))
        self._elapsed_lbl.setText(_format_elapsed(elapsed_seconds))
        self._total_lbl.setText(_format_num(total_gained))
