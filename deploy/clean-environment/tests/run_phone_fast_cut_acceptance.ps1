param(
    [string]$DeviceId = "130ddcca",
    [string]$EdgeUrl = "http://192.168.93.209:19001",
    [int]$Attempt = 1,
    [int]$ButtonX = 0,
    [int]$ButtonY = 0,
    [double]$ExecuteDeadlineSec = 15.0,
    [double]$ObserveDeadlineSec = 22.0
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$evidenceDir = Join-Path $repoRoot "deploy\clean-environment\evidence"
$uiPath = Join-Path $evidenceDir ("stage-e-fast-cut-{0:D2}-window.xml" -f $Attempt)
$resultPath = Join-Path $evidenceDir ("stage-e-fast-cut-{0:D2}.json" -f $Attempt)
$remoteUiPath = "/sdcard/harbeat-fast-cut-window.xml"
$stateUrl = "$EdgeUrl/state"

function Get-EdgeState {
    Invoke-RestMethod -Uri $stateUrl -TimeoutSec 2
}

function Get-FastCutButtonCenter {
    $savedErrorPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & adb -s $DeviceId shell uiautomator dump $remoteUiPath 2>$null | Out-Null
    $dumpExitCode = $LASTEXITCODE
    & adb -s $DeviceId pull $remoteUiPath $uiPath 2>$null | Out-Null
    $pullExitCode = $LASTEXITCODE
    $ErrorActionPreference = $savedErrorPreference
    if (-not (Test-Path $uiPath) -or (Get-Item $uiPath).Length -eq 0) {
        throw "failed to pull Android UI tree (dump=$dumpExitCode pull=$pullExitCode)"
    }

    $document = New-Object System.Xml.XmlDocument
    $document.Load($uiPath)
    $button = $document.SelectNodes('//node[@clickable="true"]') |
        Where-Object { $_.'content-desc' -match 'fast_cut' } |
        Select-Object -First 1
    if ($null -eq $button) {
        throw "fast_cut button is not visible"
    }

    $match = [regex]::Match($button.bounds, '^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$')
    if (-not $match.Success) {
        throw "invalid fast_cut bounds: $($button.bounds)"
    }
    return [pscustomobject]@{
        x = [int](([int]$match.Groups[1].Value + [int]$match.Groups[3].Value) / 2)
        y = [int](([int]$match.Groups[2].Value + [int]$match.Groups[4].Value) / 2)
        bounds = $button.bounds
    }
}

$before = Get-EdgeState
if (-not $before.playing) {
    throw "RK is not playing"
}

$button = if ($ButtonX -gt 0 -and $ButtonY -gt 0) {
    [pscustomobject]@{ x = $ButtonX; y = $ButtonY; bounds = "explicit" }
} else {
    Get-FastCutButtonCenter
}
$startedAt = Get-Date
& adb -s $DeviceId shell input tap $button.x $button.y *> $null
if ($LASTEXITCODE -ne 0) {
    throw "ADB tap failed"
}

$samples = [System.Collections.Generic.List[object]]::new()
$readyAt = $null
$executeAt = $null
$resumeAt = $null
$executedState = $null
$deadline = $startedAt.AddSeconds($ObserveDeadlineSec)

do {
    Start-Sleep -Milliseconds 500
    $now = Get-Date
    $elapsed = [math]::Round(($now - $startedAt).TotalSeconds, 3)
    try {
        $state = Get-EdgeState
    } catch {
        $samples.Add([pscustomobject]@{
            elapsed_sec = $elapsed
            request_error = $_.Exception.Message
        })
        continue
    }

    $action = [string]$state.last_transition.action
    $scheduled = $null -ne $state.scheduled_default_render
    $sample = [pscustomobject]@{
        elapsed_sec = $elapsed
        song_id = $state.current_song_id
        position_sec = $state.position_sec
        playing = $state.playing
        action = $action
        scheduled = $scheduled
        planned_from_at_sec = $state.last_transition.planned_from_at_sec
        actual_from_at_sec = $state.last_transition.actual_from_at_sec
        trigger_error_ms = $state.last_transition.trigger_error_ms
        degraded = $state.last_transition.degraded
    }
    $samples.Add($sample)

    if ($null -eq $readyAt -and ($scheduled -or $action -eq "default_render_scheduled")) {
        $readyAt = $elapsed
    }
    if ($null -eq $executeAt -and
        $state.current_song_id -ne $before.current_song_id -and
        $action -eq "default_render_playback") {
        $executeAt = $elapsed
        $executedState = $state
    }
    if ($null -ne $executeAt -and
        $null -eq $resumeAt -and
        $state.current_song_id -ne $before.current_song_id -and
        $action -eq "default_render_resume") {
        $resumeAt = $elapsed
        break
    }
} while ((Get-Date) -lt $deadline)

$passed = $null -ne $executeAt -and
    $executeAt -le $ExecuteDeadlineSec -and
    $executedState.last_transition.degraded -ne $true -and
    [math]::Abs([double]$executedState.last_transition.trigger_error_ms) -le 100.0

$result = [pscustomobject]@{
    test = "fast_cut_$Attempt"
    started_at = $startedAt.ToString("o")
    button = $button
    before = $before
    click_to_ready_sec = $readyAt
    click_to_execute_sec = $executeAt
    click_to_resume_sec = $resumeAt
    planned_from_at_sec = $executedState.last_transition.planned_from_at_sec
    actual_from_at_sec = $executedState.last_transition.actual_from_at_sec
    trigger_error_ms = $executedState.last_transition.trigger_error_ms
    degraded = $executedState.last_transition.degraded
    passed = $passed
    samples = $samples
}
$result | ConvertTo-Json -Depth 12 | Set-Content $resultPath -Encoding utf8
$result | Select-Object test, click_to_ready_sec, click_to_execute_sec,
    click_to_resume_sec, trigger_error_ms, degraded, passed | Format-List

if (-not $passed) {
    exit 1
}
