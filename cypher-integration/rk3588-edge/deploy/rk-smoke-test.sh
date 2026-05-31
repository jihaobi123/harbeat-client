#!/bin/bash
# RK local smoke test for App <-> RK fast path and basic Jetson hooks.
set -euo pipefail

RK_URL="${RK_URL:-http://127.0.0.1:9000}"
SYNC_URL="${SYNC_URL:-http://127.0.0.1:9100}"
CYPHER_HOME="${CYPHER_HOME:-/home/cat/cypher}"

echo "== health =="
curl -fsS "$RK_URL/health"
echo

echo "== sync status =="
curl -fsS "$SYNC_URL/status"
echo

echo "== load demo plan =="
curl -fsS -X POST "$RK_URL/load_plan" \
  -H "Content-Type: application/json" \
  -d @"$CYPHER_HOME/plans/demo_101_102.json"
echo

echo "== play 101 =="
curl -fsS -X POST "$RK_URL/play" \
  -H "Content-Type: application/json" \
  -d '{"song_id":101,"start_at_sec":0}'
echo

sleep 1

echo "== trigger key 1 =="
curl -fsS -X POST "$RK_URL/trigger" \
  -H "Content-Type: application/json" \
  -d '{"key":1}'
echo

echo "== state =="
curl -fsS "$RK_URL/state"
echo

echo "== next =="
curl -fsS -X POST "$RK_URL/next" \
  -H "Content-Type: application/json" \
  -d '{}'
echo

echo "== flush events =="
curl -fsS -X POST "$RK_URL/internal/flush_events" \
  -H "Content-Type: application/json" \
  -d '{}'
echo

echo "Smoke test finished."
