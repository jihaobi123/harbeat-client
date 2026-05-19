@echo off
chcp 65001 >nul
echo ========================================
echo Creating Assets Directories
echo ========================================
echo.

cd /d "d:\工作\DJ机\harbeat_app"

if not exist "assets\images" mkdir "assets\images"
if not exist "assets\icons" mkdir "assets\icons"
if not exist "assets\fonts" mkdir "assets\fonts"

echo [OK] Created assets\images
echo [OK] Created assets\icons
echo [OK] Created assets\fonts
echo.

REM Create placeholder font file
if not exist "assets\fonts\HarBeat-Regular.ttf" (
    echo Creating placeholder font file...
    type nul > "assets\fonts\HarBeat-Regular.ttf"
    type nul > "assets\fonts\HarBeat-Bold.ttf"
    echo [OK] Created placeholder font files
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. flutter pub get
echo 2. flutter pub run build_runner build --delete-conflicting-outputs
echo 3. flutter run -d chrome
echo.
pause
