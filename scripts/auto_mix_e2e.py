#!/usr/bin/env python3
"""End-to-end auto-mix smoke test.

Pipeline:
  1) login -> jetson access_token
  2) pick 3 analyzed songs (or use --songs override)
  3) /api/dj/sequence to order them by an energy curve
  4) for each pair (i, i+1):
       a) sync-worker push wav -> RK cache (if missing)
       b) edge-agent /play song i (first iteration only)
       c) poll /state until remaining <= XFADE_TRIGGER_SEC
       d) /api/dj/transitions/plan -> get rule_key + duration_sec
       e) edge-agent /xfade with mapped style and clamped fade_sec

Run from the workstation; jetson + RK must be reachable via TS / LAN.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from urllib import request, error, parse


JETSON = "http://8.136.120.255"  # cloud gateway (mobile default)
RK_EDGE = "http://192.168.43.7:9000"
RK_SYNC = "http://192.168.43.7:9100"
USER = "qqq"
PWD = "12345678"

XFADE_TRIGGER_SEC = 12.0  # start xfade this many seconds before track end

# Mirrors mobile/lib/src/dj_control_page.dart `_ruleKeyToRkStyle`.
RULE_KEY_TO_RK_STYLE = {
    # ANALYZED 11
    "harmonic_blend":    "blend",
    "eq_swap_4bar":      "filter",
    "filter_sweep_high": "filter",
    "drop_swap":         "bass_swap",
    "echo_tail":         "echo_freeze",
    "loop_roll":         "slam",
    "spin_back":         "cut",
    "drum_only_bridge":  "drum_swap",
    "key_lift":          "rise",
    "reverb_throw":      "echo_freeze",
    "back_to_back_drop": "slam",
    # RAW 7
    "raw_xfade_3s":   "blend",
    "raw_xfade_6s":   "blend",
    "raw_xfade_10s":  "melt",
    "raw_hard_cut":   "cut",
    "raw_fade_out_in":"fade",
    "raw_echo_drop":  "echo_freeze",
    "raw_lp_swap":    "filter",
}
RK_STYLES = {
    "smooth", "power", "bass_swap", "echo_out", "filter", "cut", "slam",
    "fade", "rise", "blend", "wave", "melt", "vocal_handoff", "vocal_ducking",
    "drum_swap", "instrumental_only", "vocal_solo_intro", "echo_freeze",
}


def http_json(method, url, body=None, token=None, timeout=15.0):
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {body[:300]}") from e


def login():
    r = http_json("POST", f"{JETSON}/api/auth/login",
                  {"username": USER, "password": PWD})
    return r["data"]["access_token"]


def pick_songs(token, n=3):
    r = http_json("GET", f"{JETSON}/api/library/songs?limit=50", token=token)
    songs = r.get("data", {}).get("songs", [])
    analyzed = [s for s in songs if s.get("bpm") and s.get("beat_points")]
    import random
    random.seed(42)
    pick = random.sample(analyzed, min(n, len(analyzed)))
    return pick


def sequence(token, song_ids, preset="battle_4rounds"):
    r = http_json("POST", f"{JETSON}/api/dj/sequence", token=token,
                  body={"song_ids": song_ids, "preset": preset})
    return r["data"]["sequence"]


def stream_url(token, song_id):
    # Mirrors HarBeatApiClient.streamUrl
    return f"{JETSON}/api/stream/{song_id}?token={parse.quote(token)}"


def sync_one(song_id, url, plan_id):
    body = {
        "tracks": [{
            "song_id": song_id,
            "files": {"original": {"url": url, "format": "mp3"}},
        }],
        "plan_id": plan_id,
    }
    r = http_json("POST", f"{RK_SYNC}/sync", body=body, timeout=180.0)
    return r


def wait_sync(plan_id, timeout=180.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        # sync-worker exposes /status (not /sync/status); check cache file
        # presence to decide done.
        r = http_json("GET", f"{RK_SYNC}/status")
        completed = r.get("completed", 0)
        total = r.get("total", 0)
        running = r.get("running", False)
        cur = r.get("current_file")
        if total > 0 and completed >= total and not running:
            return r
        if r.get("errors"):
            raise RuntimeError(f"sync errors: {r['errors']}")
        print(f"    [sync] {completed}/{total} running={running} cur={cur}", flush=True)
        time.sleep(1.0)
    raise RuntimeError(f"sync timeout for plan {plan_id}")


def ensure_rk_cache(token, song_id):
    # Skip if already cached
    try:
        r = http_json("GET", f"{RK_SYNC}/cache/check?song_id={song_id}")
        if r.get("exists"):
            print(f"  [cache] hit: {song_id[:8]} ({r.get('size',0)//1024}KB)", flush=True)
            return
    except Exception as e:
        print(f"  [cache] check failed: {e}", flush=True)

    plan_id = f"e2e-{int(time.time()*1000)}-{song_id[:8]}"
    url = stream_url(token, song_id)
    print(f"  [sync] song={song_id[:8]} plan={plan_id}", flush=True)
    sync_one(song_id, url, plan_id)
    st = wait_sync(plan_id)
    print(f"  [sync] OK ({st.get('completed')}/{st.get('total')})", flush=True)


def play(song_id, start_at_sec=0.0):
    return http_json("POST", f"{RK_EDGE}/play",
                     body={"song_id": song_id, "start_at_sec": start_at_sec})


def get_state():
    return http_json("GET", f"{RK_EDGE}/state")


def plan_transition(token, prev_id, next_id, cursor):
    r = http_json("POST", f"{JETSON}/api/dj/transitions/plan", token=token,
                  body={"prev_song_id": prev_id, "next_song_id": next_id,
                        "cursor_sec": cursor})
    return r["data"]


def map_style(rule_key):
    if rule_key in RK_STYLES:
        return rule_key
    return RULE_KEY_TO_RK_STYLE.get(rule_key, "blend")


def xfade(to_id, fade_sec, style):
    fade_sec = max(0.05, min(30.0, fade_sec))
    return http_json("POST", f"{RK_EDGE}/xfade", body={
        "to_song_id": to_id, "fade_sec": fade_sec, "to_at_sec": 0.0,
        "style": style,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--songs", nargs="+", help="override song IDs")
    ap.add_argument("--preset", default="battle_4rounds")
    ap.add_argument("--seek-near-end", type=float, default=0.0,
                    help="if >0, seek every song to (duration - this) seconds "
                         "to make xfades trigger fast (smoke-test mode)")
    args = ap.parse_args()

    print("== auto-mix e2e ==", flush=True)
    print("[1] login...", flush=True)
    token = login()
    print(f"    token len={len(token)}", flush=True)

    if args.songs:
        chosen = [{"id": sid, "title": sid[:8]} for sid in args.songs]
    else:
        print("[2] pick 3 random analyzed songs...", flush=True)
        chosen = pick_songs(token, 3)
    for s in chosen:
        print(f"    - {s['id']} {s.get('title','?')[:30]} bpm={s.get('bpm','?')}", flush=True)

    song_ids = [s["id"] for s in chosen]

    print(f"[3] sequence (preset={args.preset})...", flush=True)
    seq = sequence(token, song_ids, args.preset)
    ordered_ids = [e["song_id"] for e in seq]
    for e in seq:
        print(f"    #{e['position']+1} {e['song_id'][:8]} tgt={e['target_energy']:.2f} act={e['actual_energy']:.2f}", flush=True)

    print("[4] sync first track to RK + start playback...", flush=True)
    ensure_rk_cache(token, ordered_ids[0])
    play(ordered_ids[0])
    print(f"    PLAY {ordered_ids[0][:8]}", flush=True)
    if args.seek_near_end > 0:
        time.sleep(0.6)
        st0 = get_state()
        dur0 = st0.get("duration_sec", 0)
        seek_to = max(0, dur0 - args.seek_near_end)
        if seek_to > 0:
            http_json("POST", f"{RK_EDGE}/seek", body={"sec": seek_to})
            print(f"    SEEK -> {seek_to:.1f}s (dur={dur0:.1f}s)", flush=True)

    for i in range(len(ordered_ids) - 1):
        prev_id = ordered_ids[i]
        next_id = ordered_ids[i + 1]
        print(f"[5.{i+1}] prefetch next {next_id[:8]} ...", flush=True)
        ensure_rk_cache(token, next_id)

        print(f"[6.{i+1}] poll /state until remaining <= {XFADE_TRIGGER_SEC}s ...", flush=True)
        last_log = 0
        while True:
            st = get_state()
            pos = st.get("position_sec", 0.0)
            dur = st.get("duration_sec", 0.0)
            playing = st.get("playing", False)
            cur = st.get("current_song_id")
            remaining = (dur - pos) if dur > 0 else None
            if time.time() - last_log > 5:
                print(f"    pos={pos:.1f}s dur={dur:.1f}s play={playing} cur={str(cur)[:8]}", flush=True)
                last_log = time.time()
            if remaining is not None and remaining <= XFADE_TRIGGER_SEC:
                break
            if not playing and pos > 0 and dur > 0:
                # EOF safety net
                print(f"    EOF detected (pos={pos:.1f} dur={dur:.1f}); triggering xfade", flush=True)
                break
            time.sleep(0.6)

        cursor = st.get("position_sec", 0.0)
        print(f"[7.{i+1}] plan transition prev={prev_id[:8]} next={next_id[:8]} cursor={cursor:.1f}", flush=True)
        plan = plan_transition(token, prev_id, next_id, cursor)
        rule_key = plan.get("rule_key", "raw_xfade_6s")
        rule_label = plan.get("rule_label_zh", rule_key)
        duration_sec = plan.get("duration_sec", plan.get("fade_sec", 6.0))
        style = map_style(rule_key)
        print(f"    rule={rule_key} ({rule_label}) -> RK style={style}, fade={duration_sec:.1f}s", flush=True)

        print(f"[8.{i+1}] /xfade ...", flush=True)
        xfade(next_id, duration_sec, style)
        print(f"    XFADE -> {next_id[:8]} done", flush=True)

        # If smoke-test mode, seek the new track to near its end so the next
        # iteration triggers fast.
        if args.seek_near_end > 0 and i + 1 < len(ordered_ids) - 1:
            # Wait for xfade to commit so /state reflects the new song
            time.sleep(max(2.0, duration_sec * 0.6))
            stN = get_state()
            durN = stN.get("duration_sec", 0)
            seek_to = max(0, durN - args.seek_near_end)
            if seek_to > 0:
                http_json("POST", f"{RK_EDGE}/seek", body={"sec": seek_to})
                print(f"    SEEK -> {seek_to:.1f}s (dur={durN:.1f}s)", flush=True)

    # Watch the final track until it finishes (or 30s, whichever is shorter
    # past the last xfade) so we can confirm clean playback.
    print("[9] watch final track for 20s ...", flush=True)
    t0 = time.time()
    while time.time() - t0 < 20:
        st = get_state()
        print(f"    pos={st.get('position_sec',0):.1f}s play={st.get('playing')} cur={str(st.get('current_song_id'))[:8]}", flush=True)
        time.sleep(3)

    print("== DONE ==", flush=True)


if __name__ == "__main__":
    sys.exit(main())
