#!/usr/bin/env python3
"""Local-only hardware gateway contract. No BLE, IMU or button firmware here."""
import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time
from realtime import CONTROL, rpc

API_VERSION = 'harbeat.control.v1'
GESTURES = {'punch_forward':'snare_impact','flick_up':'air_horn',
            'swipe_side':'beat_stutter','wrist_roll':'bass_drop'}
COMMANDS = {'start','pause','stop','next','set_style','trigger_effect','gesture','reset_session'}


def translate_event(payload):
    """Deterministic ID across reconnect/retry. Different payload same ID conflicts downstream."""
    if not isinstance(payload,dict) or payload.get('schema_version') != API_VERSION:
        raise ValueError('unsupported_schema_version')
    for name in ('source','device_id','boot_id','event_id'):
        if not isinstance(payload.get(name),str) or not 1<=len(payload[name])<=128:
            raise ValueError('invalid_'+name)
    if payload['source'] not in ('simulator','ring_gateway','wrist_gateway','test_client'):
        raise ValueError('invalid_source')
    action=payload.get('action')
    if action not in COMMANDS - {'reset_session'}:
        raise ValueError('invalid_action')
    params=payload.get('params',{})
    if not isinstance(params,dict):
        raise ValueError('invalid_params')
    allowed={'start':{'track_id'},'next':{'track_id'},'set_style':{'style_id'},
             'trigger_effect':{'effect_id'},'gesture':{'gesture_id'}}.get(action,set())
    if set(params)-allowed:
        raise ValueError('unknown_parameter')
    for name,value in params.items():
        if not isinstance(value,str) or not 1<=len(value)<=128:
            raise ValueError('invalid_'+name)
    required={'set_style':'style_id','trigger_effect':'effect_id','gesture':'gesture_id'}.get(action)
    if required and required not in params:
        raise ValueError('missing_'+required)
    key=json.dumps([payload[k] for k in ('source','device_id','boot_id','event_id')],separators=(',',':'))
    return dict(cmd=action,request_id='device-'+sha256(key.encode()).hexdigest(),**params)


def route(method,path,payload,backend):
    if method=='GET' and path=='/v1/capabilities':
        current=backend({'cmd':'get_state'}) or {}
        tempo=current.get('mode')=='live_dual_deck_vocal_v4_tempo'
        return 200, dict(ok=True,schema_version=API_VERSION,styles=['EDM'],
            commands=sorted(COMMANDS),gesture_mapping=GESTURES,
            playback_mode=current.get('mode','live_dual_deck_original_speed'),tempo_stretch=tempo,
            tempo_processing='prepared_ffmpeg_atempo' if tempo else 'none',
            restore_mode='v4_head_then_original_tail' if tempo else 'none',
            smooth_16_bar_restore=False,
            resource_scope='frozen_edm_8',physical_input_implemented_here=False,
            gesture_test_window_seconds=10,transport_scope='rk_loopback_only')
    if method=='GET' and path=='/v1/state':
        return 200,backend({'cmd':'get_state'})
    if method=='POST' and path=='/v1/device-events':
        cmd=translate_event(payload)
    elif method=='POST' and path=='/v1/commands':
        if not isinstance(payload,dict) or payload.get('cmd') not in COMMANDS:
            raise ValueError('unknown_command')
        rid=payload.get('request_id')
        if not isinstance(rid,str) or not 1<=len(rid)<=128:
            raise ValueError('request_id_required')
        params={k:v for k,v in payload.items() if k not in ('cmd','request_id')}
        if payload['cmd']=='reset_session':
            if params:
                raise ValueError('unknown_parameter')
        else:
            translate_event(dict(schema_version=API_VERSION,source='test_client',
                device_id='diagnostic',boot_id='diagnostic',event_id=rid,
                action=payload['cmd'],params=params))
        cmd=payload
    else:
        return 404,dict(ok=False,error='not_found')
    start=time.monotonic()
    result=backend(cmd)
    return 200,dict(result,request_id=cmd['request_id'],schema_version=API_VERSION,
                    command_round_trip_ms=round((time.monotonic()-start)*1000,3))


class Handler(BaseHTTPRequestHandler):
    def respond(self,code,data):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Connection','close')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):
            pass  # Retrying the same ID returns the original result.

    def handle_request(self):
        self.connection.settimeout(5)
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('chunked_body_not_supported')
            size=int(self.headers.get('Content-Length','0'))
            if not 0<=size<=65536:
                return self.respond(413,dict(ok=False,error='body_too_large'))
            raw=self.rfile.read(size) if self.command=='POST' else b''
            if self.command=='POST' and len(raw)!=size:
                raise ValueError('truncated_body')
            payload=json.loads(raw) if raw else {}
            code,result=route(self.command,self.path,payload,lambda p:rpc(p,path=CONTROL))
            self.respond(code,result)
        except (ValueError,KeyError,TypeError) as exc:
            error=str(exc)
            conflict=any(w in error for w in ('busy','paused','not_ready','exhausted','not_started','scheduled','conflict','no_future','playing'))
            self.respond(409 if conflict else 400,dict(ok=False,error=error,schema_version=API_VERSION))
        except (OSError,ConnectionError,TimeoutError) as exc:
            self.respond(503,dict(ok=False,error='engine_unavailable',detail=str(exc),retry_same_request_id=True))

    do_GET=handle_request
    do_POST=handle_request


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=9130)
    args=parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
