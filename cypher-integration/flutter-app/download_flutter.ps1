# HarBeat - Download Flutter from Tsinghua Mirror (PowerShell)
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "HarBeat - Download Flutter SDK" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if D:\flutter already exists
if (Test-Path "D:\flutter") {
    Write-Host "[WARN] D:\flutter already exists!" -ForegroundColor Yellow
    $confirm = Read-Host "Delete and re-download? (y/n)"
    if ($confirm -eq 'y' -or $confirm -eq 'Y') {
        Write-Host "[CLEAN] Removing old Flutter folder..." -ForegroundColor Yellow
        Remove-Item -Path "D:\flutter" -Recurse -Force
    } else {
        Write-Host "[CANCEL] Aborted" -ForegroundColor Red
        exit 0
    }
}

Write-Host "[DOWNLOAD] Cloning Flutter SDK from Tsinghua mirror..." -ForegroundColor Cyan
Write-Host "This will take 5-15 minutes depending on your network speed..." -ForegroundColor Gray
Write-Host ""

# Clone from Tsinghua mirror
git clone -b stable https://mirrors.tuna.tsinghua.edu.cn/git/flutter-sdk.git D:\flutter

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Clone failed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check:" -ForegroundColor Yellow
    Write-Host "1. Git is installed (https://git-scm.com/download/win)" -ForegroundColor Gray
    Write-Host "2. Network connection is stable" -ForegroundColor Gray
    Write-Host "3. Try again later" -ForegroundColor Gray
    Write-Host ""
    pause
    exit 1
}

Write-Host ""
Write-Host "[OK] Flutter downloaded successfully to D:\flutter" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "1. Add D:\flutter\bin to system PATH" -ForegroundColor White
Write-Host "2. Restart PowerShell" -ForegroundColor White
Write-Host "3. Run: flutter doctor" -ForegroundColor White
Write-Host ""
Write-Host "Opening environment variable settings..." -ForegroundColor Yellow

# Open environment variable settings
rundll32.exe sysdm.cpl,EditEnvironmentVariables

pause
