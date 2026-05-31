#!/bin/bash
# 加载 101→102 演示 MixPlan（约 4 秒后 8s crossfade 到 102）
set -e

PLAN="$HOME/cypher/plans/demo_101_102.json"

curl -s -X POST "http://127.0.0.1:9000/load_plan" -H "Content-Type: application/json" -d @"$PLAN"
echo ""
curl -s -X POST "http://127.0.0.1:9000/play" -H "Content-Type: application/json" -d '{"song_id":101}'
echo ""
