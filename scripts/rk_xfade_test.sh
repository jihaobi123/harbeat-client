#!/bin/bash
# Quick xfade smoke test on RK.
set -e
curl -s -X POST http://127.0.0.1:9000/play -H "Content-Type: application/json" \
  -d '{"song_id":"11ae4acdc4fc4102947e1b5f932c1b17","start_at_sec":0}'
echo
sleep 3
echo "-- triggering xfade to 09bac7be20e6418b8d3c6a150fb61a16 --"
curl -s -X POST http://127.0.0.1:9000/xfade -H "Content-Type: application/json" \
  -d '{"to_song_id":"09bac7be20e6418b8d3c6a150fb61a16","fade_sec":6,"to_at_sec":0,"style":"blend"}'
echo
sleep 8
curl -s http://127.0.0.1:9000/state
echo
