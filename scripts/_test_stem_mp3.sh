#!/bin/bash
# Test stem streaming - check if MP3 is served
set -e
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"qqq","password":"12345678"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

echo "Token: ${TOKEN:0:20}..."

# Test song_id=2 stem (if it has stems with mp3 converted)
for stem in vocals drums bass other; do
  echo -n "stem=$stem: "
  curl -s -o /dev/null -w "type=%{content_type} size=%{size_download} code=%{http_code}" \
    "http://localhost:8000/api/stream/2/stem/$stem?token=$TOKEN" -r 0-1023
  echo
done
