# MapleStar Tracker Pro - Windows GPU Build Script
# Auto-detects CUDA version, picks matching paddlepaddle-gpu wheel.
# Usage:
#     powershell -ExecutionPolicy Bypass -File build\build_windows_gpu.ps1

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

Write-Host "=== MapleStar Tracker Pro GPU Build ===" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot" -ForegroundColor DarkGray

# 0. Detect CUDA
$cudaIndex = "cu129"
try {
    $smi = nvidia-smi 2>&1 | Out-String
    if ($smi -match "CUDA Version:\s*(\d+)\.(\d+)") {
        $cudaMajor = [int]$Matches[1]
        $cudaMinor = [int]$Matches[2]
        Write-Host "`n[0/5] Detected CUDA $cudaMajor.$cudaMinor" -ForegroundColor Green
        if ($cudaMajor -ge 13) { $cudaIndex = "cu129" }
        elseif ($cudaMajor -eq 12 -and $cudaMinor -ge 9) { $cudaIndex = "cu129" }
        elseif ($cudaMajor -eq 12 -and $cudaMinor -ge 6) { $cudaIndex = "cu126" }
        elseif ($cudaMajor -eq 12) { $cudaIndex = "cu126" }
        elseif ($cudaMajor -eq 11 -and $cudaMinor -ge 8) { $cudaIndex = "cu118" }
        else {
            Write-Host "      [WARN] CUDA too old (< 11.8), upgrade driver" -ForegroundColor Yellow
            exit 1
        }
        Write-Host "      -> wheel: $cudaIndex" -ForegroundColor Cyan
    }
} catch {
    Write-Host "`n[WARN] nvidia-smi not found, defaulting to cu129" -ForegroundColor Yellow
}

# 1. venv
$venv = Join-Path $projectRoot ".venv-gpu"
if (-not (Test-Path $venv)) {
    Write-Host "`n[1/5] Creating .venv-gpu..." -ForegroundColor Yellow
    python -m venv $venv
} else {
    Write-Host "`n[1/5] Using existing .venv-gpu" -ForegroundColor Yellow
}
$py = Join-Path $venv "Scripts\python.exe"

# 2. Dependencies
Write-Host "`n[2/5] Installing dependencies..." -ForegroundColor Yellow
& $py -m pip install --upgrade pip --quiet
& $py -m pip install "numpy>=2.0,<2.4" --quiet
& $py -m pip install -r requirements-gpu.txt --quiet
& $py -m pip install -r build\requirements-build.txt --quiet

$indexUrl = "https://www.paddlepaddle.org.cn/packages/stable/$cudaIndex/"
Write-Host "      paddlepaddle-gpu 3.2.2 ($cudaIndex), 2-3 GB download..." -ForegroundColor DarkGray
& $py -m pip install paddlepaddle-gpu==3.2.2 -i $indexUrl

$numpyVer = & $py -c "import numpy; print(numpy.__version__)"
Write-Host "      numpy version: $numpyVer" -ForegroundColor DarkGray

# 3. Verify GPU
Write-Host "`n[3/5] Verifying GPU..." -ForegroundColor Yellow
$gpuCheck = & $py -c "import paddle; print('OK' if paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0 else 'NO_GPU')"
if ($gpuCheck -match "OK") {
    Write-Host "      [OK] GPU available" -ForegroundColor Green
} else {
    Write-Host "      [WARN] GPU not available: $gpuCheck (app will fallback to CPU)" -ForegroundColor Yellow
}

# 4. Pre-download models
$modelsDir = Join-Path $projectRoot "paddlex_models"
if (-not (Test-Path $modelsDir)) {
    Write-Host "`n[4/5] Downloading PaddleOCR models..." -ForegroundColor Yellow
    & $py build\download_models.py --gpu

    $cached = Join-Path $env:USERPROFILE ".paddlex\official_models"
    if (Test-Path $cached) {
        New-Item -ItemType Directory -Force -Path $modelsDir | Out-Null
        foreach ($name in @("PP-OCRv5_mobile_det", "en_PP-OCRv5_mobile_rec")) {
            $src = Join-Path $cached $name
            if (Test-Path $src) {
                Copy-Item -Recurse -Force $src $modelsDir
            }
        }
    }
} else {
    Write-Host "`n[4/5] Models exist, skipping" -ForegroundColor Yellow
}

# 5. PyInstaller
Write-Host "`n[5/5] PyInstaller (onedir, 25-40 min)..." -ForegroundColor Yellow

if (Test-Path "build\build_gpu") { Remove-Item -Recurse -Force "build\build_gpu" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath dist `
    --workpath build\build_gpu `
    build\tracker_windows_gpu.spec

$exeFolder = Join-Path $projectRoot "dist\MapleStarTrackerPro_GPU"
$exe = Join-Path $exeFolder "MapleStarTrackerPro_GPU.exe"
if (Test-Path $exe) {
    $sizeMB = [math]::Round((Get-ChildItem -Recurse $exeFolder | Measure-Object Length -Sum).Sum / 1MB, 1)
    Write-Host "`n[OK] GPU build success!" -ForegroundColor Green
    Write-Host "   Folder: $exeFolder" -ForegroundColor Green
    Write-Host "   Total size: ${sizeMB} MB" -ForegroundColor Green
} else {
    Write-Host "`n[FAIL] Build failed" -ForegroundColor Red
    exit 1
}
