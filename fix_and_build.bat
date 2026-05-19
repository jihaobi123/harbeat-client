@echo off
chcp 65001 >nul
echo ========================================
echo HarBeat - Fix Dependencies and Build APK
echo ========================================
echo.

echo [STEP 1] Cleaning project...
flutter clean

echo.
echo [STEP 2] Installing dependencies...
flutter pub get

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [STEP 3] Generating code...
flutter pub run build_runner build --delete-conflicting-outputs

echo.
echo [STEP 4] Checking Android SDK...
flutter doctor

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Install Android Studio if not installed
echo 2. Run: flutter build apk --release
echo.
pause
