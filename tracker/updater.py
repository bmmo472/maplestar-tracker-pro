"""GitHub Release 更新檢查 — 半自動：只通知不下載。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional
from urllib import request, error


GITHUB_API_LATEST = "https://api.github.com/repos/bmmo472/maplestar-tracker-pro/releases/latest"
RELEASE_PAGE = "https://github.com/bmmo472/maplestar-tracker-pro/releases/latest"


@dataclass
class UpdateInfo:
    latest_version: str       # 例如 "1.4.0"
    current_version: str       # 例如 "1.3.0"
    is_newer: bool             # 是否有更新
    release_url: str           # 下載頁面 URL
    release_notes: str         # release 說明
    zip_url: Optional[str] = None  # 直接下載 zip 的 URL


def _parse_version(v: str) -> tuple[int, ...]:
    """'v1.3.0' / '1.3.0' / 'v1.3.0-beta' → (1, 3, 0)"""
    v = v.lstrip("vV")
    nums = re.findall(r"\d+", v)
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def check_for_updates(current_version: str, timeout: float = 5.0) -> Optional[UpdateInfo]:
    """
    查 GitHub 最新 release。回傳 UpdateInfo（出錯回 None，不要拋例外影響啟動）。
    
    timeout 預設 5 秒，避免網路慢或斷網時卡住程式啟動。
    """
    try:
        req = request.Request(
            GITHUB_API_LATEST,
            headers={"User-Agent": f"MapleStarTrackerPro/{current_version}"},
        )
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    except Exception:
        return None

    tag = data.get("tag_name", "").lstrip("vV")
    if not tag:
        return None

    # 比版本
    cur = _parse_version(current_version)
    latest = _parse_version(tag)
    is_newer = latest > cur

    # 找 zip asset
    zip_url = None
    for asset in data.get("assets") or []:
        name = asset.get("name", "").lower()
        if name.endswith(".zip") and "模型" not in name and "model" not in name:
            zip_url = asset.get("browser_download_url")
            break

    return UpdateInfo(
        latest_version=tag,
        current_version=current_version,
        is_newer=is_newer,
        release_url=data.get("html_url") or RELEASE_PAGE,
        release_notes=(data.get("body") or "")[:1500],  # 限制長度
        zip_url=zip_url,
    )
