#!/bin/bash
BASE_URL="http://localhost:8000"

echo "=== 1. Register ==="
RESP=$(curl -s -X POST $BASE_URL/api/auth/register -H "Content-Type: application/json" -d '{"username":"test'$(date +%s)'","password":"Test123456","dance_style":"hiphop","level":"beginner","favorite_style":"hiphop"}')
echo $RESP | python3 -m json.tool
TOKEN=$(echo $RESP | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

echo -e "\n=== 2. Get Me ==="
curl -s -X GET $BASE_URL/api/auth/me -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\n=== 3. Refresh Token ==="
REFRESH=$(echo $RESP | grep -o '"refresh_token":"[^"]*' | cut -d'"' -f4)
curl -s -X POST $BASE_URL/api/auth/refresh -H "Content-Type: application/json" -d '{"refresh_token":"'$REFRESH'"}' | python3 -m json.tool

echo -e "\n=== 4. Change Password ==="
curl -s -X POST $BASE_URL/api/auth/change-password -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"old_password":"Test123456","new_password":"NewPass123"}' | python3 -m json.tool

echo -e "\n=== 5. Logout ==="
curl -s -X POST $BASE_URL/api/auth/logout -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

echo -e "\n=== Done ==="
