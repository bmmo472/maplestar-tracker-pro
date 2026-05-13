"""關於與打賞對話框。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .styles import COLORS, stylesheet


def _asset_path(filename: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "assets" / filename


class AboutDialog(QDialog):
    """關於對話框：版本、作者、致謝。"""

    def __init__(self, parent: Optional[QWidget] = None,
                 version: str = "1.1.0", author: str = "土豆地雷"):
        super().__init__(parent)
        self.setWindowTitle("關於")
        self.setFixedSize(420, 460)
        self.setStyleSheet(stylesheet())

        icon_path = _asset_path("app_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)

        # Logo
        png_path = _asset_path("app_icon_128.png")
        if png_path.exists():
            logo = QLabel()
            logo.setPixmap(QPixmap(str(png_path)).scaled(
                96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)

        # 標題
        title = QLabel("MapleStar Tracker Pro")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {COLORS['fg']}; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(title)

        ver = QLabel(f"v{version}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color: {COLORS['fg_muted']}; font-size: 12px;")
        layout.addWidget(ver)

        layout.addSpacing(6)

        # 說明
        desc = QLabel(
            "楓星 (MapleStory Worlds) 經驗值即時追蹤工具。\n"
            "透過螢幕擷取 + OCR 辨識，計算經驗效率、預估升級時間。"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['fg_muted']}; font-size: 12px;")
        layout.addWidget(desc)

        layout.addSpacing(6)

        # 作者
        author_lbl = QLabel(f"作者　{author}")
        author_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_lbl.setStyleSheet(f"color: {COLORS['fg']}; font-size: 13px;")
        layout.addWidget(author_lbl)

        copyright_lbl = QLabel(f"© 2026 {author}　保留所有權利")
        copyright_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_lbl.setStyleSheet(f"color: {COLORS['fg_dim']}; font-size: 11px;")
        layout.addWidget(copyright_lbl)

        # 致謝
        credits = QLabel(
            "技術棧：PySide6 · PaddleOCR · mss · NumPy"
        )
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credits.setWordWrap(True)
        credits.setStyleSheet(f"color: {COLORS['fg_dim']}; font-size: 10px;")
        layout.addWidget(credits)

        layout.addStretch(1)

        # 按鈕列
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        donate_btn = QPushButton("贊助作者")
        donate_btn.clicked.connect(self._open_donate)
        btn_row.addWidget(donate_btn)
        close_btn = QPushButton("關閉")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._author = author

    def _open_donate(self) -> None:
        dlg = DonateDialog(self, author=self._author)
        dlg.exec()


class DonateDialog(QDialog):
    """打賞對話框：街口支付 QR Code。"""

    def __init__(self, parent: Optional[QWidget] = None, author: str = "土豆地雷"):
        super().__init__(parent)
        self.setWindowTitle("贊助作者")
        self.setFixedSize(420, 620)
        self.setStyleSheet(stylesheet())

        icon_path = _asset_path("app_icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        # 標題
        title = QLabel("請我喝杯飲料")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color: {COLORS['fg']}; font-size: 18px; font-weight: bold;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "如果這個工具對你有幫助、想表達一點謝意，\n"
            "可以用街口支付掃下方 QR Code，或記下帳號轉帳。"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {COLORS['fg_muted']}; font-size: 12px;")
        layout.addWidget(subtitle)

        # QR Code 圖片
        qr_path = _asset_path("donate_jkopay.png")
        if qr_path.exists():
            qr_label = QLabel()
            qr_label.setPixmap(QPixmap(str(qr_path)).scaled(
                340, 340, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qr_label.setStyleSheet(
                f"background-color: white; border-radius: 8px; padding: 8px;"
            )
            layout.addWidget(qr_label)
        else:
            qr_label = QLabel("（QR Code 圖片未找到）")
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qr_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
            layout.addWidget(qr_label)

        # 帳號資訊
        info = QLabel("街口代碼　396\n街口帳號　907515904")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet(
            f"color: {COLORS['fg']}; "
            f"font-family: 'JetBrains Mono', 'Consolas', monospace; "
            f"font-size: 13px;"
        )
        layout.addWidget(info)

        # 感謝詞
        thanks = QLabel(
            "白嫖也沒關係，覺得好用記得幫我推薦給楓星朋友。"
        )
        thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thanks.setWordWrap(True)
        thanks.setStyleSheet(f"color: {COLORS['fg_dim']}; font-size: 11px;")
        layout.addWidget(thanks)

        layout.addStretch(1)

        # 關閉按鈕
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("關閉")
        close_btn.setObjectName("primary")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
