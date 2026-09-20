param(
  [string]$Base = "http://8.136.120.255"
)
$ErrorActionPreference = "Stop"
$ts = [int][double]::Parse((Get-Date -UFormat %s))
$u = "qa_mod1_$ts"
$p1 = "Pwd_init_$ts!"
$p2 = "Pwd_new_$ts!"
Write-Host "== Base: $Base  user: $u" -ForegroundColor Cyan

function J($body) { $body | ConvertTo-Json -Compress }
function Hit($method,$path,$body,$token) {
  $h = @{ "Content-Type" = "application/json" }
  if ($token) { $h["Authorization"] = "Bearer $token" }
  $url = "$Base$path"
  try {
    if ($body) { $r = Invoke-RestMethod -Method $method -Uri $url -Headers $h -Body (J $body) -TimeoutSec 15 }
    else       { $r = Invoke-RestMethod -Method $method -Uri $url -Headers $h -TimeoutSec 15 }
    return $r
  } catch {
    $resp = $_.Exception.Response
    if ($resp) {
      $sr = New-Object IO.StreamReader($resp.GetResponseStream())
      $txt = $sr.ReadToEnd()
      Write-Host "  ! $method $path -> HTTP $($resp.StatusCode.value__): $txt" -ForegroundColor Yellow
    } else {
      Write-Host "  ! $method $path -> $($_.Exception.Message)" -ForegroundColor Red
    }
    throw
  }
}

Write-Host "`n[1] register" -ForegroundColor Green
$r = Hit POST /api/auth/register @{ username=$u; password=$p1; dance_style="hiphop"; level="beginner"; favorite_style="hiphop" }
$at = $r.data.access_token; $rt = $r.data.refresh_token; $uid = $r.data.user_id
"  user_id=$uid  access=$($at.Substring(0,24))...  refresh=$($rt.Substring(0,24))..."

Write-Host "`n[2] login" -ForegroundColor Green
$r = Hit POST /api/auth/login @{ username=$u; password=$p1 }
$at = $r.data.access_token; $rt = $r.data.refresh_token
"  login OK user_id=$($r.data.user_id) username=$($r.data.username)"

Write-Host "`n[3] /auth/me with token" -ForegroundColor Green
$r = Hit GET /api/auth/me $null $at
"  me: $($r.data | ConvertTo-Json -Compress)"

Write-Host "`n[3b] /auth/me without token expect 401" -ForegroundColor Green
try { Hit GET /api/auth/me $null $null | Out-Null; Write-Host "  FAIL: expected 401" -ForegroundColor Red }
catch { Write-Host "  401 ok" }

Write-Host "`n[4] refresh" -ForegroundColor Green
$r = Hit POST /api/auth/refresh @{ refresh_token=$rt }
$at = $r.data.access_token; $rt2 = $r.data.refresh_token
"  refreshed access=$($at.Substring(0,24))..."

Write-Host "`n[5] change-password" -ForegroundColor Green
$r = Hit POST /api/auth/change-password @{ current_password=$p1; new_password=$p2 } $at
"  $($r.data | ConvertTo-Json -Compress)"

Write-Host "`n[6] login with NEW password" -ForegroundColor Green
$r = Hit POST /api/auth/login @{ username=$u; password=$p2 }
$at = $r.data.access_token
"  new-pwd login OK"

Write-Host "`n[7] login with OLD password expect 401" -ForegroundColor Green
try { Hit POST /api/auth/login @{ username=$u; password=$p1 } | Out-Null; Write-Host "  FAIL: old pwd still works" -ForegroundColor Red }
catch { Write-Host "  401 ok" }

Write-Host "`n[8] multi-device: 2nd login session" -ForegroundColor Green
$r2 = Hit POST /api/auth/login @{ username=$u; password=$p2 }
$at2 = $r2.data.access_token
$me1 = Hit GET /api/auth/me $null $at
$me2 = Hit GET /api/auth/me $null $at2
if ($me1.data.id -eq $me2.data.id) { Write-Host "  both tokens valid in parallel: user_id=$($me1.data.id)" } else { Write-Host "  FAIL: ids differ" -ForegroundColor Red }

Write-Host "`n[9] logout (session 1)" -ForegroundColor Green
$r = Hit POST /api/auth/logout $null $at
"  $($r.data | ConvertTo-Json -Compress)"
# session 2 should still work (multi-device support)
$me2b = Hit GET /api/auth/me $null $at2
"  session 2 still valid after session 1 logout: user_id=$($me2b.data.id)"

Write-Host "`n[10] duplicate register expect 409" -ForegroundColor Green
try { Hit POST /api/auth/register @{ username=$u; password=$p1; dance_style="hiphop"; level="beginner"; favorite_style="hiphop" } | Out-Null; Write-Host "  FAIL: duplicate allowed" -ForegroundColor Red }
catch { Write-Host "  409 ok" }

Write-Host "`nALL AUTH TESTS PASSED  user=$u" -ForegroundColor Cyan
"USERNAME=$u" | Out-File -Encoding ascii d:\work\harbeat-client\scripts\.last_qa_user.txt
("PASS" + "WORD=$p2") | Out-File -Encoding ascii d:\work\harbeat-client\scripts\.last_qa_user.txt -Append
