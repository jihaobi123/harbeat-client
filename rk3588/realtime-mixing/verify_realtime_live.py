"""Authorized physical-engine test. Ends paused, never claims real BLE gestures.

Uses diagnostic seek before later transitions to avoid listening through all 8
whole tracks. Commands still schedule/mix against the real audio callback.
"""
import json
from pathlib import Path
import time
import sys
import urllib.request
import urllib.error
from realtime import BASE, CONTROL, rpc, load_catalog, exit_candidates
USE_HTTP='--http' in sys.argv
USE_TEMPO='--tempo' in sys.argv
from prepare_tempo import playback_time

report = {'started_at':time.time(), 'checks':[], 'transitions':[],
          'physical_gesture_verified':False, 'acoustic_listening_verified':False,
          'diagnostic_seeks_used':True, 'mode':'live_original_speed_dual_deck'}
report['command_transport']='HTTP simulated device events' if USE_HTTP else 'Unix socket'
if USE_TEMPO:
    report['mode']='live_dual_deck_vocal_v4_tempo'
catalog, v4 = load_catalog()
def check(name, condition, **details):
    row = dict(name=name, passed=bool(condition), **details)
    report['checks'].append(row)
    print(json.dumps(row), flush=True)
    if not condition:
        raise AssertionError(name)

