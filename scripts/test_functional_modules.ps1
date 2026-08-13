param(
    [switch]$StopOnFailure
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$tests = @(
    @{ Name = "observability-e2e"; Command = { py -m unittest discover modules/observability-e2e/tests -v } },
    @{ Name = "device-runtime"; Command = { py -m unittest discover modules/device-runtime/tests -v } },
    @{ Name = "library-catalog"; Command = { py -m unittest discover modules/library-catalog/tests -v } },
    @{ Name = "audio-preprocess"; Command = { py -m unittest discover modules/audio-preprocess/tests -v } },
    @{ Name = "stem-separation"; Command = { py -m unittest discover modules/stem-separation/tests -v } },
    @{ Name = "sequence-planner"; Command = { py -m unittest discover modules/sequence-planner/tests -v } },
    @{ Name = "transition-planner"; Command = {
        $env:PYTHONPATH = Join-Path $repoRoot "modules/transition-planner/src"
        py -m unittest discover modules/transition-planner/tests -v
    } },
    @{ Name = "transition-renderer"; Command = {
        $env:PYTHONPATH = Join-Path $repoRoot "modules/transition-renderer/src"
        py -m pytest -q modules/transition-renderer/tests
    } },
    @{ Name = "asset-sync"; Command = {
        $env:PYTHONPATH = Join-Path $repoRoot "modules/asset-sync/src"
        py -m pytest -q modules/asset-sync/tests
    } },
    @{ Name = "transition-orchestrator"; Command = {
        $env:PYTHONPATH = Join-Path $repoRoot "modules/transition-orchestrator/src"
        py -m pytest -q modules/transition-orchestrator/tests
    } },
    @{ Name = "audio-runtime"; Command = {
        $env:PYTHONPATH = Join-Path $repoRoot "modules/audio-runtime/src"
        py -m pytest -q modules/audio-runtime/tests
    } },
    @{ Name = "mobile-dj-control"; Command = { dart run modules/mobile-dj-control/tests/mobile_dj_control_test.dart } },
    @{ Name = "physical-input"; Command = {
        $env:PYTHONPATH = Join-Path $repoRoot "modules/physical-input/src"
        py -m pytest -q modules/physical-input/tests
    } }
)

$originalPythonPath = $env:PYTHONPATH
$results = @()

try {
    foreach ($test in $tests) {
        $env:PYTHONPATH = $originalPythonPath
        $started = Get-Date
        Write-Host "`n=== $($test.Name) ===" -ForegroundColor Cyan

        & $test.Command
        $exitCode = $LASTEXITCODE
        $elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds, 3)
        $passed = $exitCode -eq 0

        $results += [PSCustomObject]@{
            Module = $test.Name
            Passed = $passed
            Seconds = $elapsed
            ExitCode = $exitCode
        }

        if (-not $passed -and $StopOnFailure) {
            break
        }
    }
}
finally {
    $env:PYTHONPATH = $originalPythonPath
}

Write-Host "`n=== Functional module test summary ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$failed = @($results | Where-Object { -not $_.Passed })
$missing = $tests.Count - $results.Count
if ($failed.Count -gt 0 -or $missing -gt 0) {
    Write-Error "$($failed.Count) module test command(s) failed; $missing not run."
    exit 1
}

Write-Host "All $($tests.Count) module test commands passed." -ForegroundColor Green
exit 0
