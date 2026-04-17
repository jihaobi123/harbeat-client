#!/bin/bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"qqq","password":"12345678"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "TOKEN=$TOKEN"
curl -s -X POST http://localhost:8000/api/playlists/generate-dj-mix-plan \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"playlist_id":8,"duration_minutes":5,"style":"breaking","user_id":8}' 2>&1
echo ""
echo "DONE"
