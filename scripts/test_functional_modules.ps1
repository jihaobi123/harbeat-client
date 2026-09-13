param(
    [switch]$StopOnFailure
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repoRoot "scripts/test_current_modules.py"
$runnerArgs = @($runner)
if ($StopOnFailure) {
    $runnerArgs += "--stop-on-failure"
}
py @runnerArgs
exit $LASTEXITCODE
