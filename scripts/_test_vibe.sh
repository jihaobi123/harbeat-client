#!/bin/bash
curl -s -m 120 -w "\nHTTP_CODE:%{http_code}\nTIME:%{time_total}" \
  http://127.0.0.1:8000/api/recommendations/vibe-search \
  -X POST -H 'Content-Type: application/json' \
  -d '{"query":"battle","top_k":5}' 2>&1 | tail -c 800
