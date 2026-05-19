@echo off
chcp 65001 >nul
echo ========================================
echo Verify Android SDK Installation
echo ========================================
echo.

REM Set Android SDK path
set ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk

echo [INFO] Android SDK Path: %ANDROID_HOME%
echo.

REM Check installed components
echo [CHECK] Checking installed components...
if exist "%ANDROID_HOME%\platform-tools\adb.exe" (
    echo [OK] Platform Tools
) else (
    echo [ERROR] Platform Tools not found
)

if exist "%ANDROID_HOME%\build-tools\37.0.0\aapt.exe" (
    echo [OK] Build Tools 37.0.0
) else if exist "%ANDROID_HOME%\build-tools\36.1.0\aapt.exe" (
    echo [OK] Build Tools 36.1.0
) else (
    echo [ERROR] Build Tools not found
)

if exist "%ANDROID_HOME%\platforms\android-36.1\android.jar" (
    echo [OK] Android Platform 36.1
) else (
    echo [ERROR] Android Platform not found
)

echo.
echo [STEP] Accepting licenses...
call "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" --licenses

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Restart PowerShell
echo 2. Run: flutter doctor
echo 3. Verify Android toolchain shows green checkmark
echo.
pause
