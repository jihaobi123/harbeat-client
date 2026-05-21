# HARIBEAT APK Build Script
# This script sets environment variables and builds the APK

Write-Host "Setting Android SDK environment variables..." -ForegroundColor Cyan
$env:ANDROID_HOME = "D:\FlutterCache\.android\sdk"
$env:ANDROID_SDK_ROOT = "D:\FlutterCache\.android\sdk"

Write-Host "ANDROID_HOME = $env:ANDROID_HOME" -ForegroundColor Green
Write-Host "ANDROID_SDK_ROOT = $env:ANDROID_SDK_ROOT" -ForegroundColor Green
Write-Host ""

Write-Host "Starting Flutter build..." -ForegroundColor Yellow
flutter build apk --release

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "APK Build Successful!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Build failed with exit code: $LASTEXITCODE" -ForegroundColor Red
}