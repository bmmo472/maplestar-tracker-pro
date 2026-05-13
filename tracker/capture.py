"""視窗列舉與螢幕擷取。"""
from __future__ import annotations

import platform
import sys
from dataclasses import dataclass
from typing import Optional

import mss
from PIL import Image

try:
    import pywinctl as pwc
except ImportError:
    pwc = None  # type: ignore[assignment]


@dataclass
class WindowInfo:
    title: str
    x: int
    y: int
    width: int
    height: int
    obj: object  # pywinctl window object

    @property
    def display(self) -> str:
        return f"{self.title}  ({self.width}×{self.height})"


def enable_dpi_awareness() -> None:
    """Windows 高 DPI 必須開，不然截圖座標會錯。"""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def list_windows() -> list[WindowInfo]:
    """列出所有可見視窗。"""
    if pwc is None:
        return []
    out: list[WindowInfo] = []
    try:
        windows = pwc.getAllWindows()
    except Exception:
        return []
    for w in windows:
        try:
            title = w.title or ""
            if not title.strip():
                continue
            if not getattr(w, "visible", True):
                continue
            x, y = int(w.left), int(w.top)
            width, height = int(w.width), int(w.height)
            if width < 50 or height < 50:
                continue
            out.append(WindowInfo(title=title, x=x, y=y,
                                  width=width, height=height, obj=w))
        except Exception:
            continue
    return out


def grab_region(left: int, top: int, width: int, height: int,
                sct: Optional[object] = None) -> Image.Image:
    """擷取螢幕指定矩形區域。傳入 sct 可避免重複開銷。"""
    region = {"left": left, "top": top, "width": width, "height": height}
    if sct is not None:
        shot = sct.grab(region)  # type: ignore[union-attr]
    else:
        with mss.mss() as s:
            shot = s.grab(region)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def grab_window(win: WindowInfo, sct: Optional[object] = None) -> Optional[Image.Image]:
    try:
        # 視窗可能被移動或縮放
        live = win.obj
        x, y = int(live.left), int(live.top)  # type: ignore[attr-defined]
        w, h = int(live.width), int(live.height)  # type: ignore[attr-defined]
    except Exception:
        x, y, w, h = win.x, win.y, win.width, win.height
    if w < 10 or h < 10:
        return None
    return grab_region(x, y, w, h, sct=sct)


def grab_window_roi(win: WindowInfo, ox: int, oy: int, ow: int, oh: int,
                    sct: Optional[object] = None) -> Optional[Image.Image]:
    """在視窗座標下截 ROI（ox/oy 相對於視窗左上）。"""
    try:
        x = int(win.obj.left) + ox  # type: ignore[attr-defined]
        y = int(win.obj.top) + oy   # type: ignore[attr-defined]
    except Exception:
        x = win.x + ox
        y = win.y + oy
    if ow < 1 or oh < 1:
        return None
    return grab_region(x, y, ow, oh, sct=sct)
