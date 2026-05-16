# MapleStar Tracker Pro v1.3.3 — 一鍵打包 CPU + GPU 兩版
# 用法：powershell -ExecutionPolicy Bypass -File update_release.ps1

$ErrorActionPreference = "Stop"

Write-Host "===== Step 1: 終止舊 process =====" -ForegroundColor Cyan
Get-Process MapleStarTrackerPro -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1

Write-Host ""
Write-Host "===== Step 2: 確認版號 =====" -ForegroundColor Cyan
$ver = (Select-String "APP_VERSION" ui\main_window.py | Select-Object -First 1).Line
Write-Host $ver
if (-not ($ver -match '1\.3\.3')) {
    Write-Host "錯誤: main_window.py 版號不是 1.3.3，請先覆蓋 source" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "===== Step 3: Build CPU 版 =====" -ForegroundColor Cyan
.\.venv\Scripts\Activate.ps1
Remove-Item -Recurse -Force "dist\MapleStarTrackerPro" -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --distpath dist --workpath build\build build\tracker_windows.spec
if ($LASTEXITCODE -ne 0) { Write-Host "CPU build 失敗" -ForegroundColor Red; exit 1 }

# CPU 版砍全部 mypyc (已驗證 OK)
Get-ChildItem -Recurse "dist\MapleStarTrackerPro\_internal\chardet" -Filter "*.pyd" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Recurse "dist\MapleStarTrackerPro\_internal\charset_normalizer" -Filter "*.pyd" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item USAGE.md dist\MapleStarTrackerPro\USAGE.md -ErrorAction SilentlyContinue
Write-Host "  CPU build 完成" -ForegroundColor Green

Write-Host ""
Write-Host "===== Step 4: 壓 CPU zip =====" -ForegroundColor Cyan
Remove-Item -Force "MapleStarTrackerPro_v1.3.3.zip" -ErrorAction SilentlyContinue
Compress-Archive -Path "dist\MapleStarTrackerPro" -DestinationPath "MapleStarTrackerPro_v1.3.3.zip" -CompressionLevel Optimal
$cpuSize = [math]::Round((Get-Item "MapleStarTrackerPro_v1.3.3.zip").Length / 1MB, 1)
Write-Host "  CPU zip: $cpuSize MB" -ForegroundColor Green

Write-Host ""
Write-Host "===== Step 5: Build GPU 版 =====" -ForegroundColor Cyan
deactivate 2>$null

if (-not (Test-Path ".venv-gpu\Scripts\Activate.ps1")) {
    Write-Host "  找不到 .venv-gpu，跳過 GPU build" -ForegroundColor Yellow
    Write-Host "  如要做 GPU 版，先跑 build\build_windows_gpu.ps1"
    Write-Host ""
    Write-Host "=========== 完成 (只做 CPU 版) ===========" -ForegroundColor Green
    exit 0
}

.\.venv-gpu\Scripts\Activate.ps1
Remove-Item -Recurse -Force "dist\MapleStarTrackerPro_GPU" -ErrorAction SilentlyContinue
python -m PyInstaller --noconfirm --distpath dist --workpath build\build-gpu build\tracker_windows_gpu.spec
if ($LASTEXITCODE -ne 0) { Write-Host "GPU build 失敗" -ForegroundColor Red; exit 1 }

# GPU 版智慧砍 - 只砍有 .py fallback 的 .pyd
Write-Host "  智慧砍 mypyc .pyd..." -ForegroundColor Yellow
foreach ($dir in @("chardet", "charset_normalizer")) {
    Get-ChildItem -Recurse "dist\MapleStarTrackerPro_GPU\_internal\$dir" -Filter "*.pyd" -ErrorAction SilentlyContinue | ForEach-Object {
        $pyFile = $_.FullName -replace '\.cp\d+-win_amd64\.pyd$', '.py' -replace '\.pyd$', '.py'
        if (Test-Path $pyFile) {
            Remove-Item $_.FullName -Force
            Write-Host "    Removed: $($_.Name)"
        } else {
            Write-Host "    Kept (no .py): $($_.Name)"
        }
    }
}
Copy-Item USAGE.md dist\MapleStarTrackerPro_GPU\USAGE.md -ErrorAction SilentlyContinue
Write-Host "  GPU build 完成" -ForegroundColor Green

Write-Host ""
Write-Host "===== Step 6: 壓 GPU zip =====" -ForegroundColor Cyan
Remove-Item -Force "MapleStarTrackerPro_v1.3.3_GPU.zip" -ErrorAction SilentlyContinue
Compress-Archive -Path "dist\MapleStarTrackerPro_GPU" -DestinationPath "MapleStarTrackerPro_v1.3.3_GPU.zip" -CompressionLevel Optimal
$gpuSize = [math]::Round((Get-Item "MapleStarTrackerPro_v1.3.3_GPU.zip").Length / 1MB, 1)
Write-Host "  GPU zip: $gpuSize MB" -ForegroundColor Green

Write-Host ""
Write-Host "=========== 全部完成 ===========" -ForegroundColor Green
Write-Host "CPU zip: MapleStarTrackerPro_v1.3.3.zip ($cpuSize MB)"
Write-Host "GPU zip: MapleStarTrackerPro_v1.3.3_GPU.zip ($gpuSize MB)"
