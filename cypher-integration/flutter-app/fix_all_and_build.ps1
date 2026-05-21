# HarBeat - Complete Fix and Build Script
# Run this in PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "HarBeat - Complete Fix and Build" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we're in the right directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-Host "[INFO] Working directory: $(Get-Location)" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean
Write-Host "[1/5] Cleaning project..." -ForegroundColor Yellow
flutter clean
Write-Host "[OK] Clean completed" -ForegroundColor Green
Write-Host ""

# Step 2: Remove lock file
Write-Host "[2/5] Removing pubspec.lock..." -ForegroundColor Yellow
if (Test-Path "pubspec.lock") {
    Remove-Item "pubspec.lock" -Force
    Write-Host "[OK] pubspec.lock removed" -ForegroundColor Green
} else {
    Write-Host "[INFO] pubspec.lock not found" -ForegroundColor Cyan
}
Write-Host ""

# Step 3: Install dependencies
Write-Host "[3/5] Installing dependencies (this may take a while)..." -ForegroundColor Yellow
flutter pub get
Write-Host ""

# Step 4: Run build_runner
Write-Host "[4/5] Running build_runner..." -ForegroundColor Yellow
flutter pub run build_runner build --delete-conflicting-outputs
Write-Host ""

# Step 5: Summary
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Test in browser:" -ForegroundColor White
Write-Host "   flutter run -d chrome" -ForegroundColor Green
Write-Host ""
Write-Host "2. Build APK (requires Android SDK):" -ForegroundColor White
Write-Host "   flutter build apk --release" -ForegroundColor Green
Write-Host ""
