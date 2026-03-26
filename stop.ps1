#!/usr/bin/env pwsh
#Requires -Version 5.1
# HarBeat — Stop all services
# Usage: .\stop.ps1

Write-Host ""
Write-Host "  HarBeat — stopping services" -ForegroundColor Cyan

$stopped = 0

# Stop uvicorn (Python backend)
Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -EA SilentlyContinue).CommandLine
    if ($cmd -match "uvicorn") {
        Stop-Process -Id $_.Id -Force -EA SilentlyContinue
        Write-Host " [OK] Stopped uvicorn (PID $($_.Id))" -ForegroundColor Green
        $stopped++
    }
}

# Stop Electron / Vite dev server
Get-Process -Name "electron","node" -ErrorAction SilentlyContinue | ForEach-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -EA SilentlyContinue).CommandLine
    if ($cmd -match "vite|electron|harbeat") {
        Stop-Process -Id $_.Id -Force -EA SilentlyContinue
        Write-Host " [OK] Stopped $($_.Name) (PID $($_.Id))" -ForegroundColor Green
        $stopped++
    }
}

if ($stopped -eq 0) {
    Write-Host " [OK] No running services found" -ForegroundColor DarkGray
}
Write-Host ""
