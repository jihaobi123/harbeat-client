#!/bin/bash
# Test stream API performance 
# Get token first - try several user/password combos
for CREDS in 'qqq:12345678' 'q:12345678' 'mark:123456' 'admin:admin123'; do
  USER=${CREDS%%:*}
  PASS=${CREDS##*:}
  RESP=$(curl -s -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USER\",\"password\":\"$PASS\"}" 2>/dev/null)
  TOKEN=$(echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))" 2>/dev/null)
  if [ -n "$TOKEN" ]; then
    echo "Authenticated as $USER"
    break
  fi
done

if [ -z "$TOKEN" ]; then
  echo "Could not authenticate. Response was: $RESP"
  exit 1
fi

echo "Got token: ${TOKEN:0:20}..."

# Get first song ID 
SONGS_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/library/songs")
echo "Songs response (first 200 chars): ${SONGS_RESP:0:200}"
SONG_ID=$(echo "$SONGS_RESP" | python3 -c "
import sys,json
data=json.load(sys.stdin)
songs=data.get('data',{}).get('songs',[])
if not songs:
    songs=data.get('songs',[])
# pick first song that has file_size > 0
for s in songs:
    print(s['id'])
    break
" 2>/dev/null)

echo "Song ID: $SONG_ID"

if [ -z "$SONG_ID" ]; then
  echo "No songs found"
  exit 1
fi

# Test 1: Stream full download (simulates extractPeaks fetch)
echo ""
echo "=== Test 1: Full stream download (simulates extractPeaks) ==="
curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes\n  First byte: %{time_starttransfer}s\n  Total time: %{time_total}s\n  Speed: %{speed_download} bytes/s\n" \
  "http://localhost:8000/api/stream/$SONG_ID?token=$TOKEN"

# Test 2: Range request (simulates <audio> metadata loading)
echo ""
echo "=== Test 2: Range request 0-64KB (audio metadata) ==="
curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes\n  First byte: %{time_starttransfer}s\n  Total time: %{time_total}s\n" \
  -H "Range: bytes=0-65535" \
  "http://localhost:8000/api/stream/$SONG_ID?token=$TOKEN"

# Test 3: Check stems for this song
echo ""
echo "=== Test 3: Stem streaming ==="
for STEM in vocals drums bass other; do
  echo "--- Stem: $STEM ---"
  curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes, first_byte: %{time_starttransfer}s, total: %{time_total}s\n" \
    -H "Range: bytes=0-65535" \
    "http://localhost:8000/api/stream/$SONG_ID/stem/$STEM?token=$TOKEN"
done

# Test 4: Full stem download
echo ""
echo "=== Test 4: Full stem download (vocals) ==="
curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes\n  First byte: %{time_starttransfer}s\n  Total time: %{time_total}s\n  Speed: %{speed_download} bytes/s\n" \
  "http://localhost:8000/api/stream/$SONG_ID/stem/vocals?token=$TOKEN"

echo ""
echo "Done!"
