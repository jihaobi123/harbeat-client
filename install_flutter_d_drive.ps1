# HarBeat - Flutter Install via Tsinghua Mirror (D Drive)
Write-Host "HarBeat - Flutter Auto Install (Tsinghua Mirror + D Drive)" -ForegroundColor Cyan
Write-Host ""

$FLUTTER_PATH = "D:lutter"

# Check if Flutter is installed
$flutterInstalled = Test-Path "$FLUTTER_PATHinlutter.bat"

if (-not $flutterInstalled) {
    Write-Host "[WARN] Flutter not found at $FLUTTER_PATH" -ForegroundColor Yellow
    Write-Host ""
    
    $continue = Read-Host "Download Flutter (~500MB) from Tsinghua mirror to D:? (y/n)"
    if ($continue -ne 'y' -and $continue -ne 'Y') {
        Write-Host "[CANCEL] Cancelled" -ForegroundColor Red
        exit 0
    }
    
    Write-Host ""
    Write-Host "[DOWNLOAD] Downloading from Tsinghua mirror..." -ForegroundColor Cyan
    
    $gitInstalled = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitInstalled) {
        Write-Host "[ERROR] Git not installed. Download from https://git-scm.com/download/win" -ForegroundColor Red
        exit 1
    }
    
    # Set China mirror env vars
    $env:PUB_HOSTED_URL = "https://pub.flutter-io.cn"
    $env:FLUTTER_STORAGE_BASE_URL = "https://storage.flutter-io.cn"
    
    Write-Host "[INSTALL] Cloning to $FLUTTER_PATH..." -ForegroundColor Yellow
    
    if (Test-Path $FLUTTER_PATH) {
        Remove-Item -Recurse -Force $FLUTTER_PATH
    }
    
    git clone -b stable https://mirrors.tuna.tsinghua.edu.cn/git/flutter-sdk.git $FLUTTER_PATH
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Clone failed" -ForegroundColor Red
        Write-Host "[INFO] Manual: Download zip from https://mirrors.tuna.tsinghua.edu.cn/flutter/flutter_infra_release/releases/stable/windows/" -ForegroundColor Yellow
        exit 1
    }
    
    $env:Path += ";$FLUTTER_PATHin"
    [Environment]::SetEnvironmentVariable("PUB_HOSTED_URL", "https://pub.flutter-io.cn", "User")
    [Environment]::SetEnvironmentVariable("FLUTTER_STORAGE_BASE_URL", "https://storage.flutter-io.cn", "User")
    
    Write-Host "[OK] Flutter installed to $FLUTTER_PATH" -ForegroundColor Green
    Write-Host ""
    
    flutter precache
    flutter doctor
} else {
    Write-Host "[OK] Flutter already installed at $FLUTTER_PATH" -ForegroundColor Green
    $env:Path += ";$FLUTTER_PATHin"
}

Write-Host ""
Write-Host "[BUILD] Building APK..." -ForegroundColor Cyan

cd "d:\工作\DJ机\harbeat_app"
flutter clean
flutter pub get
flutter build apk --release

$apkPath = "buildpp\outputslutter-apkpp-release.apk"
if (Test-Path $apkPath) {
    $apkSize = (Get-Item $apkPath).Length / 1MB
    Write-Host ""
    Write-Host "Location: $PWD\$apkPath" -ForegroundColor Cyan
    Write-Host "Size: $([math]::Round($apkSize, 2)) MB" -ForegroundColor Cyan
    explorer.exe "$PWDuildpp\outputslutter-apk"
} else {
    Write-Host "[ERROR] APK not found" -ForegroundColor Red
}

Write-Host ""
