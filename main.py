"""MapleStar Tracker Pro — 主程式入口（含 crash logger）。"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

LOG_PATH = Path(os.environ.get("TEMP", os.environ.get("TMP", "."))) / "maplestar_crash.log"


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass
    print(msg, flush=True)


def main() -> int:
    try:
        _log("=== MapleStar Tracker Pro 啟動 ===")
        os.environ.setdefault("FLAGS_use_mkldnn", "False")

        _log("Step 1: import paddle")
        try:
            import paddle
            _log(f"  paddle {paddle.__version__}")
        except Exception as e:
            _log(f"  paddle FAIL (繼續): {e}")

        _log("Step 2: import numpy")
        import numpy
        _log(f"  numpy {numpy.__version__}")

        _log("Step 3: PySide6")
        from PySide6.QtWidgets import QApplication

        _log("Step 4: ui.main_window")
        from ui.main_window import MainWindow

        _log("Step 5: QApplication")
        app = QApplication(sys.argv)
        app.setApplicationName("MapleStar Tracker Pro")

        _log("Step 6: MainWindow()")
        win = MainWindow()

        _log("Step 7: show()")
        win.show()

        _log("Step 8: event loop")
        return app.exec()

    except SystemExit:
        raise
    except BaseException as e:
        _log(f"FATAL: {type(e).__name__}: {e}")
        _log(traceback.format_exc())
        try:
            input("\n按 Enter 鍵結束...")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
