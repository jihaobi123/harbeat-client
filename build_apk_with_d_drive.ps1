# Flutter APK Build Script - Use D Drive Cache
# Usage: .\build_apk_with_d_drive.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Flutter APK Build (Using D Drive Cache)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set environment variables to redirect Gradle and Pub cache to D drive
$env:GRADLE_USER_HOME = "D:\FlutterCache\.gradle"
$env:PUB_CACHE = "D:\FlutterCache\.pub-cache"
$env:ANDROID_HOME = "D:\FlutterCache\.android\sdk"
$env:ANDROID_SDK_ROOT = "D:\FlutterCache\.android\sdk"

Write-Host "[1/5] Environment variables set:" -ForegroundColor Green
Write-Host "  GRADLE_USER_HOME = $env:GRADLE_USER_HOME" -ForegroundColor Gray
Write-Host "  PUB_CACHE = $env:PUB_CACHE" -ForegroundColor Gray
Write-Host "  ANDROID_HOME = $env:ANDROID_HOME" -ForegroundColor Gray
Write-Host "  ANDROID_SDK_ROOT = $env:ANDROID_SDK_ROOT" -ForegroundColor Gray
Write-Host ""

# Check D drive space
Write-Host "[2/5] Checking D drive space..." -ForegroundColor Yellow
$dDrive = Get-PSDrive D
$freeSpaceGB = [math]::Round($dDrive.Free / 1GB, 2)
Write-Host "  D Drive free space: ${freeSpaceGB} GB" -ForegroundColor Gray

if ($freeSpaceGB -lt 10) {
    Write-Host "  WARNING: D drive has less than 10GB free space!" -ForegroundColor Red
    $continue = Read-Host "Continue anyway? (y/n)"
    if ($continue -ne 'y') {
        Write-Host "Build cancelled" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  OK: D drive has sufficient space" -ForegroundColor Green
}
Write-Host ""

# Change to project directory (use script directory)
$projectPath = $PSScriptRoot
Write-Host "[3/5] Project directory: $projectPath" -ForegroundColor Yellow
Set-Location $projectPath

# Clean old build files
Write-Host "[4/5] Cleaning old build files..." -ForegroundColor Yellow
flutter clean
Write-Host ""

# Get dependencies
Write-Host "[5/5] Getting Flutter dependencies..." -ForegroundColor Yellow
flutter pub get
Write-Host ""

# Start build
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting APK build (first build may take 10-20 minutes)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

flutter build apk --release

# Check build result
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "APK Build Successful!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    
    $apkPath = Join-Path $projectPath "build\app\outputs\flutter-apk\app-release.apk"
    if (Test-Path $apkPath) {
        $apkSize = [math]::Round((Get-Item $apkPath).Length / 1MB, 2)
        Write-Host "APK file location: $apkPath" -ForegroundColor Cyan
        Write-Host "APK file size: ${apkSize} MB" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "You can transfer this APK file to your phone for testing" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "APK Build Failed!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please check the error messages above. Common issues:" -ForegroundColor Yellow
    Write-Host "  1. Insufficient D drive space (need at least 10GB)" -ForegroundColor Gray
    Write-Host "  2. Network connection issues (domestic mirrors configured)" -ForegroundColor Gray
    Write-Host "  3. Android SDK not properly installed" -ForegroundColor Gray
    Write-Host ""
}
