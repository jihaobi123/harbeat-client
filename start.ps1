#!/usr/bin/env pwsh
#Requires -Version 5.1
# HarBeat — One-click environment setup & start
# Usage: .\start.ps1
# Encoding: UTF-8 BOM (required for Chinese Windows PowerShell 5.1)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Helpers ─────────────────────────────────────────
function Step($msg)  { Write-Host "[...] $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host " [OK] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[ERR] $msg" -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "  HarBeat — one-click start" -ForegroundColor Magenta
Write-Host ("=" * 55) -ForegroundColor DarkGray

# ── 1. Check Python ─────────────────────────────────
Step "Checking Python..."
$PythonExe = $null
$pythonPaths = @(where.exe python 2>$null)
foreach ($p in $pythonPaths) {
    if ($p -match "WindowsApps") { continue }
    $testOut = & $p --version 2>&1
    if ($LASTEXITCODE -eq 0) { $PythonExe = $p; break }
}
if (-not $PythonExe) {
    Fail "Python not found. Install Python 3.10+ from https://python.org"
}
$pyVer = & $PythonExe --version 2>&1
Ok "$pyVer  [$PythonExe]"

# ── 2. Check Node.js ────────────────────────────────
Step "Checking Node.js..."
$nodeVer = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "Node.js not found. Install Node.js 18+ from https://nodejs.org"
}
Ok "Node.js $nodeVer"

# ── 3. .env ─────────────────────────────────────────
Step "Checking .env..."
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    $example = Join-Path $Root ".env.example"
    if (Test-Path $example) {
        Copy-Item $example $envFile
        Warn ".env created from .env.example (edit if needed)"
    } else {
        Fail ".env.example missing — cannot configure backend"
    }
} else {
    Ok ".env exists"
}

# ── 4. Python venv + deps ───────────────────────────
$venv    = Join-Path $Root ".venv"
$pip     = Join-Path $venv "Scripts\pip.exe"
$uvicorn = Join-Path $venv "Scripts\uvicorn.exe"

if (-not (Test-Path $venv)) {
    Step "Creating Python virtual environment (.venv)..."
    & $PythonExe -m venv $venv
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create .venv" }
    Ok ".venv created"
} else {
    Ok ".venv exists"
}

Step "Installing Python dependencies (first run may take a few minutes)..."
$ErrorActionPreference = "Continue"
& $pip install -q --upgrade pip 2>$null
& $pip install -r (Join-Path $Root "requirements.txt") 2>$null
$ErrorActionPreference = "Stop"
if (-not (Test-Path $uvicorn)) {
    Fail "Python deps install failed — check requirements.txt and network"
}
Ok "Python deps ready"

# ── 5. Node modules ─────────────────────────────────
$nodeModules = Join-Path $Root "node_modules"
if (-not (Test-Path $nodeModules)) {
    Step "Running npm install (first run only)..."
    Push-Location $Root
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "npm install failed" }
    Pop-Location
    Ok "Node modules installed"
} else {
    Ok "node_modules exists"
}

# ── 6. Electron mirror (China) ──────────────────────
if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
}

Write-Host ("=" * 55) -ForegroundColor DarkGray

# ── 7. Start Backend ────────────────────────────────
Step "Starting FastAPI backend (http://localhost:8000)..."
$backendCmd = @"
Set-Location '$Root'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host '=== HarBeat Backend ===' -ForegroundColor Cyan
Write-Host 'API Docs: http://localhost:8000/docs' -ForegroundColor DarkGray
& '$uvicorn' app.main:app --reload --host 0.0.0.0 --port 8000
"@
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $backendCmd

Start-Sleep -Seconds 3

# ── 8. Start Frontend ───────────────────────────────
Step "Starting Electron + Vite frontend..."
$frontendCmd = @"
Set-Location '$Root'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Host '=== HarBeat Frontend ===' -ForegroundColor Cyan
npm run dev
"@
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $frontendCmd

# ── Done ────────────────────────────────────────────
Write-Host ("=" * 55) -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Backend  : http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs : http://localhost:8000/docs" -ForegroundColor White
Write-Host "  Frontend : Electron window will open shortly" -ForegroundColor White
Write-Host ""
Write-Host "  Stop all : .\stop.ps1" -ForegroundColor DarkGray
Write-Host ""
