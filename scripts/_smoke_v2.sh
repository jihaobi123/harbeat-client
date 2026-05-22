#!/usr/bin/env bash
# Smoke test for v2 features on Jetson local FastAPI
set -u
BASE=${BASE:-http://127.0.0.1:8000}
post() {
  echo "--- $1 ---"
  curl -s -X POST "$BASE/api/voice/command" -H 'Content-Type: application/json' -d "$2"
  echo
}
echo "### Voice intents ###"
post "loop_last_30s_en"  '{"text":"loop 30","language_hint":"auto"}'
post "loop_last_30s_zh"  '{"text":"前30秒循环","language_hint":"auto"}'
post "loop_off"          '{"text":"exit loop","language_hint":"auto"}'
post "next"              '{"text":"下一首","language_hint":"auto"}'
post "lift_energy"       '{"text":"high energy","language_hint":"auto"}'
post "drop_energy"       '{"text":"chill out","language_hint":"auto"}'
post "switch_style"      '{"text":"breaking","language_hint":"auto"}'
post "emergency_stop"    '{"text":"emergency stop","language_hint":"auto"}'

echo
echo "### Flourish list ###"
curl -s "$BASE/api/music/flourish" | head -c 500
echo
echo
echo "### Flourish stream impact ###"
curl -s -o /tmp/imp.wav -w 'HTTP=%{http_code} size=%{size_download} ct=%{content_type}\n' "$BASE/api/music/flourish/impact"
file /tmp/imp.wav | head -1

echo
echo "### dev/songs ###"
curl -s "$BASE/api/dev/songs?limit=3" | head -c 500
echo

echo
echo "### mix-plan with target_energy_curve ###"
curl -s -X POST "$BASE/api/dev/mix-plan" -H 'Content-Type: application/json' \
  -d '{"style":"hiphop","duration_minutes":5,"max_tracks":4,"target_energy_curve":[3,5,7,9]}' | head -c 400
echo
