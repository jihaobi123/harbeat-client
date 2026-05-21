# HarBeat - Quick Start Script (No Code Generation)
# Run this in PowerShell to quickly test the app in browser

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "HarBeat - Quick Start" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we're in the right directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir
Write-Host "[INFO] Working directory: $(Get-Location)" -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean
Write-Host "[1/3] Cleaning project..." -ForegroundColor Yellow
flutter clean
Write-Host "[OK] Clean completed" -ForegroundColor Green
Write-Host ""

# Step 2: Install dependencies
Write-Host "[2/3] Installing dependencies..." -ForegroundColor Yellow
flutter pub get
Write-Host ""

# Step 3: Run in Chrome
Write-Host "[3/3] Launching in Chrome..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Starting Flutter app in Chrome..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

flutter run -d chrome
