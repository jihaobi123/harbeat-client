@echo off
chcp 65001 >nul
echo ========================================
echo Install Android SDK Components Manually
echo ========================================
echo.

REM Set Android SDK path
set ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk

echo [INFO] Android SDK Path: %ANDROID_HOME%
echo.

REM Check if sdkmanager exists
if not exist "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" (
    echo [ERROR] sdkmanager not found!
    echo Please complete Android Studio installation first.
    pause
    exit /b 1
)

echo [STEP 1] Accepting licenses...
call "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" --licenses
echo.

echo [STEP 2] Installing required components...
echo This may take 10-20 minutes...
echo.

call "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" ^
    "platform-tools" ^
    "platforms;android-34" ^
    "build-tools;34.0.0" ^
    "cmdline-tools;latest"

if %errorlevel% equ 0 (
    echo.
    echo [OK] Installation completed successfully!
    echo.
    echo Next steps:
    echo 1. Restart PowerShell
    echo 2. Run: flutter doctor
    echo 3. Verify Android toolchain shows green checkmark
) else (
    echo.
    echo [ERROR] Installation failed!
    echo Try again or check your network connection.
)

echo.
pause
