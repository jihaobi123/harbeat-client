#!/usr/bin/env python3
"""EDM live-control prototype; original-speed, native two-deck playback.

No whole-mixtape rendering. Never edits the original v4 or live engine source.
The local control socket is private to cat. This is NOT a BLE classifier.
"""
import argparse
import fcntl
from collections import OrderedDict
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import stat
import sys
import threading
import time

BASE = Path('/home/cat/harbeat-mixing-v1')
CONTROL = str(BASE / 'realtime.sock')
ENGINE = '/tmp/cypher-audio.sock'


def recv_exact(s, size):
    data = b''
    while len(data) < size:
        chunk = s.recv(size - len(data))
        if not chunk:
            raise ConnectionError('Truncated frame')
        data += chunk
    return data


def receive(s):
    n = struct.unpack('>I', recv_exact(s, 4))[0]
    if not 0 < n <= 65536:
        raise ValueError('Invalid frame size')
    return json.loads(recv_exact(s, n))


def send(s, data):
    b = json.dumps(data, ensure_ascii=False).encode()
    s.sendall(struct.pack('>I', len(b)) + b)


def rpc(data, path=ENGINE, timeout=30):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        send(s, data)
        result = receive(s)
    if not result.get('ok'):
        raise ValueError(result.get('error', str(result)))
    return result


def exit_candidates(manifest, bars, position, lead=3.0, fade=12.0):
    """All bar starts INSIDE source out/both windows, not one per window.

    Only use section-boundary fallback if no future window candidate remains.
    Never claim a point outside its window belongs to that window.
    """
    minimum = position + lead
    maximum = manifest['source']['duration_ms'] / 1000 - fade - 0.5
    future = sorted(set(b / 1000 for b in bars if minimum <= b / 1000 <= maximum))
    windows = [w for w in manifest['analysis'].get('transition_windows', [])
               if w.get('role') in ('out', 'both')]
    cues = [(b, 'out_window') for b in future if any(
        w['start_ms'] / 1000 <= b <= w['end_ms'] / 1000 for w in windows)]
    if cues:
        return cues
    ends = [s['end_ms'] / 1000 for s in manifest['analysis']['sections'].get('items', [])]
    fallback = sorted(set(min(future, key=lambda b: abs(b - end)) for end in ends
                          if future and minimum <= end <= maximum))
    return [(b, 'section_bar_fallback') for b in fallback]


def load_catalog():
    release = BASE / 'releases/harbeat_mixing_algorithm_vocal_v4_20260913'
    sys.path.insert(0, str(release))
    spec = importlib.util.spec_from_file_location('v4_live_baseline', release / 'scripts/render_edm_bundle_smooth_v3.py')
    v4 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = v4
    spec.loader.exec_module(v4)
    from harbeat import read_track_preprocess_from_manifest_key
    root = BASE / 'data/edm_8_bundle'
    report = json.loads((BASE / 'reports/data_validation.json').read_text())
    if report['status'] != 'ready':
        raise ValueError('Input validation not ready')
    result = {}
    for row in report['tracks']:
        manifest = json.loads(Path(row['manifest_path']).read_text())
        # Recheck metadata binding on every startup; full assets validated by manage.py.
        import hashlib
        if hashlib.sha256(Path(row['manifest_path']).read_bytes()).hexdigest() != row['manifest_sha256']:
            raise ValueError('Manifest changed')
        bundle = read_track_preprocess_from_manifest_key(str(Path(row['manifest_path']).relative_to(root)),
            root=root, expected_track_id=row['track_id'], expected_analysis_run_id=row['analysis_run_id'],
            style='EDM', allow_degraded=True, verify_assets=False)
        vocal = json.loads(Path(row['vocal_activity_path']).read_text())
        intervals = [(i['start_ms'], i['end_ms']) for i in vocal['intervals']]
        tid = row['track_id']
        sid = 'rtv1-' + tid.removeprefix('track-')
        result[tid] = dict(row, manifest=manifest, bundle=bundle, intervals=intervals,
                           bars=v4.bars_ms(manifest), song_id=sid)
    return result, v4


