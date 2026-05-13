# MapleStar Tracker Pro - One-shot EXE rebuild script
#
# Usage:
#     powershell -ExecutionPolicy Bypass -File build\rebuild.ps1
#
# This script:
#   1. Activates .venv
#   2. Verifies numpy version is correct (2.x)
#   3. Rebuilds EXE incrementally (5-10 min)
#   4. Deletes mypyc .pyd files (chardet + charset_normalizer)
#   5. Verifies the EXE was built successfully
#
# For the very first build, use build_windows.ps1 instead (handles venv setup,
# dependency install, model download).

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

Write-Host "=== MapleStar Tracker Pro Rebuild ===" -ForegroundColor Cyan

# 1. Activate venv
$venv = Join-Path $projectRoot ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "[FAIL] .venv not found. Run build\build_windows.ps1 for the first build." -ForegroundColor Red
    exit 1
}
$py = Join-Path $venv "Scripts\python.exe"

# 2. Verify numpy version (must be 2.x to avoid C ABI mismatch with paddle)
Write-Host "`n[1/4] Verifying dependencies..." -ForegroundColor Yellow
$numpyVer = & $py -c "import numpy; print(numpy.__version__)"
Write-Host "      numpy version: $numpyVer" -ForegroundColor DarkGray
if (-not ($numpyVer -match "^2\.")) {
    Write-Host "      [WARN] numpy is not 2.x, reinstalling..." -ForegroundColor Yellow
    & $py -m pip install "numpy>=2.0,<2.4" --force-reinstall --no-deps --quiet
    $numpyVer = & $py -c "import numpy; print(numpy.__version__)"
    Write-Host "      numpy now: $numpyVer" -ForegroundColor Green
}

# 3. Quick source-mode sanity check
Write-Host "`n[2/4] Source mode sanity check..." -ForegroundColor Yellow
$check = & $py -c "import paddle, numpy; print(f'paddle {paddle.__version__} numpy {numpy.__version__}')" 2>&1
Write-Host "      $check" -ForegroundColor DarkGray

# 4. PyInstaller rebuild
Write-Host "`n[3/4] PyInstaller rebuild (incremental, 5-15 min)..." -ForegroundColor Yellow

# Stop any running EXE instances to avoid file lock
Get-Process MapleStarTrackerPro -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

# Remove dist to force fresh COLLECT
if (Test-Path "dist\MapleStarTrackerPro") {
    Remove-Item -Recurse -Force "dist\MapleStarTrackerPro" -ErrorAction SilentlyContinue
}

& $py -m PyInstaller `
    --noconfirm `
    --distpath dist `
    --workpath build\build `
    build\tracker_windows.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[FAIL] PyInstaller exited with code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

# 5. Delete mypyc .pyd files (chardet + charset_normalizer)
Write-Host "`n[4/4] Removing mypyc compiled modules (force pure-Python fallback)..." -ForegroundColor Yellow

$pydDeleted = 0
foreach ($pkg in @("chardet", "charset_normalizer")) {
    $pkgDir = "dist\MapleStarTrackerPro\_internal\$pkg"
    if (Test-Path $pkgDir) {
        $files = Get-ChildItem -Recurse $pkgDir -Filter "*.pyd" -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            Remove-Item -Force $f.FullName
            $pydDeleted++
        }
    }
}
Write-Host "      Removed $pydDeleted .pyd files" -ForegroundColor DarkGray

# 6. Verify EXE exists
$exe = Join-Path $projectRoot "dist\MapleStarTrackerPro\MapleStarTrackerPro.exe"
if (-not (Test-Path $exe)) {
    Write-Host "`n[FAIL] EXE was not produced" -ForegroundColor Red
    exit 1
}

$exeFolder = Split-Path $exe -Parent
$sizeMB = [math]::Round(
    (Get-ChildItem -Recurse $exeFolder | Measure-Object Length -Sum).Sum / 1MB, 1
)

Write-Host "`n[OK] Rebuild complete!" -ForegroundColor Green
Write-Host "    EXE folder : $exeFolder" -ForegroundColor Green
Write-Host "    Total size : ${sizeMB} MB" -ForegroundColor Green
Write-Host ""
Write-Host "Test: .\dist\MapleStarTrackerPro\MapleStarTrackerPro.exe" -ForegroundColor Cyan
Write-Host "Pack: Compress-Archive -Path dist\MapleStarTrackerPro -DestinationPath MapleStarTrackerPro_v1.1.zip -Force" -ForegroundColor Cyan
