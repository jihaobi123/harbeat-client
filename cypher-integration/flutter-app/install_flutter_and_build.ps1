# HarBeat - Flutter Auto Install and APK Build Script (with China Mirror Support)
Write-Host "HarBeat - Flutter Auto Install and APK Build" -ForegroundColor Cyan
Write-Host ""

# Check if Flutter is installed
$flutterInstalled = $false
try {
    $flutterVersion = flutter --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $flutterInstalled = $true
        Write-Host "[OK] Flutter is already installed" -ForegroundColor Green
        Write-Host $flutterVersion[0] -ForegroundColor Gray
    }
} catch {
    $flutterInstalled = $false
}

if (-not $flutterInstalled) {
    Write-Host "[WARN] Flutter not found, starting auto-install..." -ForegroundColor Yellow
    Write-Host ""
    
    # Ask user to continue
    $continue = Read-Host "This will download and install Flutter (~500MB). Continue? (y/n)"
    if ($continue -ne 'y' -and $continue -ne 'Y') {
        Write-Host "[CANCEL] Installation cancelled" -ForegroundColor Red
        Write-Host ""
        Write-Host "[INFO] Manual installation guide:" -ForegroundColor Yellow
        Write-Host "   1. Visit: https://docs.flutter.dev/get-started/install/windows" -ForegroundColor Gray
        Write-Host "   2. Download Flutter SDK" -ForegroundColor Gray
        Write-Host "   3. Extract to C:\flutter" -ForegroundColor Gray
        Write-Host "   4. Add C:\flutter\bin to system PATH" -ForegroundColor Gray
        Write-Host "   5. Re-run this script" -ForegroundColor Gray
        exit 0
    }
    
    Write-Host ""
    Write-Host "[DOWNLOAD] Downloading Flutter from China mirror..." -ForegroundColor Cyan
    
    # Check if Git is installed
    $gitInstalled = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitInstalled) {
        Write-Host "[ERROR] Git is required but not installed" -ForegroundColor Red
        Write-Host "   Download from: https://git-scm.com/download/win" -ForegroundColor Gray
        exit 1
    }
    
    # Set environment variables for China mirror
    Write-Host "[CONFIG] Setting up China mirror URLs..." -ForegroundColor Yellow
    $env:PUB_HOSTED_URL = "https://pub.flutter-io.cn"
    $env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"
    
    # Clone Flutter using Gitee mirror (faster in China)
    Write-Host "[INSTALL] Cloning Flutter SDK from Gitee mirror to C:\flutter..." -ForegroundColor Yellow
    cd C:\
    
    # Try Gitee mirror first
    git clone https://gitee.com/mirrors/flutter.git -b stable
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARN] Gitee mirror failed, trying GitHub with proxy settings..." -ForegroundColor Yellow
        
        # Configure Git for better connectivity
        git config --global http.postBuffer 524288000
        git config --global http.lowSpeedLimit 0
        git config --global http.lowSpeedTime 999999
        
        # Try GitHub
        git clone https://github.com/flutter/flutter.git -b stable
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] Flutter clone failed from all sources" -ForegroundColor Red
            Write-Host ""
            Write-Host "[INFO] Please try manual installation:" -ForegroundColor Yellow
            Write-Host "   1. Download Flutter SDK zip from:" -ForegroundColor Gray
            Write-Host "      https://docs.flutter.dev/get-started/install/windows" -ForegroundColor Gray
            Write-Host "   2. Extract to C:\flutter" -ForegroundColor Gray
            Write-Host "   3. Add C:\flutter\bin to system PATH" -ForegroundColor Gray
            Write-Host "   4. Re-run this script" -ForegroundColor Gray
            exit 1
        }
    }
    
    # Add to PATH (current session)
    $env:Path += ";C:\flutter\bin"
    
    Write-Host "[OK] Flutter installation completed" -ForegroundColor Green
    Write-Host ""
    
    # Precache
    Write-Host "[SETUP] Precaching Flutter components..." -ForegroundColor Yellow
    flutter precache
    
    Write-Host "[OK] Precache completed" -ForegroundColor Green
    Write-Host ""
}

# Enter project directory
Write-Host "[STEP] Entering project directory..." -ForegroundColor Cyan
cd "d:\工作\DJ机\harbeat_app"

# Clean old build
Write-Host "[CLEAN] Cleaning old build..." -ForegroundColor Yellow
flutter clean