class Controller:
    def __init__(self, catalog, v4, call=rpc):
        self.catalog, self.v4, self.call = catalog, v4, call
        self.ids = list(catalog)
        self.by_sid = {r['song_id']: tid for tid, r in catalog.items()}
        self.visited = []
        self.pending = None
        self.active = False
        self.last_error = None
        self.events = []
        self.dedup = OrderedDict()
        self.lock = threading.RLock()
        self.auto_failed_track = None

    def event(self, event, **fields):
        row = dict(at=time.time(), event=event, **fields)
        self.events.append(row)
        self.events = self.events[-100:]
        print(json.dumps(row, ensure_ascii=False), flush=True)

    def state(self):
        s = self.call({'cmd': 'state'})
        return dict(ok=True, engine=s, active=self.active, pending=self.pending,
                    current_track_id=self.by_sid.get(str(s.get('current_song_id'))),
                    visited=self.visited[:], last_error=self.last_error,
                    mode='live_dual_deck_original_speed', available_styles=['EDM'],
                    events=self.events[-12:])

    def prepare(self, ids):
        result = self.call({'cmd': 'prefetch', 'song_ids': [self.catalog[t]['song_id'] for t in ids],
                            'wait': True, 'load_stems': False})
        if not result.get('all_ready'):
            raise ValueError('Audio prefetch failed: ' + str(result.get('failed')))

    def schedule(self, request_id, target=None, auto=False):
        s = self.call({'cmd': 'state'})
        if s['in_transition']:
            raise ValueError('transition_busy')
        tid = self.by_sid.get(str(s['current_song_id']))
        if not self.active or tid is None:
            raise ValueError('session_not_started')
        if self.pending and not self.pending['auto']:
            return dict(ok=True, status='already_scheduled', pending=self.pending)
        candidates = [t for t in self.ids if t not in self.visited and t != tid]
        if target is not None:
            if target not in candidates:
                raise ValueError('target_unavailable_or_already_played')
            candidates = [target]
        if not candidates:
            raise ValueError('queue_exhausted')
        self.prepare(candidates)
        s = self.call({'cmd': 'state'})
        if self.by_sid.get(str(s['current_song_id'])) != tid or s['in_transition']:
            raise ValueError('playback_changed_during_preparation')
        row = self.catalog[tid]
        # Auto mode waits for the late-song region. Manual chooses nearest available now.
        position = s['position_sec']
        points = exit_candidates(row['manifest'], row['bars'], position)
        if not points:
            raise ValueError('no_future_candidate_with_enough_audio')
        cue, reason = (min(points, key=lambda p: abs(p[0] - (row['manifest']['source']['duration_ms']/1000-30)))
                       if auto else points[0])
        from harbeat.drums import drum_overlap_score
        scored = []
        for nxt in candidates:
            b = self.catalog[nxt]
            entry = self.v4.choose_entry_cue(b['manifest'], first_track=False,
                vocal_intervals=b['intervals'], incoming_overlap_ms=12000).time_ms / 1000
            a_bpm = self.v4.effective_mix_bpm(row['bundle'].track.bpm)
            b_bpm = self.v4.effective_mix_bpm(b['bundle'].track.bpm)
            score = (0.30 * max(0, 1-abs(a_bpm-b_bpm)/30)
                     + 0.24 * drum_overlap_score(row['bundle'].track.drum_profile, b['bundle'].track.drum_profile)
                     - 0.62 * self.v4.vocal_ratio(b['intervals'], int(entry*1000), int((entry+12)*1000)))
            scored.append((score, nxt, entry))
        _, nxt, entry = max(scored, key=lambda x: (x[0], x[1]))
        pending = dict(request_id=request_id, from_track_id=tid, to_track_id=nxt,
                       from_at_sec=cue, to_at_sec=entry, fade_sec=12.0,
                       candidate_reason=reason, requested_at_position=position, auto=auto, status='scheduled')
        # Native callback schedules against AUDIO frames. No polling-triggered xfade.
        plan = {'plan_id': 'rtv1-' + request_id,
                'tracks': [row['song_id'], self.catalog[nxt]['song_id']],
                'transitions': [dict(from_song_id=row['song_id'], to_song_id=self.catalog[nxt]['song_id'],
                    from_at_sec=cue, to_at_sec=entry, fade_sec=12.0, fade_curve='linear',
                    style='smooth', transition_id=request_id)]}
        self.call({'cmd': 'load_plan', 'mix_plan': plan})
        self.pending = pending
        self.event('scheduled', **pending)
        return dict(ok=True, status='scheduled', pending=dict(pending))

    def tick(self):
        if not self.active:
            return
        s = self.call({'cmd': 'state'})
        tid = self.by_sid.get(str(s['current_song_id']))
        if tid is None:
            self.active = False
            self.pending = None
            self.event('external_player_takeover')
            return
        if self.pending:
            if s['in_transition'] and self.pending['status'] != 'transitioning':
                self.pending['status'] = 'transitioning'
                self.event('transitioning', actual_position=s['position_sec'], **self.pending)
            if tid == self.pending['to_track_id'] and not s['in_transition']:
                self.event('completed', **{k:v for k,v in self.pending.items() if k != 'status'})
                if tid not in self.visited:
                    self.visited.append(tid)
                self.pending = None
                self.auto_failed_track = None
        if not s['playing'] and not s['paused']:
            self.active = False
            self.event('ended')
        elif not self.pending and len(self.visited) < len(self.ids) and self.auto_failed_track != tid:
            try:
                self.schedule('auto-' + str(time.time_ns()), auto=True)
            except ValueError as exc:
                self.last_error = str(exc)
                self.auto_failed_track = tid
                self.event('auto_schedule_failed', track_id=tid, error=str(exc))

    def command(self, msg):
        with self.lock:
            cmd = msg.get('cmd')
            if cmd == 'get_state':
                return self.state()
            rid = msg.get('request_id')
            if not isinstance(rid, str) or not 1 <= len(rid) <= 128:
                raise ValueError('request_id_required')
            encoded = json.dumps(msg, sort_keys=True)
            if rid in self.dedup:
                old, result = self.dedup[rid]
                if old != encoded:
                    raise ValueError('request_id_conflict')
                return result
            if cmd == 'start':
                if self.active:
                    result = self.call({'cmd': 'resume'})
                else:
                    s = self.call({'cmd': 'state'})
                    if s['playing'] or s['in_transition']:
                        raise ValueError('another_session_is_playing')
                    first = msg.get('track_id', self.ids[0])
                    if first not in self.catalog:
                        raise ValueError('unknown_track')
                    self.prepare(self.ids)
                    self.call({'cmd': 'load_plan', 'mix_plan': {}})
                    result = self.call({'cmd': 'play', 'song_id': self.catalog[first]['song_id'], 'load_stems': False})
                    self.active, self.visited, self.pending = True, [first], None
                result = dict(result, status='playing')
            elif cmd in ('pause', 'stop'):
                if not self.active:
                    raise ValueError('session_not_started')
                result = dict(self.call({'cmd': 'pause'}), status='paused')
            elif cmd == 'reset_session':
                s = self.call({'cmd':'state'})
                if str(s.get('current_song_id')) not in self.by_sid:
                    raise ValueError('not_our_session')
                self.call({'cmd':'pause'})
                self.call({'cmd':'load_plan','mix_plan':{}})
                self.active, self.visited, self.pending = False, [], None
                self.auto_failed_track = None
                result = dict(ok=True, status='idle')
            elif cmd == 'next':
                result = self.schedule(rid, msg.get('track_id'))
            elif cmd == 'set_style':
                if msg.get('style_id') != 'EDM':
                    raise ValueError('style_assets_not_ready')
                result = dict(ok=True, status='unchanged', style_id='EDM')
            elif cmd in ('trigger_effect', 'gesture'):
                s = self.call({'cmd': 'state'})
                if not self.active or not s['playing']:
                    raise ValueError('playback_paused_or_inactive')
                mapping = {'punch_forward': 'snare_impact', 'flick_up': 'air_horn',
                           'swipe_side': 'beat_stutter', 'wrist_roll': 'bass_drop'}
                effect = msg.get('effect_id') if cmd == 'trigger_effect' else mapping.get(msg.get('gesture_id'))
                if not effect:
                    raise ValueError('unknown_gesture')
                result = self.call({'cmd': 'trigger_effect', 'effect': effect})
                result.update(input_source='software_command', physical_gesture_verified=False)
            else:
                raise ValueError('unknown_command')
            self.event('command', cmd=cmd, request_id=rid)
            self.dedup[rid] = (encoded, result)
            while len(self.dedup) > 512:
                self.dedup.popitem(last=False)
            return result


def serve(tempo=False):
    lock_file = (BASE / 'realtime.lock').open('a')
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    catalog, v4 = load_catalog()
    if tempo:
        from tempo_control import TempoController
        control = TempoController(catalog, v4)
    else:
        control = Controller(catalog, v4)
    if Path(CONTROL).exists():
        info = Path(CONTROL).lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError('Refusing to remove unexpected socket path')
        Path(CONTROL).unlink()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(CONTROL)
        os.chmod(CONTROL, 0o600)
        server.listen(8)
        server.settimeout(0.1)
        try:
            while True:
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    conn = None
                if conn:
                    with conn:
                        conn.settimeout(2)
                        try:
                            send(conn, control.command(receive(conn)))
                        except Exception as exc:
                            send(conn, dict(ok=False, error=str(exc)))
                try:
                    control.tick()
                except Exception as exc:
                    control.last_error = str(exc)
        finally:
            Path(CONTROL).unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['serve', 'call'])
    parser.add_argument('json', nargs='?')
    parser.add_argument('--tempo', action='store_true')
    args = parser.parse_args()
    if args.action == 'serve':
        serve(args.tempo)
    else:
        print(json.dumps(rpc(json.loads(args.json), path=CONTROL), ensure_ascii=False, indent=2))