def call(cmd, **args):
    if USE_HTTP:
        payload=dict(schema_version='harbeat.control.v1',source='simulator',
            device_id='sim-ring' if cmd in ('gesture','trigger_effect') else 'sim-wrist',
            boot_id='integration-'+str(report['started_at']),event_id=str(time.time_ns()),action=cmd,params=args)
        request=urllib.request.Request('http://127.0.0.1:9130/v1/device-events',
            data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ValueError(json.load(exc).get('error')) from exc
    return rpc(dict(cmd=cmd, request_id='verify-'+str(time.time_ns()), **args), path=CONTROL)

def state():
    return rpc({'cmd':'get_state'}, path=CONTROL)

before = rpc({'cmd':'state'})
report['before'] = before
try:
    check('not_interrupting_other_playback', not before['playing'] and not before['in_transition'])
    call('start')
    time.sleep(1)
    a = state()
    report['after_start'] = a['engine']
    check('start_advances_audio', a['engine']['playing'] and a['engine']['position_sec'] > 0.5)
    call('pause')
    p = state()['engine']['position_sec']
    time.sleep(1)
    b = state()
    check('pause_freezes_position', b['engine']['paused'] and abs(b['engine']['position_sec']-p)<0.03)
    try:
        call('gesture', gesture_id='flick_up')
        blocked=False
    except ValueError:
        blocked=True
    check('paused_gesture_command_rejected', blocked)
    call('start')
    time.sleep(0.5)
    check('resume_continues', state()['engine']['position_sec']>p+0.3)
    for gesture in ('punch_forward','flick_up','swipe_side','wrist_roll'):
        sent_at=time.monotonic()
        r = call('gesture',gesture_id=gesture)
        check('software_gesture_'+gesture, r.get('action')=='one_shot' and not r['physical_gesture_verified']
              and time.monotonic()-sent_at<10, result=r, observed_within_seconds=10)
        time.sleep(1.5)
    for i in range(7):
        s = state()
        tid = s['current_track_id']
        row = catalog[tid]
        source_pos=s['source_position_sec'] if USE_TEMPO else s['engine']['position_sec']
        # The active auto plan has already resolved the original-v4 next pair.
        fade=s['pending']['fade_sec'] if USE_TEMPO else 12
        points = exit_candidates(row['manifest'],row['bars'],source_pos,fade=fade)
        check('future_candidate_'+str(i), bool(points), current=tid)
        # Clear previous auto plan before a diagnostic forward seek; never seek in fade.
        rpc({'cmd':'load_plan','mix_plan':{}})
        if points[0][0] - source_pos > 6:
            seek_at=playback_time(s['active_asset'],points[0][0]-4.5) if USE_TEMPO else points[0][0]-4.5
            rpc({'cmd':'seek','sec':seek_at})
        accepted = call('next')
        pending = accepted['pending']
        nearest = exit_candidates(row['manifest'],row['bars'],pending['requested_at_position'],fade=pending['fade_sec'])[0][0]
        check('nearest_candidate_'+str(i), abs(nearest-pending['from_at_sec'])<0.001, pending=pending)
        if USE_TEMPO:
            from harbeat.transition import build_transition_plan
            from harbeat.models import TransitionConfig
            expected=build_transition_plan(row['bundle'].track,catalog[pending['to_track_id']]['bundle'].track,
                                            TransitionConfig(mini_set_size=8))
            check('v4_entry_rate_'+str(i),abs(pending['entry_rate']-expected.bpm_plan.playback_rate)<1e-9)
            expected_fade=v4.overlap_seconds(expected.method.value,row['bundle'].track.bpm,
                                             catalog[pending['to_track_id']]['bundle'].track.bpm)
            check('v4_overlap_'+str(i),pending['fade_sec']==expected_fade)
        again = call('next')
        check('duplicate_next_not_rescheduled_'+str(i), again['status']=='already_scheduled')
        # First transition also exercises paused countdown, not wall-clock scheduling.
        if i==0:
            call('pause')
            countdown=state()['engine']['next_transition_in_sec']
            time.sleep(1)
            check('paused_countdown_frozen', abs(state()['engine']['next_transition_in_sec']-countdown)<0.03)
            call('start')
        native_cue=pending['from_playback_at_sec'] if USE_TEMPO else pending['from_at_sec']
        deadline=time.monotonic()+max(25,native_cue-state()['engine']['position_sec']+pending['fade_sec']+8)
        transition_seen=False
        actual=None
        paused_mid=False
        while time.monotonic()<deadline:
            s=state()
            if s['engine']['in_transition']:
                if not transition_seen:
                    actual=s['engine']['position_sec']
                transition_seen=True
                if i==0 and not paused_mid:
                    call('pause')
                    mid=state()
                    time.sleep(1)
                    frozen=state()
                    check('pause_during_fade', frozen['engine']['in_transition'] and
                        abs(frozen['engine']['position_sec']-mid['engine']['position_sec'])<0.03)
                    try:
                        call('next')
                        busy=False
                    except ValueError:
                        busy=True
                    check('next_during_fade_rejected',busy)
                    call('start')
                    paused_mid=True
            if s['current_track_id']==pending['to_track_id'] and not s['engine']['in_transition']:
                break
            time.sleep(0.05)
        check('live_crossfade_completed_'+str(i), transition_seen and s['current_track_id']==pending['to_track_id']
              and not s['engine']['in_transition'], first_observed_at=actual)
        check('trigger_timing_'+str(i), actual is not None and -0.03 <= actual-native_cue<0.3,
              observed_error_ms=None if actual is None else (actual-native_cue)*1000)
        report['transitions'].append(dict(pending, first_observed_position=actual, after=s['engine']))
    call('stop')
    check('stop_is_pause',state()['engine']['paused'])
    time.sleep(0.3)
    report['after']=rpc({'cmd':'state'})
    report['xrun_delta']=report['after']['audio_xrun_count']-before['audio_xrun_count']
    report['control_status']='passed'
    report['audio_stability_status']='passed' if report['xrun_delta']==0 else 'failed_underflow'
    report['status']='passed' if report['xrun_delta']==0 else 'partial_audio_underflow'
except Exception as exc:
    report['status']='failed'
    report['error']=repr(exc)
    raise
finally:
    try:
        call('pause')
    except Exception:
        pass
    report['finished_at']=time.time()
    name='realtime_tempo_http_test.json' if USE_TEMPO else ('realtime_simulated_http_test.json' if USE_HTTP else 'realtime_live_test.json')
    target=BASE/'reports'/name
    target.write_text(json.dumps(report,indent=2))
    # Never lose earlier measurements when rerunning an experiment.
    archived=target.with_name(target.stem+'-'+str(int(report['started_at']))+'.json')
    archived.write_text(json.dumps(report,indent=2))
    print(json.dumps({'status':report['status'],'report':str(target)}),flush=True)
