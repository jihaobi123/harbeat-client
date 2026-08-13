param(
    [string]$Wheelhouse = "$env:TEMP\harbeat-wheelhouse-v030-final-20260814"
)

$ErrorActionPreference = "Stop"
$venv = Join-Path $env:TEMP "harbeat-wheel-install-v030-verify"
$python = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $python)) {
    py -m venv $venv
}

$wheels = @(Get-ChildItem $Wheelhouse -Filter "*.whl" | Select-Object -ExpandProperty FullName)
if ($wheels.Count -ne 12) {
    throw "Expected 12 HarBeat wheels, got $($wheels.Count)"
}

& $python -m pip install --disable-pip-version-check --quiet `
    "numpy==1.26.4" "soundfile==0.13.1" "sounddevice==0.4.6" `
    "fastapi==0.116.1" "httpx==0.28.1"
if ($LASTEXITCODE -ne 0) { throw "Profile dependency installation failed" }

& $python -m pip install --disable-pip-version-check --quiet --no-deps $wheels
if ($LASTEXITCODE -ne 0) { throw "Wheel installation failed" }

$code = @'
import harbeat_asset_sync
import harbeat_audio_preprocess
import harbeat_audio_runtime
import harbeat_device_runtime
import harbeat_library_catalog
import harbeat_observability
import harbeat_physical_input
import harbeat_sequence_planner
import harbeat_stem_separation
import harbeat_transition_orchestrator
import harbeat_transition_planner
import harbeat_transition_renderer
print("12 wheel imports ok")
'@
& $python -c $code
if ($LASTEXITCODE -ne 0) { throw "Wheel import smoke test failed" }
