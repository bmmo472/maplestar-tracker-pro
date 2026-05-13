"""ROI 區域選取對話框 — 在視窗截圖上拖選矩形。"""
from __future__ import annotations

from typing import Optional

from PIL import Image
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)


class _Canvas(QWidget):
    """繪製截圖 + 拖選矩形。"""
    selection_changed = Signal(QRect)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self._rect: Optional[QRect] = None
        self._start: Optional[QPoint] = None
        self.setMouseTracking(True)
        self.setMinimumSize(pixmap.width(), pixmap.height())

    def sizeHint(self):
        return self._pixmap.size()

    def selection(self) -> Optional[QRect]:
        return self._rect

    def set_selection(self, rect: QRect) -> None:
        self._rect = rect.normalized()
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        if self._rect is not None:
            # 暗化未選取區域
            painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
            overlay_color = self.palette().window().color()
            overlay_color.setAlpha(120)
            painter.fillRect(self.rect(), overlay_color)
            painter.drawPixmap(self._rect, self._pixmap, self._rect)
            pen = QPen(Qt.GlobalColor.cyan, 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._rect = QRect(self._start, self._start)
            self.update()

    def mouseMoveEvent(self, event):
        if self._start is None:
            return
        cur = event.position().toPoint()
        # 限制在 pixmap 內
        cur.setX(max(0, min(self._pixmap.width() - 1, cur.x())))
        cur.setY(max(0, min(self._pixmap.height() - 1, cur.y())))
        self._rect = QRect(self._start, cur).normalized()
        self.update()
        self.selection_changed.emit(self._rect)

    def mouseReleaseEvent(self, _event):
        self._start = None


def _pil_to_qpixmap(image: Image.Image) -> QPixmap:
    rgb = image.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class RegionPickerDialog(QDialog):
    """彈出視窗讓使用者在截圖上拖選 ROI。"""

    def __init__(self, snapshot: Image.Image, parent=None,
                 title: str = "框選 EXP 區域"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._snapshot = snapshot
        self._result: Optional[tuple[int, int, int, int]] = None

        # 必要時縮放到適合螢幕
        max_w, max_h = 1400, 900
        sw, sh = snapshot.width, snapshot.height
        scale = min(1.0, max_w / sw, max_h / sh)
        if scale < 1.0:
            display = snapshot.resize((int(sw * scale), int(sh * scale)),
                                      Image.Resampling.LANCZOS)
        else:
            display = snapshot
        self._scale = scale
        pixmap = _pil_to_qpixmap(display)

        self._canvas = _Canvas(pixmap)
        self._canvas.selection_changed.connect(self._on_selection)

        self._coord_lbl = QLabel("請用滑鼠左鍵在畫面上拖出 EXP 區域", self)
        self._coord_lbl.setObjectName("subtitle")
        self._ok_btn = QPushButton("確定")
        self._ok_btn.setObjectName("primary")
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addWidget(self._coord_lbl, 1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(self._ok_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self._canvas, 1)
        layout.addLayout(button_row)

    def _on_selection(self, rect: QRect):
        if rect.width() < 10 or rect.height() < 5:
            self._ok_btn.setEnabled(False)
            return
        # 反算回原始解析度
        x = int(rect.x() / self._scale)
        y = int(rect.y() / self._scale)
        w = int(rect.width() / self._scale)
        h = int(rect.height() / self._scale)
        self._result = (x, y, w, h)
        self._coord_lbl.setText(f"已框選：{w}×{h} @ ({x}, {y})")
        self._ok_btn.setEnabled(True)

    def _accept(self):
        if self._result is None:
            self.reject()
        else:
            self.accept()

    @property
    def result_region(self) -> Optional[tuple[int, int, int, int]]:
        return self._result
