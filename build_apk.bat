@echo off
chcp 65001 >nul
echo ========================================
echo Flutter APK Build Script
echo ========================================
echo.

REM Set environment variables
set GRADLE_USER_HOME=D:\FlutterCache\.gradle
set PUB_CACHE=D:\FlutterCache\.pub-cache
set ANDROID_HOME=D:\FlutterCache\.android\sdk
set ANDROID_SDK_ROOT=D:\FlutterCache\.android\sdk

echo [1/4] Environment configured
echo   ANDROID_HOME=%ANDROID_HOME%
echo   GRADLE_USER_HOME=%GRADLE_USER_HOME%
echo.

REM Change to script directory
cd /d "%~dp0"

echo [2/4] Getting dependencies...
call flutter pub get
if errorlevel 1 (
    echo ERROR: Failed to get dependencies
    pause
    exit /b 1
)
echo.

echo [3/4] Building APK (this may take 10-20 minutes for first build)...
call flutter build apk --release
if errorlevel 1 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    pause
    exit /b 1
)
echo.

echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo.
pause
