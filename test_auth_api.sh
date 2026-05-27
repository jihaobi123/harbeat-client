#!/bin/bash

BASE_URL="http://localhost:8080"

echo "=== Testing User Authentication Module ==="
echo ""

# Test 1: Register new user
echo "1. Testing user registration..."
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser_'$(date +%s)'","password":"Test123456","dance_style":"hiphop","level":"beginner","favorite_style":"hiphop"}')
echo "Response: $REGISTER_RESPONSE"
ACCESS_TOKEN=$(echo $REGISTER_RESPONSE | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
REFRESH_TOKEN=$(echo $REGISTER_RESPONSE | grep -o '"refresh_token":"[^"]*' | cut -d'"' -f4)
echo "Access Token: ${ACCESS_TOKEN:0:50}..."
echo "Refresh Token: ${REFRESH_TOKEN:0:50}..."
echo ""

# Test 2: Get current user info
echo "2. Testing get current user info..."
ME_RESPONSE=$(curl -s -X GET "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN")
echo "Response: $ME_RESPONSE"
echo ""

# Test 3: Login with same user
echo "3. Testing user login..."
USERNAME=$(echo $REGISTER_RESPONSE | grep -o '"username":"[^"]*' | cut -d'"' -f4)
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"'$USERNAME'","password":"Test123456"}')
echo "Response: $LOGIN_RESPONSE"
echo ""

# Test 4: Refresh token
echo "4. Testing refresh token..."
REFRESH_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"'$REFRESH_TOKEN'"}')
echo "Response: $REFRESH_RESPONSE"
NEW_ACCESS_TOKEN=$(echo $REFRESH_RESPONSE | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
echo "New Access Token: ${NEW_ACCESS_TOKEN:0:50}..."
echo ""

# Test 5: Change password
echo "5. Testing change password..."
CHANGE_PWD_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/change-password" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"old_password":"Test123456","new_password":"NewTest123456"}')
echo "Response: $CHANGE_PWD_RESPONSE"
echo ""

# Test 6: Login with new password
echo "6. Testing login with new password..."
LOGIN2_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"'$USERNAME'","password":"NewTest123456"}')
echo "Response: $LOGIN2_RESPONSE"
NEW_TOKEN=$(echo $LOGIN2_RESPONSE | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)
echo ""

# Test 7: Logout
echo "7. Testing logout..."
LOGOUT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/logout" \
  -H "Authorization: Bearer $NEW_TOKEN")
echo "Response: $LOGOUT_RESPONSE"
echo ""

# Test 8: Deactivate account
echo "8. Testing account deactivation..."
DEACTIVATE_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/deactivate" \
  -H "Authorization: Bearer $NEW_TOKEN")
echo "Response: $DEACTIVATE_RESPONSE"
echo ""

# Test 9: Try to login with deactivated account
echo "9. Testing login with deactivated account (should fail)..."
LOGIN3_RESPONSE=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"'$USERNAME'","password":"NewTest123456"}')
echo "Response: $LOGIN3_RESPONSE"
echo ""

echo "=== All tests completed ==="
