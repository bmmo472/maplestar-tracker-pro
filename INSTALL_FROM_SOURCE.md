# 從原始碼安裝 — 給防毒擋下 EXE 的人

如果你下載 EXE 後解壓出來檔案不完整、或 Windows Defender 一直把 EXE 砍掉，可以改用原始碼跑。不用裝太多東西，**約 15 分鐘**搞定。

只在 Windows 上測試過。Python 程式本身跨平台，但打包工具鏈僅限 Windows。

---

## 1. 安裝 Python 3.11 或 3.12

到 https://www.python.org/downloads/windows/ 下載安裝。

⚠ **安裝時務必勾「Add Python to PATH」**，這個忘記勾後面整個流程會卡住。

裝完開 PowerShell 確認：

```
python --version
```

要看到 `Python 3.11.x` 或 `Python 3.12.x`。

---

## 2. 下載原始碼

到 https://github.com/<你的帳號>/maplestar-tracker-pro 按綠色的 **Code → Download ZIP**，解壓到方便的位置，例如桌面。

進入解壓出的資料夾：

```
cd C:\Users\<你的使用者>\Desktop\maplestar-tracker-pro-main
```

---

## 3. 安裝依賴

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install "numpy>=2.0,<2.4"
pip install -r requirements.txt
```

下載量約 500 MB，需要 5–10 分鐘。完成後提示符前面會有 `(.venv)` 字樣。

⚠ 如果 `Activate.ps1` 跳「禁止執行指令碼」錯誤，先跑這行：

```
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

回答 `Y` 後再執行 activate。

---

## 4. 啟動

```
python main.py
```

第一次啟動會自動下載 PaddleOCR 模型（約 30 MB），網路慢可能要等 1–2 分鐘。下次就直接開了。

---

## 之後每次想用

開 PowerShell 進到專案資料夾，跑：

```
.\.venv\Scripts\Activate.ps1
python main.py
```

可以建一個 `.bat` 檔丟桌面快速啟動。

把下面這段存成 `啟動楓星追蹤.bat`：

```
@echo off
cd /d "C:\Users\<你的使用者>\Desktop\maplestar-tracker-pro-main"
call .venv\Scripts\activate.bat
python main.py
```

之後雙擊就跑。

---

## 常見問題

### `python` 找不到指令
Python 安裝時沒勾 PATH，重裝勾上。

### `pip install` 卡很久或下載失敗
網路問題。可以加台灣鏡像：

```
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### `paddle` import 失敗
你的 pip 版本太舊，先升級：

```
python -m pip install --upgrade pip
```

### OCR 看不懂、辨識率很差
框 EXP 區域時要框「整條 EXP 列」，包含綠色進度條 + 數字 + 百分比，不要只框數字。把楓星視窗開大一點，讓 EXP 字至少 18 像素高。

---

## 為什麼用原始碼跑會比較沒問題

- 沒有編譯後的 EXE 可以被防毒誤判
- 模型檔走 pip 從官方 mirror 下載，不會被傳輸過程中破壞
- 缺失任何套件 pip 會直接報錯，不會像 EXE 一樣靜默失敗

缺點是要裝 Python、要等下載、空間占約 4 GB。

---

問題截圖找 [你的聯絡方式]
