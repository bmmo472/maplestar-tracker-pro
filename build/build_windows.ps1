# MapleStar Tracker Pro - Windows CPU Build Script
# Usage:
#     powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
#
# Output: dist\MapleStarTrackerPro\ folder, share by zipping the folder.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

Write-Host "=== MapleStar Tracker Pro CPU Build ===" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot" -ForegroundColor DarkGray

# 1. venv
$venv = Join-Path $projectRoot ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "`n[1/5] Creating .venv..." -ForegroundColor Yellow
    python -m venv $venv
} else {
    Write-Host "`n[1/5] Using existing .venv" -ForegroundColor Yellow
}
$py = Join-Path $venv "Scripts\python.exe"

# 2. Dependencies (lock numpy 2.x first to avoid version drift)
Write-Host "`n[2/5] Installing dependencies (~500 MB)..." -ForegroundColor Yellow
& $py -m pip install --upgrade pip --quiet
& $py -m pip install "numpy>=2.0,<2.4" --quiet
& $py -m pip install -r requirements.txt --quiet
& $py -m pip install -r build\requirements-build.txt --quiet

$numpyVer = & $py -c "import numpy; print(numpy.__version__)"
Write-Host "      numpy version: $numpyVer" -ForegroundColor DarkGray

# 3. Pre-download PaddleOCR models
$modelsDir = Join-Path $projectRoot "paddlex_models"
if (-not (Test-Path $modelsDir)) {
    Write-Host "`n[3/5] Downloading PaddleOCR models..." -ForegroundColor Yellow
    & $py build\download_models.py

    $cached = Join-Path $env:USERPROFILE ".paddlex\official_models"
    if (Test-Path $cached) {
        New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
        foreach ($name in @("PP-OCRv5_mobile_det", "en_PP-OCRv5_mobile_rec")) {
            $src = Join-Path $cached $name
            if (Test-Path $src) {
                Write-Host "      copying $name" -ForegroundColor DarkGray
                Copy-Item -Recurse -Force $src $modelsDir
            }
        }
    }
} else {
    Write-Host "`n[3/5] Models already exist, skipping" -ForegroundColor Yellow
}

# 4. Sanity check
Write-Host "`n[4/5] Sanity check..." -ForegroundColor Yellow
$check = & $py -c "import paddle, numpy; print(f'paddle {paddle.__version__} numpy {numpy.__version__}')"
Write-Host "      $check" -ForegroundColor DarkGray

# 5. PyInstaller build (onedir mode)
Write-Host "`n[5/5] PyInstaller (onedir mode, 20-30 min)..." -ForegroundColor Yellow

if (Test-Path "build\build") { Remove-Item -Recurse -Force "build\build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath dist `
    --workpath build\build `
    build\tracker_windows.spec

$exeFolder = Join-Path $projectRoot "dist\MapleStarTrackerPro"
$exe = Join-Path $exeFolder "MapleStarTrackerPro.exe"
if (Test-Path $exe) {
    $sizeMB = [math]::Round((Get-ChildItem -Recurse $exeFolder | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "`n[OK] CPU build success!" -ForegroundColor Green
    Write-Host "   Folder: $exeFolder" -ForegroundColor Green
    Write-Host "   Total size: ${sizeMB} MB" -ForegroundColor Green
    Write-Host "`n   -> Test: .\dist\MapleStarTrackerPro\MapleStarTrackerPro.exe" -ForegroundColor Cyan
    Write-Host "   -> Share: zip the whole folder" -ForegroundColor Cyan
} else {
    Write-Host "`n[FAIL] Build failed, no EXE produced" -ForegroundColor Red
    exit 1
}
