# MapleStar Tracker Pro

楓星 (MapleStory Worlds) 經驗值追蹤工具。透過螢幕擷取與 OCR 即時讀取 EXP 條，計算累積速率、預估升級時間。

桌面應用，本機運算，不需登入。

## 介面

主視窗：即時追蹤分頁顯示等級、進度、1/5/10/30 分鐘速率與 ETA。設定分頁管理目標視窗、ROI、取樣間隔與 OCR 引擎選擇。OCR 診斷分頁可看單次辨識細節，方便除錯。

懸浮視窗：可固定在畫面上層的小窗，顯示同樣的即時數據。練功時擺在角落不擋畫面，右鍵可調透明度。

## 技術細節

- 螢幕擷取：mss + pywinctl，支援 DPI awareness
- OCR：PaddleOCR 3.5 (PP-OCRv5_mobile)
- 多前處理候選圖投票：原圖 / 去綠條 / 放大三組各跑一次 OCR 再投票
- OCR 結果與視覺進度條交叉驗證，差距過大降低信心
- 自動等級偵測：連續 3 筆樣本投票確認
- 升級事件偵測：EXP 大跌或視覺 % 從高到低
- 多時間窗速率：1 / 5 / 10 / 30 分鐘 + Session 平均
- UI：PySide6 + Tokyo Night 配色
- GPU 推論約 30ms/張，CPU 約 150–400ms

## 從原始碼執行

需要 Python 3.11 或 3.12。

```
git clone https://github.com/<your-username>/maplestar-tracker-pro.git
cd maplestar-tracker-pro
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # Windows
pip install "numpy>=2.0,<2.4"
pip install -r requirements.txt
python main.py
```

GPU 版本（NVIDIA 顯卡 + CUDA 11.8 / 12.6 / 12.9）：

```
pip install -r requirements-gpu.txt
pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
python main.py
```

## 打包成 EXE

打包成單一資料夾分發給沒裝 Python 的使用者。Windows 環境：

```
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
```

腳本會自動：

1. 建立或重用 `.venv`
2. 安裝依賴（鎖定 numpy 2.x 避免版本飄移）
3. 預先下載 PaddleOCR 模型到 `paddlex_models/`
4. PyInstaller onedir 模式打包

輸出在 `dist\MapleStarTrackerPro\`，整個資料夾壓 zip 分發即可。

打包時會踩到的雷與對應修法都寫在 `build/tracker_windows.spec` 的註解中，包含 numpy CPU dispatcher tracer 衝突、chardet mypyc segfault、paddlex importlib.metadata 檢查、setuptools vendor data 等問題。

## 使用流程

1. 啟動程式，選擇楓星視窗
2. 設定 → 框選 EXP 區域（整條，含進度條與數字）
3. 設定 → 校正目前等級（可省略，會自動偵測）
4. 即時追蹤 → 開始追蹤

第一次按開始追蹤需 5–10 秒載入 PaddleOCR 模型。後續即時追蹤每秒擷取一次。

## 設定檔位置

`%LOCALAPPDATA%\MapleStarTrackerPro\settings.json` 存目標視窗名稱、各視窗 ROI、校正等級、取樣間隔、懸浮視窗位置與透明度。

## 已知問題

- 楓星全螢幕獨佔模式下，懸浮視窗會被遊戲蓋過。請改用「無邊框視窗模式」
- PyInstaller 打包的 EXE 偶爾被 Windows Defender 誤判，需手動加白名單
- 首次啟動 EXE 載入時間較長（解壓 PaddleOCR 模型約 5–10 秒）

## 專案結構

```
maplestar_pro/
├── main.py                       入口（含 crash logger）
├── tracker/
│   ├── exp_table.py              Lv 10-199 經驗表
│   ├── preprocess.py             去綠條、進度條像素 %
│   ├── parser.py                 OCR 文字 → (raw, pct)
│   ├── ocr.py                    PaddleOCR + 多候選圖投票
│   ├── corrector.py              修正 pipeline
│   ├── rate.py                   多時間窗速率
│   ├── tracker.py                主狀態機
│   ├── capture.py                mss + pywinctl + DPI awareness
│   └── settings.py               設定 I/O
├── ui/
│   ├── main_window.py            主視窗
│   ├── floating_window.py        懸浮視窗
│   ├── about_dialog.py           關於 + 打賞對話框
│   ├── region_picker.py          ROI 拖選
│   └── styles.py                 Tokyo Night QSS
├── data/maplestar_exp.json       經驗表資料
├── assets/                       icon、QR Code 圖片
├── build/
│   ├── tracker_windows.spec      CPU 版 PyInstaller spec
│   ├── tracker_windows_gpu.spec  GPU 版 PyInstaller spec
│   ├── runtime_hook.py           PyInstaller runtime hook
│   ├── version_info.txt          EXE 屬性版本資訊
│   ├── download_models.py        模型預下載腳本
│   ├── build_windows.ps1         CPU 打包腳本
│   └── build_windows_gpu.ps1     GPU 打包腳本
├── requirements.txt              CPU 依賴
├── requirements-gpu.txt          GPU 依賴
└── README.md
```

## License

個人使用、非商業用途自由使用。商業用途請聯絡作者。

## 作者

土豆地雷

Copyright (c) 2026 土豆地雷
