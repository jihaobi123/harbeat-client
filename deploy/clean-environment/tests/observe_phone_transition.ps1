param(
    [Parameter(Mandatory = $true)]
    [string]$TestName,
    [Parameter(Mandatory = $true)]
    [int]$ButtonX,
    [Parameter(Mandatory = $true)]
    [int]$ButtonY,
    [string]$DeviceId = "130ddcca",
    [string]$EdgeUrl = "http://192.168.93.209:19001",
    [double]$ObserveDeadlineSec = 45.0
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$evidenceDir = Join-Path $repoRoot "deploy\clean-environment\evidence"
$resultPath = Join-Path $evidenceDir ("stage-e-$TestName.json")
$stateUrl = "$EdgeUrl/state"

function Get-EdgeState {
    Invoke-RestMethod -Uri $stateUrl -TimeoutSec 2
}

$before = Get-EdgeState
if (-not $before.playing) {
    throw "RK is not playing"
}

$startedAt = Get-Date
& adb -s $DeviceId shell input tap $ButtonX $ButtonY *> $null
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
    $elapsed = [math]::Round(((Get-Date) - $startedAt).TotalSeconds, 3)
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
    $samples.Add([pscustomobject]@{
        elapsed_sec = $elapsed
        song_id = $state.current_song_id
        position_sec = $state.position_sec
        playing = $state.playing
        action = $action
        transition_id = $state.last_transition.transition_id
        scheduled = $scheduled
        planned_from_at_sec = $state.last_transition.planned_from_at_sec
        actual_from_at_sec = $state.last_transition.actual_from_at_sec
        trigger_error_ms = $state.last_transition.trigger_error_ms
        degraded = $state.last_transition.degraded
    })

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
    $executedState.last_transition.degraded -ne $true -and
    [math]::Abs([double]$executedState.last_transition.trigger_error_ms) -le 100.0

$result = [pscustomobject]@{
    test = $TestName
    started_at = $startedAt.ToString("o")
    button = [pscustomobject]@{ x = $ButtonX; y = $ButtonY }
    before = $before
    click_to_ready_sec = $readyAt
    click_to_execute_sec = $executeAt
    click_to_resume_sec = $resumeAt
    transition_id = $executedState.last_transition.transition_id
    planned_from_at_sec = $executedState.last_transition.planned_from_at_sec
    actual_from_at_sec = $executedState.last_transition.actual_from_at_sec
    trigger_error_ms = $executedState.last_transition.trigger_error_ms
    degraded = $executedState.last_transition.degraded
    passed = $passed
    samples = $samples
}
$result | ConvertTo-Json -Depth 12 | Set-Content $resultPath -Encoding utf8
$result | Select-Object test, click_to_ready_sec, click_to_execute_sec,
    click_to_resume_sec, transition_id, trigger_error_ms, degraded, passed |
    Format-List

if (-not $passed) {
    exit 1
}
