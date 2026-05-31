#!/bin/bash
# 快速测耳机是否有声（不经过 cypher）
set -e
WAV="${1:-$HOME/cypher/cache/102/original.wav}"
echo "1) ALSA 直出 plughw:2,0 ..."
timeout 3 aplay -D plughw:2,0 "$WAV" 2>&1 || echo "  (若 busy 可忽略，试 2)"
echo "2) Pulse default ..."
timeout 3 paplay "$WAV" 2>&1 && echo "  paplay OK"
echo "3) cypher play ..."
curl -s -X POST http://127.0.0.1:9000/play \
  -H "Content-Type: application/json" \
  -d '{"song_id":102}'
echo ""
