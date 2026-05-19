@echo off
chcp 65001 >nul
echo ========================================
echo Install Android cmdline-tools
echo ========================================
echo.

set ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk

echo [INFO] Checking cmdline-tools...
if exist "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" (
    echo [OK] cmdline-tools already installed
    goto :accept_licenses
)

echo [WARN] cmdline-tools not found!
echo.
echo Please install manually:
echo 1. Open Android Studio
echo 2. File ^> Settings ^> Android SDK ^> SDK Tools
echo 3. Check "Android SDK Command-line Tools (latest)"
echo 4. Click Apply
echo.
pause
exit /b 1

:accept_licenses
echo.
echo [STEP] Accepting licenses...
call "%ANDROID_HOME%\cmdline-tools\latest\bin\sdkmanager.bat" --licenses

echo.
echo ========================================
echo Done!
echo ========================================
echo.
echo Next: Restart PowerShell and run flutter doctor
echo.
pause
