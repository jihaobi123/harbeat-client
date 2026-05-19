@echo off
chcp 65001 >nul
echo ========================================
echo HarBeat - Download Flutter from Tsinghua Mirror
echo ========================================
echo.

REM Check if D:\flutter already exists
if exist "D:\flutter" (
    echo [WARN] D:\flutter already exists!
    set /p confirm="Delete and re-download? (y/n): "
    if /i "%confirm%"=="y" (
        echo [CLEAN] Removing old Flutter folder...
        rmdir /s /q "D:\flutter"
    ) else (
        echo [CANCEL] Aborted
        pause
        exit /b 0
    )
)

echo [DOWNLOAD] Cloning Flutter SDK from Tsinghua mirror...
echo This will take 5-15 minutes depending on your network speed...
echo.

REM Clone from Tsinghua mirror
git clone -b stable https://mirrors.tuna.tsinghua.edu.cn/git/flutter-sdk.git D:\flutter

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Clone failed!
    echo.
    echo Please check:
    echo 1. Git is installed (https://git-scm.com/download/win)
    echo 2. Network connection is stable
    echo 3. Try again later
    echo.
    pause
    exit /b 1
)

echo.
echo [OK] Flutter downloaded successfully to D:\flutter
echo.
echo Next steps:
echo 1. Add D:\flutter\bin to system PATH
echo 2. Restart PowerShell
echo 3. Run: flutter doctor
echo.
pause