# Install dependencies
Write-Host "[DEPS] Installing dependencies..." -ForegroundColor Yellow
flutter pub get

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Dependency installation failed" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] Dependencies installed" -ForegroundColor Green
Write-Host ""

# Generate code
Write-Host "[BUILD] Generating serialization code..." -ForegroundColor Yellow
flutter pub run build_runner build --delete-conflicting-outputs

if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Code generation warning (can be ignored)" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Code generation completed" -ForegroundColor Green
}

Write-Host ""

# Build APK
Write-Host "[BUILD] Building Release APK..." -ForegroundColor Cyan
Write-Host "This may take 5-15 minutes, please wait..." -ForegroundColor Gray
Write-Host ""

flutter build apk --release

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] APK build failed" -ForegroundColor Red
    Write-Host ""
    Write-Host "[INFO] View detailed error:" -ForegroundColor Yellow
    Write-Host "   flutter build apk --release -v" -ForegroundColor Gray
    exit 1
}

# Check APK file
$apkPath = "build\app\outputs\flutter-apk\app-release.apk"
if (Test-Path $apkPath) {
    $apkSize = (Get-Item $apkPath).Length / 1MB
    
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host "[SUCCESS] APK Build Completed!" -ForegroundColor Green
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "APK Location:" -ForegroundColor Cyan
    Write-Host "   $PWD\$apkPath" -ForegroundColor White
    Write-Host ""
    Write-Host "APK Size:" -ForegroundColor Cyan
    Write-Host "   $([math]::Round($apkSize, 2)) MB" -ForegroundColor White
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    
    # Ask for next action
    Write-Host "Choose next action:" -ForegroundColor Yellow
    Write-Host "1. Install to connected device via USB" -ForegroundColor White
    Write-Host "2. Show file location only" -ForegroundColor White
    Write-Host ""
    
    $choice = Read-Host "Enter option (1-2)"
    
    switch ($choice) {
        "1" {
            Write-Host ""
            Write-Host "[CHECK] Checking connected devices..." -ForegroundColor Cyan
            
            $devices = flutter devices 2>&1
            Write-Host $devices
            
            if ($devices -match "android") {
                Write-Host ""
                Write-Host "[INSTALL] Installing to device..." -ForegroundColor Green
                flutter install
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host ""
                    Write-Host "[SUCCESS] Installation completed! Open HarBeat on your phone" -ForegroundColor Green
                } else {
                    Write-Host ""
                    Write-Host "[ERROR] Installation failed" -ForegroundColor Red
                    Write-Host ""
                    Write-Host "[INFO] Please check:" -ForegroundColor Yellow
                    Write-Host "   1. Phone connected via USB" -ForegroundColor Gray
                    Write-Host "   2. USB Debugging enabled on phone" -ForegroundColor Gray
                    Write-Host "   3. USB Debugging authorized on phone" -ForegroundColor Gray
                }
            } else {
                Write-Host ""
                Write-Host "[WARN] No Android device detected" -ForegroundColor Yellow
                Write-Host ""
                Write-Host "[INFO] Please:" -ForegroundColor Yellow
                Write-Host "   1. Connect phone via USB" -ForegroundColor Gray
                Write-Host "   2. Enable USB Debugging (Settings -> Developer Options)" -ForegroundColor Gray
                Write-Host "   3. Authorize USB Debugging on phone" -ForegroundColor Gray
                Write-Host "   4. Re-run this script" -ForegroundColor Gray
            }
        }
        "2" {
            Write-Host ""
            Write-Host "[INFO] Manual installation methods:" -ForegroundColor Yellow
            Write-Host "   1. Copy APK to phone (USB/WeChat/QQ)" -ForegroundColor Gray
            Write-Host "   2. Find APK in phone file manager" -ForegroundColor Gray
            Write-Host "   3. Tap to install" -ForegroundColor Gray
            Write-Host ""
            Write-Host "[OPEN] Opening APK folder..." -ForegroundColor Cyan
            explorer.exe "$PWD\build\app\outputs\flutter-apk"
        }
        default {
            Write-Host ""
            Write-Host "[OPEN] Opening APK folder..." -ForegroundColor Cyan
            explorer.exe "$PWD\build\app\outputs\flutter-apk"
        }
    }
} else {
    Write-Host ""
    Write-Host "[ERROR] APK file not found" -ForegroundColor Red
}

Write-Host ""
Write-Host "[DONE] All tasks completed!" -ForegroundColor Green
