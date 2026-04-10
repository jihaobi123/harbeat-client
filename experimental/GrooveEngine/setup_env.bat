@echo off
setlocal EnableExtensions EnableDelayedExpansion

title GrooveEngine Windows Setup
color 0B

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%venv"
set "REQ_FILE=%PROJECT_DIR%requirements.txt"
set "MODELS_DIR=%PROJECT_DIR%models"

echo ================================================================
echo   GrooveEngine - Windows Environment Bootstrap
echo ================================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py"
    goto :python_found
)

where python >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

color 0C
echo [ERROR] Python was not found on this machine.
echo.
echo Install Python 3.11+ from:
echo   https://www.python.org/downloads/windows/
echo.
echo Then re-run this script.
exit /b 1

:python_found
echo [OK] Found Python launcher: %PYTHON_CMD%
echo.

if not exist "%REQ_FILE%" (
    color 0C
    echo [ERROR] requirements.txt not found at:
    echo   %REQ_FILE%
    exit /b 1
)

echo [1/5] Creating virtual environment...
"%PYTHON_CMD%" -m venv "%VENV_DIR%"
if errorlevel 1 goto :fail

echo [2/5] Activating virtual environment...
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 goto :fail

echo [3/5] Upgrading pip, setuptools, and wheel...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :fail

echo [4/5] Installing GrooveEngine dependencies...
python -m pip install -r "%REQ_FILE%"
if errorlevel 1 goto :fail

echo [5/5] Ensuring models directory exists...
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"
if errorlevel 1 goto :fail

echo.
color 0A
echo [SUCCESS] GrooveEngine environment setup completed.
echo.
color 0E
echo [IMPORTANT] External tools you may still need:
echo.
echo   1. FFmpeg is required for some audio workflows and pydub convenience.
echo      Install guide / binaries:
echo      https://www.gyan.dev/ffmpeg/builds/
echo      Scoop-friendly page:
echo      https://www.gyan.dev/ffmpeg/builds/#release-builds
echo.
echo   2. If you experience high latency, crackles, or weak Windows drivers,
echo      install ASIO4ALL:
echo      https://asio4all.org/
echo.
echo Next steps:
echo   call venv\Scripts\activate
echo   python tests\check_env.py
echo   python scripts\download_songformer.py
echo.
exit /b 0

:fail
color 0C
echo.
echo [FAILED] Setup did not complete successfully.
echo Review the error messages above, then re-run this script.
exit /b 1
