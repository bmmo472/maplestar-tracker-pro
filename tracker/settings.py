"""設定儲存（ROI、視窗、間隔、等級…）。寫入 user data dir。"""
from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any


def app_data_dir() -> Path:
    if platform.system() == "Windows":
        base = Path.home() / "AppData" / "Local"
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    d = base / "MapleStarTrackerPro"
    d.mkdir(parents=True, exist_ok=True)
    return d


SETTINGS_PATH = app_data_dir() / "settings.json"


def load() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(data: dict[str, Any]) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
    except Exception:
        pass
