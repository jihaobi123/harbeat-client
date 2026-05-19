# HarBeat - Fixed APK Build Script (Handles disk space and path issues)
Write-Host "HarBeat - APK Build Script (Fixed Version)" -ForegroundColor Cyan
Write-Host ""

# Check if Flutter is installed
$flutterInstalled = $false
try {
    $flutterVersion = flutter --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $flutterInstalled = $true
        Write-Host "[OK] Flutter is already installed" -ForegroundColor Green
    }
} catch {
    $flutterInstalled = $false
}

if (-not $flutterInstalled) {
    Write-Host "[ERROR] Flutter is not installed" -ForegroundColor Red
    Write-Host ""
    Write-Host "[INFO] Due to disk space issues on C:, please install Flutter manually:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Step 1: Free up disk space on C: drive (need at least 5GB free)" -ForegroundColor White
    Write-Host "Step 2: Download Flutter SDK from:" -ForegroundColor White
    Write-Host "   https://mirrors.tuna.tsinghua.edu.cn/flutter/flutter_infra_release/releases/stable/windows/" -ForegroundColor Gray
    Write-Host "Step 3: Extract to D:\flutter (not C:\flutter to save space)" -ForegroundColor White
    Write-Host "Step 4: Add D:\flutter\bin to system PATH" -ForegroundColor White
    Write-Host "Step 5: Restart PowerShell and run: .\build_apk_simple.ps1" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Use UTF8 encoding for Chinese paths
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$projectPath = "d:\工作\DJ机\harbeat_app"

# Verify project path exists
if (-not (Test-Path $projectPath)) {
    Write-Host "[ERROR] Project directory not found: $projectPath" -ForegroundColor Red
    exit 1
}

# Enter project directory
Write-Host "[STEP] Entering project directory..." -ForegroundColor Cyan
Set-Location $projectPath

# Clean old build
Write-Host "[CLEAN] Cleaning old build..." -ForegroundColor Yellow
flutter clean

# Install dependencies
Write-Host "[DEPS] Installing dependencies..." -ForegroundColor Yellow
flutter pub get

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Dependency installation failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "[INFO] Try clearing cache:" -ForegroundColor Yellow
    Write-Host "   flutter pub cache repair" -ForegroundColor Gray
    exit 1
}

Write-Host "[OK] Dependencies installed" -ForegroundColor Green
Write-Host ""

# Generate code
Write-Host "[BUILD] Generating serialization code..." -ForegroundColor Yellow
flutter pub run build_runner build --delete-conflicting-outputs 2>&1 | Out-Null

Write-Host ""

# Build APK
Write-Host "[BUILD] Building Release APK..." -ForegroundColor Cyan
Write-Host "This may take 5-15 minutes..." -ForegroundColor Gray
Write-Host ""

flutter build apk --release

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Build failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "[INFO] View detailed error:" -ForegroundColor Yellow
    Write-Host "   flutter build apk --release -v" -ForegroundColor Gray
    exit 1
}

# Success
$apkPath = "build\app\outputs\flutter-apk\app-release.apk"
if (Test-Path $apkPath) {
    $apkSize = (Get-Item $apkPath).Length / 1MB
    
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host "[SUCCESS] APK Built Successfully!" -ForegroundColor Green
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "APK Location:" -ForegroundColor Cyan
    Write-Host "   $projectPath\$apkPath" -ForegroundColor White
    Write-Host ""
    Write-Host "APK Size:" -ForegroundColor Cyan
    Write-Host "   $([math]::Round($apkSize, 2)) MB" -ForegroundColor White
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    
    # Open folder
    Write-Host "[OPEN] Opening APK folder..." -ForegroundColor Cyan
    explorer.exe "$projectPath\build\app\outputs\flutter-apk"
    
    Write-Host ""
    Write-Host "[INFO] To install on phone:" -ForegroundColor Yellow
    Write-Host "   Method 1: USB - flutter install" -ForegroundColor Gray
    Write-Host "   Method 2: WeChat/QQ - Send APK to phone" -ForegroundColor Gray
    Write-Host "   Method 3: HTTP Server - python -m http.server 8080" -ForegroundColor Gray
} else {
    Write-Host "[ERROR] APK file not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "[DONE] Completed!" -ForegroundColor Green
