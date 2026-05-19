# Fix Retrofit Generator and Build Project
# Run this in PowerShell

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Fixing Dependencies and Building" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Set-Location "d:\工作\DJ机\harbeat_app"

# Step 1: Remove lock file
Write-Host "[1/4] Removing pubspec.lock..." -ForegroundColor Yellow
if (Test-Path "pubspec.lock") {
    Remove-Item "pubspec.lock" -Force
    Write-Host "[OK] pubspec.lock removed" -ForegroundColor Green
} else {
    Write-Host "[INFO] pubspec.lock not found, skipping" -ForegroundColor Cyan
}
Write-Host ""

# Step 2: Install dependencies
Write-Host "[2/4] Installing dependencies..." -ForegroundColor Yellow
flutter pub get
Write-Host ""

# Step 3: Verify retrofit_generator version
Write-Host "[3/4] Checking retrofit_generator version..." -ForegroundColor Yellow
if (Test-Path "pubspec.lock") {
    $lockContent = Get-Content "pubspec.lock" -Raw
    if ($lockContent -match "retrofit_generator.*version:.*8\.0\.") {
        Write-Host "[OK] retrofit_generator version is compatible" -ForegroundColor Green
    } else {
        Write-Host "[WARN] retrofit_generator may not be at 8.0.x version" -ForegroundColor Yellow
    }
}
Write-Host ""

# Step 4: Try to build
Write-Host "[4/4] Running build_runner..." -ForegroundColor Yellow
flutter pub run build_runner build --delete-conflicting-outputs

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Done!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next: Run 'flutter run -d chrome' to test in browser" -ForegroundColor Yellow
Write-Host "Or: Run 'flutter build apk --release' to build APK" -ForegroundColor Yellow
