# HarBeat - Simple APK Build Script (Flutter must be pre-installed)
Write-Host "HarBeat - APK Build Script" -ForegroundColor Cyan
Write-Host ""

# Check Flutter
Write-Host "[CHECK] Checking Flutter installation..." -ForegroundColor Yellow
try {
    flutter --version 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Flutter not found"
    }
    Write-Host "[OK] Flutter is installed" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Flutter is not installed or not in PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "[INFO] Please install Flutter first:" -ForegroundColor Yellow
    Write-Host "   Option 1: Run download_flutter.ps1 (auto-install from Tsinghua mirror)" -ForegroundColor Gray
    Write-Host "   Option 2: Manual install from https://mirrors.tuna.tsinghua.edu.cn" -ForegroundColor Gray
    exit 1
}

Write-Host ""

# Enter project directory (use relative path)
Write-Host "[STEP] Entering project directory..." -ForegroundColor Cyan

# Install deps
Write-Host "[DEPS] Installing dependencies..." -ForegroundColor Yellow
flutter pub get

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Dependencies ready" -ForegroundColor Green
Write-Host ""

# Generate code
Write-Host "[BUILD] Generating code..." -ForegroundColor Yellow
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
    Write-Host "Run 'flutter build apk --release -v' for details" -ForegroundColor Yellow
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
    Write-Host "Location: $PWD\$apkPath" -ForegroundColor Cyan
    Write-Host "Size: $([math]::Round($apkSize, 2)) MB" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    
    # Open folder
    Write-Host "[OPEN] Opening APK folder..." -ForegroundColor Cyan
    explorer.exe "$PWD\build\app\outputs\flutter-apk"
    
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
