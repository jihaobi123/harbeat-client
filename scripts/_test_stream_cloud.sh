#!/bin/bash
# Test latency from cloud server to Jetson (via Tailscale) 
# This simulates the real user path: browser -> cloud -> Tailscale -> Jetson

JETSON="http://100.91.30.53:8000"

# Login
TOKEN=$(curl -s -X POST "$JETSON/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"qqq","password":"12345678"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('access_token',''))")

echo "Token: ${TOKEN:0:20}..."
SONG_ID="c9ab2d36cdd8402683e866eed36f6d31"

echo ""
echo "=== Full MP3 download (3.4MB) via Tailscale ==="
curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes\n  First byte: %{time_starttransfer}s\n  Total: %{time_total}s\n  Speed: %{speed_download} B/s\n" \
  "$JETSON/api/stream/$SONG_ID?token=$TOKEN"

echo ""
echo "=== Range 0-64KB via Tailscale ==="
curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes\n  First byte: %{time_starttransfer}s\n  Total: %{time_total}s\n" \
  -H "Range: bytes=0-65535" \
  "$JETSON/api/stream/$SONG_ID?token=$TOKEN"

# Get a song that has stems
STEM_SONG=$(curl -s -H "Authorization: Bearer $TOKEN" "$JETSON/api/library/songs" | \
  python3 -c "
import sys,json
data=json.load(sys.stdin)
songs=data.get('data',{}).get('songs',[])
for s in songs:
    if s.get('stems'):
        print(s['id'], s['title'])
        break
" 2>/dev/null)

STEM_ID=$(echo "$STEM_SONG" | cut -d' ' -f1)
STEM_TITLE=$(echo "$STEM_SONG" | cut -d' ' -f2-)
echo ""
echo "=== Found song with stems: $STEM_TITLE ($STEM_ID) ==="

if [ -n "$STEM_ID" ]; then
  for STEM in vocals drums bass other; do
    echo "--- Stem: $STEM ---"
    curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes, first_byte: %{time_starttransfer}s, total: %{time_total}s\n" \
      "$JETSON/api/stream/$STEM_ID/stem/$STEM?token=$TOKEN"
  done
  
  echo ""
  echo "=== Full vocals stem download ==="
  curl -s -o /dev/null -w "  HTTP %{http_code}, size: %{size_download} bytes\n  First byte: %{time_starttransfer}s\n  Total: %{time_total}s\n  Speed: %{speed_download} B/s\n" \
    "$JETSON/api/stream/$STEM_ID/stem/vocals?token=$TOKEN"
fi

echo ""
echo "Done!"
