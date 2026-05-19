# HarBeat - Final Fix and Test Script
# Run this in PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "HarBeat - Final Fix and Test" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we're in the right directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-Host "[INFO] Working directory: $(Get-Location)" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean
Write-Host "[1/4] Cleaning project..." -ForegroundColor Yellow
flutter clean
Write-Host "[OK] Clean completed" -ForegroundColor Green
Write-Host ""

# Step 2: Install dependencies
Write-Host "[2/4] Installing dependencies..." -ForegroundColor Yellow
flutter pub get
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Dependencies installed" -ForegroundColor Green
Write-Host ""

# Step 3: Check for compilation errors
Write-Host "[3/4] Checking for compilation errors..." -ForegroundColor Yellow
flutter analyze
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Found some issues, but continuing..." -ForegroundColor Yellow
}
Write-Host ""

# Step 4: Run in Chrome
Write-Host "[4/4] Launching in Chrome..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Starting Flutter app in Chrome..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

flutter run -d chrome
