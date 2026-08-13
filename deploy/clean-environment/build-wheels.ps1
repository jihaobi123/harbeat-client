param(
    [string]$Output = "$env:TEMP\harbeat-wheelhouse-v0.3"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\")).Path
$builder = Join-Path $env:TEMP "harbeat-build-tools-v030"
$python = Join-Path $builder "Scripts\python.exe"
$env:SOURCE_DATE_EPOCH = "1723680000"

if (-not (Test-Path $python)) {
    throw "Build tool venv is missing: $builder. Create it with Python >= 3.10 and install build==1.2.2.post1, wheel==0.45.1, setuptools==81.0.0."
}

New-Item -ItemType Directory -Force $Output | Out-Null
$failed = @()
Get-ChildItem (Join-Path $repoRoot "modules") -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "pyproject.toml") } |
    ForEach-Object {
        & $python -m build --wheel --no-isolation --outdir $Output $_.FullName
        if ($LASTEXITCODE -ne 0) { $failed += $_.Name }
    }

if ($failed.Count -gt 0) {
    throw "Wheel build failed: $($failed -join ', ')"
}

$manifest = @{
    schema_version = 1
    release = "0.3.0"
    builder = @{
        python = (& $python --version).Trim()
        setuptools = "81.0.0"
        wheel = "0.45.1"
        build = "1.2.2.post1"
    }
    artifacts = @(
        Get-ChildItem $Output -Filter "*.whl" | Sort-Object Name | ForEach-Object {
            $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            @{ name = $_.Name; bytes = $_.Length; sha256 = $hash }
        }
    )
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $Output "wheelhouse-manifest.json") -Encoding UTF8
if ($manifest.artifacts.Count -ne 12) { throw "Expected 12 Python wheels, got $($manifest.artifacts.Count)" }
Write-Output ($manifest | ConvertTo-Json -Depth 8)
