from __future__ import annotations
import json, os, subprocess, webbrowser
from pathlib import Path
from threading import Timer
from uuid import uuid4
import librosa, numpy as np, soundfile as sf
from flask import Flask, jsonify, render_template, request, send_from_directory
from audio.artifacts import export_playlist_artifact, export_candidate_search_report, export_transition_artifact
from audio.offline_renderer import OfflineDualDeckRenderer
from analyzer.extractor import TrackAnalyzer
from analyzer.storage import MetadataStorage
from core.datatypes import TrackMetadata, TransitionPlan
from core.enums import PhraseType, TransitionType
from engine.online_controller import OnlineDJController
from logic.brain import TransitionPlanner
from logic.playlist import PlaylistPlanner
from logic.strategies import STRATEGY_REGISTRY

B=Path(__file__).resolve().parent; S=B.parent/'SongFormer'; SP=S/'.venv'/'Scripts'/'python.exe'; SI=S/'infer_single.py'; SR=S/'src'/'SongFormer'/'test_results'; F=B/'fixtures'
U=B/'temp_uploads'; R=B/'temp_songformer_results'; M=B/'temp_metadata'; O=B/'temp_outputs'; A=B/'temp_artifacts'
MUSIC_DIR=B/'music'
for d in [U,R,M,O,A, MUSIC_DIR]: d.mkdir(exist_ok=True)
app=Flask(__name__,template_folder=str(B/'web'/'templates'),static_folder=str(B/'web'/'static'))
planner=TransitionPlanner(); playlist_planner=PlaylistPlanner(planner); analyzer=TrackAnalyzer(); renderer=OfflineDualDeckRenderer(); LIB={}
online_ctrl: OnlineDJController | None = None  # online playback controller singleton


def f(x,d=0.0):
    try:return float(x)
    except:return d

def resolve_audio(raw:str)->Path:
    p=Path(raw)
    return p if p.is_absolute() else (B/p).resolve()

def renderable(raw:str)->bool: return resolve_audio(raw).exists()

def curve(segs):
    mp={'intro':.38,'verse':.56,'bridge':.5,'build':.76,'chorus':.88,'drop':.96,'outro':.28,'inst':.64,'unknown':.5}
    return [{'index':i,'label':str(s.get('label','unknown')).lower(),'start':f(s.get('start')),'end':f(s.get('end')),'energy':mp.get(str(s.get('label','unknown')).lower(),.5)} for i,s in enumerate(segs,1)]

def label_at(segs,t):
    for s in segs:
        if f(s.get('start'))<=t<f(s.get('end')): return str(s.get('label',PhraseType.UNKNOWN.value)).lower()
    return str(segs[-1].get('label',PhraseType.UNKNOWN.value)).lower() if segs else PhraseType.UNKNOWN.value

def reg(p): LIB[p['track_id']]=p; return p

def sf_payload(data,source,artist):
    title=Path(data['audio_file']).stem; segs=data.get('segments',[])
    return {'source':source,'track_id':f"songformer-{title.lower().replace(' ','-')}",'title':title,'artist':artist,'audio_path':data['audio_file'],'duration_seconds':max((f(s.get('end')) for s in segs),default=0.0),'bpm':None,'camelot':None,'phrase_segments':segs,'bar_structure':[],'energy_curve':curve(segs),'metadata_path':None,'renderable':renderable(data['audio_file']),'api_payload':{'track_id':f"songformer-{title.lower().replace(' ','-')}",'title':title,'structure_segments':segs,'energy_curve':curve(segs),'storage_status':'ready_for_database_api'}}

def load_sf(name): return sf_payload(json.loads((SR/name).read_text(encoding='utf-8')),'songformer','SongFormer test audio')

def track_payload(md,source,segs,extra=None):
    saved=str(MetadataStorage.save(md,M/f'{md.track_id}.groove.json'))
    p={'source':source,'track_id':md.track_id,'title':md.title,'artist':md.artist,'audio_path':md.path,'duration_seconds':md.duration_seconds,'bpm':md.beatgrid.bpm,'camelot':md.key.camelot,'phrase_segments':segs,'bar_structure':[{'bar':e.bar,'start':e.start_time,'end':e.end_time,'energy':e.combined,'label':label_at(segs,e.start_time),'rms':e.rms,'spectral_flux':e.spectral_flux} for e in md.energy_bars],'energy_curve':[{'bar':e.bar,'energy':e.combined} for e in md.energy_bars],'metadata_path':saved,'renderable':renderable(md.path),'api_payload':{**md.model_dump(mode='json'),**(extra or {})}}
    return reg(p)

def fixture(name):
    md=MetadataStorage.load(F/name)
    segs=[{'label':p.phrase_type.value,'start':p.start_time,'end':p.end_time,'start_bar':p.start_bar,'end_bar':p.end_bar,'confidence':p.confidence} for p in md.phrases]
    return track_payload(md,'groove_fixture',segs)

def run_sf(audio):
    if not SP.exists() or not SI.exists(): raise FileNotFoundError('SongFormer runtime not found')
    out=R/f'{audio.stem}_{uuid4().hex[:8]}.json'
    c=subprocess.run([str(SP),str(SI),str(audio),str(out)],cwd=str(S),env=os.environ.copy(),capture_output=True,text=True,timeout=1800)
    if c.returncode!=0: raise RuntimeError(f'SongFormer inference failed.\nstdout:\n{c.stdout}\n\nstderr:\n{c.stderr}')
    return json.loads(out.read_text(encoding='utf-8'))

def analyze_upload(path):
    try:
        md=analyzer.analyze(path)
    except Exception as exc:
        raise RuntimeError(f'音频解码/分析失败：{exc}') from exc
    try:
        res=run_sf(path)
    except FileNotFoundError as exc:
        raise RuntimeError('模型未启动或 SongFormer 运行环境不存在。') from exc
    except RuntimeError as exc:
        raise RuntimeError(f'结构推断失败：{exc}') from exc
    except Exception as exc:
        raise RuntimeError(f'模型推断异常：{exc}') from exc
    segs=[{'label':str(s.get('label','unknown')).lower(),'start':f(s.get('start')),'end':f(s.get('end')),'confidence':1.0} for s in res.get('segments',[])]
    return track_payload(md,'uploaded_audio_songformer',segs,{'songformer':{'device':res.get('device'),'task':res.get('task'),'segments':segs}})

def la(path,sr=44100):
    a,src=sf.read(resolve_audio(path),always_2d=True,dtype='float32')
    if src!=sr: a=np.stack([librosa.resample(a[:,i],orig_sr=src,target_sr=sr) for i in range(a.shape[1])],axis=1)
    if a.shape[1]==1: a=np.repeat(a,2,axis=1)
    return a.astype(np.float32,copy=False)

def ordered_renderables(track_ids):
    items=[]
    for track_id in track_ids:
        if track_id not in LIB: raise KeyError(track_id)
        item=LIB[track_id]
        if not item.get('renderable'): raise ValueError('One or more selected tracks have no real local audio file. Fixtures are analysis-only; upload real songs for output.')
        if not item.get('metadata_path'): raise ValueError('One or more selected tracks are missing saved metadata and cannot be rendered yet.')
        items.append(item)
    return items

def mix_playlist(track_ids):
    items=ordered_renderables(track_ids)
    metadata=[MetadataStorage.load(item['metadata_path']) for item in items]
    playlist_plan=playlist_planner.plan(metadata)
    ordered_items=[LIB[track_id] for track_id in playlist_plan.ordered_track_ids]
    ordered_md=[MetadataStorage.load(item['metadata_path']) for item in ordered_items]
    current=la(ordered_md[0].path,44100); transitions=[]; transition_artifacts=[]; run_id=uuid4().hex[:8]
    for index,transition in enumerate(playlist_plan.transitions,1):
        result=renderer.render_transition(current,ordered_md[index-1],ordered_items[index-1]['title'],transition.plan,la(ordered_md[index].path,44100),ordered_md[index],ordered_items[index]['title'])
        current=result.audio; transitions.append(result.transition_summary)
        artifact_path=A/f'transition_{index}_{run_id}.json'
        export_transition_artifact(artifact_path,track_a_title=ordered_items[index-1]['title'],track_b_title=ordered_items[index]['title'],plan=transition.plan,transition_summary=result.transition_summary,render_trace=result.render_trace)
        transition_artifacts.append({'path':str(artifact_path),'summary':result.transition_summary})
    out=O/f'medley_{run_id}.wav'; sf.write(out,np.clip(current,-1,1),44100)
    mix_result={'audio_url':f'/outputs/{out.name}','filename':out.name,'duration_seconds':len(current)/44100,'track_count':len(ordered_items),'ordered_track_ids':playlist_plan.ordered_track_ids,'ordered_titles':playlist_plan.ordered_titles,'average_score':playlist_plan.average_score,'playlist_notes':playlist_plan.notes,'transitions':transitions}
    playlist_artifact=A/f'playlist_{run_id}.json'; export_playlist_artifact(playlist_artifact,playlist_plan=playlist_plan,mix_result=mix_result,transition_artifacts=transition_artifacts)
    return {**mix_result,'artifact_path':str(playlist_artifact),'transition_artifacts':transition_artifacts}


def _transition_plan_from_row(a_md,b_md,row):
    candidates = planner.top_candidates(a_md,b_md,limit=max(int(row.get("candidate_rank", 1)), 1))
    target = next((item for item in candidates if item.search_rank == int(row.get("candidate_rank", 1)) and item.track_a_exit_bar == int(row.get("candidate_exit_bar", row.get("candidate_window", "0->0").split("->")[0])) and item.track_b_entry_bar == int(row.get("candidate_entry_bar", row.get("candidate_window", "0->0").split("->")[-1])) and item.strategy.value == str(row.get("strategy", row.get("candidate_strategy", "")))), None)
    if target is None:
        raise ValueError("Requested candidate could not be reconstructed.")
    plan = TransitionPlan(mix_start_time=planner._bar_start_time(a_md, target.track_a_exit_bar), overlap_duration_beats=target.overlap_beats, target_bpm=target.target_bpm, phase_offset_beats=target.phase_offset_beats, alignment_confidence=target.alignment_confidence, handoff_profile=target.handoff_profile, strategy=target.strategy, track_a_exit_bar=target.track_a_exit_bar, track_b_entry_bar=target.track_b_entry_bar, automation=[], score_breakdown=target)
    plan.automation = STRATEGY_REGISTRY[target.strategy].build_automation(plan)
    return plan


def render_transition_candidate_payload(track_a_id:str,track_b_id:str,row:dict):
    if track_a_id not in LIB or track_b_id not in LIB: raise KeyError('track not found')
    a_item=LIB[track_a_id]; b_item=LIB[track_b_id]
    if not a_item.get('metadata_path') or not b_item.get('metadata_path'): raise ValueError('Selected tracks are missing saved metadata.')
    a_md=MetadataStorage.load(a_item['metadata_path']); b_md=MetadataStorage.load(b_item['metadata_path'])
    plan=_transition_plan_from_row(a_md,b_md,row)
    result=renderer.render_transition(la(a_item['audio_path'],44100),a_md,a_item['title'],plan,la(b_item['audio_path'],44100),b_md,b_item['title'])
    run_id=uuid4().hex[:8]
    wav_path=O/f'transition_preview_{run_id}.wav'; sf.write(wav_path,np.clip(result.audio,-1,1),44100)
    artifact_path=A/f'transition_preview_{run_id}.json'
    export_transition_artifact(artifact_path,track_a_title=a_item['title'],track_b_title=b_item['title'],plan=plan,transition_summary=result.transition_summary,render_trace=result.render_trace)
    return {'audio_url':f'/outputs/{wav_path.name}','filename':wav_path.name,'artifact_path':str(artifact_path),'summary':result.transition_summary,'plan':plan.model_dump(mode='json')}


def candidate_report_payload(track_a_id:str,track_b_id:str,limit:int=5,render_shortlist_limit:int|None=None):
    if track_a_id not in LIB or track_b_id not in LIB: raise KeyError('track not found')
    a_item=LIB[track_a_id]; b_item=LIB[track_b_id]
    if not a_item.get('metadata_path') or not b_item.get('metadata_path'): raise ValueError('Selected tracks are missing saved metadata.')
    a_md=MetadataStorage.load(a_item['metadata_path']); b_md=MetadataStorage.load(b_item['metadata_path'])
    report=planner.candidate_report(a_md,b_md,limit=limit,render_shortlist_limit=render_shortlist_limit)
    report["track_sync"]={"track_a": planner._track_sync_summary(a_md), "track_b": planner._track_sync_summary(b_md)}
    run_id=uuid4().hex[:8]
    json_path=A/f'candidate_report_{run_id}.json'; csv_path=A/f'candidate_report_{run_id}.csv'
    export_candidate_search_report(json_path,csv_path,title=report['overview_section']['title'],rows=report['rows'],metadata=report['overview_section'],pruning_rules=report['pruning_section']['rules'])
    return {**report,'json_report_path':str(json_path),'csv_report_path':str(csv_path)}


@app.route('/')
def index():
    return render_template('index.html',test_tracks=[{'id':'songformer:notshy','label':'SongFormer · NOT SHY','file':'NotShy-ITZY있지-K12PBWZV.json'},{'id':'songformer:gold','label':'SongFormer · GOLD','file':'tMUmAV-GOLD-ITZY_(있지).json'},{'id':'fixture:a','label':'Fixture · Battle Seed A','file':'track_a.groove.json'},{'id':'fixture:b','label':'Fixture · Battle Seed B','file':'track_b.groove.json'},{'id':'fixture:c','label':'Fixture · Low Energy Mismatch','file':'track_c_low_energy.json'},{'id':'fixture:d','label':'Fixture · Build Up Launcher','file':'track_d_build_up.json'},{'id':'fixture:e','label':'Fixture · High Energy Drop','file':'track_e_high_energy_drop.json'}])

@app.get('/api/dj-strategy')
def dj_strategy():
    return jsonify({'article_takeaways':['Use 4/4 bar counting and phrase boundaries as the main transition timing reference.','Beatmatch first, then align phrase starts; matching BPM alone is not enough.','Prefer low-EQ swaps when two full-range tracks overlap.','Use 8, 16, or 32 bar loops to extend usable transition windows.','Apply FX sparingly: echo, delay, reverb, and risers should support the handoff, not hide weak timing.','Read crowd energy and choose continuity, reset, or impact transitions.','Final render should now support ordered multi-song medleys, not only a single two-song handoff.']})

@app.get('/api/library')
def library(): return jsonify({'tracks':list(LIB.values())})

@app.get('/api/demo-library')
def demo_library(): return jsonify({'songformer':[load_sf('NotShy-ITZY있지-K12PBWZV.json'),load_sf('tMUmAV-GOLD-ITZY_(있지).json')],'groove_fixtures':[fixture('track_a.groove.json'),fixture('track_b.groove.json'),fixture('track_c_low_energy.json'),fixture('track_d_build_up.json'),fixture('track_e_high_energy_drop.json')]})

@app.post('/api/analyze')
def analyze_track():
    source=request.form.get('source','upload')
    if source=='songformer': return jsonify(load_sf(request.form['filename']))
    if source=='fixture': return jsonify(fixture(request.form['filename']))
    audio=request.files.get('audio')
    if audio is None or not audio.filename: return jsonify({'error':'No audio file uploaded.'}),400
    path=U/f"{Path(audio.filename).stem}_{uuid4().hex[:8]}{Path(audio.filename).suffix or '.wav'}"; audio.save(path)
    try: return jsonify(analyze_upload(path))
    except Exception as exc: return jsonify({'error':str(exc)}),500

@app.post('/api/transition')
def transition_preview():
    p=request.get_json(force=True)
    if not p.get('track_a') or not p.get('track_b'): return jsonify({'error':'track_a and track_b are required.'}),400
    a=MetadataStorage.load(F/p['track_a']); b=MetadataStorage.load(F/p['track_b']); plan=planner.plan(a,b)
    return jsonify({'track_a':a.title,'track_b':b.title,'plan':plan.model_dump(mode='json'),'track_sync':{'track_a':planner._track_sync_summary(a),'track_b':planner._track_sync_summary(b)}})

@app.post('/api/transition-report')
def transition_report_api():
    p=request.get_json(force=True); track_a_id=p.get('track_a_id'); track_b_id=p.get('track_b_id'); limit=int(p.get('limit',5) or 5); render_shortlist_limit=int(p.get('render_shortlist_limit',3) or 3)
    if not track_a_id or not track_b_id: return jsonify({'error':'track_a_id and track_b_id are required.'}),400
    try: return jsonify(candidate_report_payload(track_a_id,track_b_id,limit=limit,render_shortlist_limit=render_shortlist_limit))
    except KeyError: return jsonify({'error':'Selected track not found in current library.'}),400
    except Exception as exc: return jsonify({'error':str(exc)}),400

@app.post('/api/render-transition-candidate')
def render_transition_candidate_api():
    p=request.get_json(force=True); track_a_id=p.get('track_a_id'); track_b_id=p.get('track_b_id'); row=p.get('row') or {}
    if not track_a_id or not track_b_id: return jsonify({'error':'track_a_id and track_b_id are required.'}),400
    if not isinstance(row, dict) or not row: return jsonify({'error':'row is required.'}),400
    try: return jsonify(render_transition_candidate_payload(track_a_id,track_b_id,row))
    except KeyError: return jsonify({'error':'Selected track not found in current library.'}),400
    except Exception as exc: return jsonify({'error':str(exc)}),400

@app.post('/api/playlist-plan')
def playlist_plan_api():
    p=request.get_json(force=True); ids=p.get('track_ids',[])
    if len(ids)<2: return jsonify({'error':'Select at least two tracks for playlist planning.'}),400
    try:
        items=ordered_renderables(ids); metadata=[MetadataStorage.load(item['metadata_path']) for item in items]
        return jsonify(playlist_planner.plan(metadata).model_dump(mode='json'))
    except KeyError: return jsonify({'error':'Selected track not found in current library.'}),400
    except Exception as exc: return jsonify({'error':str(exc)}),400

@app.post('/api/mix')
def mix_api():
    p=request.get_json(force=True); ids=p.get('track_ids',[])
    if len(ids)<2: return jsonify({'error':'Select at least two tracks for the final mix.'}),400
    try: return jsonify(mix_playlist(ids))
    except KeyError: return jsonify({'error':'Selected track not found in current library.'}),400
    except Exception as exc: return jsonify({'error':str(exc)}),400

@app.get('/outputs/<path:name>')
def outputs(name:str): return send_from_directory(O,name,as_attachment=False)

# ══════════════════════════════════════════════════════════════════════
# Online DJ player routes
# ══════════════════════════════════════════════════════════════════════

@app.route('/player')
def player_page():
    return render_template('player.html',
        strategies=[{'value': s.value, 'name': s.value.replace('_', ' ').title(), 'label': _strategy_label(s)} for s in TransitionType])

@app.post('/api/online/load')
def online_load():
    global online_ctrl
    p = request.get_json(force=True)
    ids = p.get('track_ids', [])
    if len(ids) < 1:
        return jsonify({'error': 'Need at least one track.'}), 400
    items = ordered_renderables(ids)
    metadata_list: list[TrackMetadata] = [
        MetadataStorage.load(item['metadata_path']) for item in items
    ]
    online_ctrl = OnlineDJController(sample_rate=44100, block_size=1024)
    online_ctrl.load_playlist(metadata_list)
    online_ctrl._scheduler.metadata_lookup = lambda tid: _lookup_metadata(tid)
    return jsonify({
        'status': 'loaded',
        'track_count': len(metadata_list),
        'titles': [md.title for md in metadata_list],
    })

@app.post('/api/online/start')
def online_start():
    global online_ctrl
    if online_ctrl is None:
        return jsonify({'error': 'No playlist loaded.'}), 400
    online_ctrl.start()
    return jsonify({'status': 'playing'})

@app.post('/api/online/stop')
def online_stop():
    global online_ctrl
    if online_ctrl is None:
        return jsonify({'error': 'Not running.'}), 400
    online_ctrl.stop()
    online_ctrl = None
    return jsonify({'status': 'stopped'})

@app.post('/api/online/pause')
def online_pause():
    if online_ctrl is None:
        return jsonify({'error': 'Not running.'}), 400
    online_ctrl.press_pause()
    return jsonify({'status': 'paused'})

@app.post('/api/online/resume')
def online_resume():
    if online_ctrl is None:
        return jsonify({'error': 'Not running.'}), 400
    online_ctrl.press_resume()
    return jsonify({'status': 'resumed'})

@app.post('/api/online/manual')
def online_manual():
    if online_ctrl is None:
        return jsonify({'error': 'Not running.'}), 400
    p = request.get_json(force=True)
    strategy_str = p.get('strategy')
    strategy = None
    if strategy_str:
        try:
            strategy = TransitionType(strategy_str)
        except ValueError:
            return jsonify({'error': f'Invalid strategy: {strategy_str}'}), 400
    online_ctrl.press_manual(strategy)
    return jsonify({
        'status': 'manual_queued',
        'override_strategy': strategy.value if strategy else 'auto',
    })

@app.get('/api/online/status')
def online_status():
    if online_ctrl is None:
        return jsonify({'running': False, 'mode': 'idle'})
    snapshot = online_ctrl.status_snapshot()
    snapshot['running'] = True
    return jsonify(snapshot)

@app.get('/api/online/strategies')
def online_strategies():
    return jsonify({
        'strategies': [
            {'value': s.value, 'label': _strategy_label(s)}
            for s in TransitionType
        ]
    })

# ── Music folder scan & batch analyze ──────────────────────────

@app.get('/api/music/scan')
def music_scan():
    """Scan the music/ folder for audio files and report which are already analyzed."""
    audio_exts = {'.wav', '.mp3', '.flac', '.ogg', '.aiff', '.aif', '.m4a'}
    files = []
    for fpath in sorted(MUSIC_DIR.iterdir()):
        if fpath.suffix.lower() in audio_exts:
            track_id = f"music-{fpath.stem.lower().replace(' ','-')}"
            already = any(t.get('track_id') == track_id for t in LIB.values())
            files.append({
                'name': fpath.name,
                'stem': fpath.stem,
                'path': str(fpath),
                'track_id': track_id,
                'analyzed': already,
            })
    return jsonify({'music_dir': str(MUSIC_DIR), 'files': files, 'total': len(files)})

@app.post('/api/music/analyze-all')
def music_analyze_all():
    """Analyze all un-analyzed audio files in music/ folder. Runs sequentially."""
    audio_exts = {'.wav', '.mp3', '.flac', '.ogg', '.aiff', '.aif', '.m4a'}
    to_analyze = []
    for fpath in sorted(MUSIC_DIR.iterdir()):
        if fpath.suffix.lower() in audio_exts:
            track_id = f"music-{fpath.stem.lower().replace(' ','-')}"
            if not any(t.get('track_id') == track_id for t in LIB.values()):
                to_analyze.append(fpath)

    if not to_analyze:
        return jsonify({'status': 'all_done', 'message': '所有歌曲已分析完毕', 'analyzed': 0})

    results = []
    errors = []
    for i, fpath in enumerate(to_analyze):
        try:
            payload = analyze_upload(fpath)
            results.append({'name': fpath.name, 'track_id': payload['track_id'], 'title': payload['title'], 'bpm': payload.get('bpm'), 'status': 'ok'})
        except Exception as exc:
            errors.append({'name': fpath.name, 'error': str(exc), 'status': 'failed'})

    return jsonify({
        'status': 'complete',
        'analyzed': len(results),
        'failed': len(errors),
        'results': results,
        'errors': errors,
        'library_count': len(LIB),
    })

# ── Online queue insert ─────────────────────────────────────────

@app.post('/api/online/insert')
def online_insert():
    """Insert a track into the online playlist at a given position (1-based, after current)."""
    global online_ctrl
    p = request.get_json(force=True)
    track_id = p.get('track_id')
    position = p.get('position')  # 1-based, None = append after current

    if not track_id:
        return jsonify({'error': 'track_id required'}), 400
    if track_id not in LIB:
        return jsonify({'error': f'Track not found: {track_id}'}), 400
    item = LIB[track_id]
    if not item.get('metadata_path'):
        return jsonify({'error': 'Track not analyzed yet'}), 400

    md = MetadataStorage.load(item['metadata_path'])

    if online_ctrl is None or not online_ctrl._running:
        return jsonify({'error': 'No active online session. Load a playlist first.'}), 400

    # Insert after current index
    insert_at = online_ctrl._current_index + 1
    if position is not None:
        insert_at = max(online_ctrl._current_index + 1, min(int(position), len(online_ctrl._playlist)))

    online_ctrl._playlist.insert(insert_at, md)
    if online_ctrl._next_index >= insert_at:
        online_ctrl._next_index += 1

    # Reload the inserted track onto idle deck if idle is free
    idle = online_ctrl._decks.idle_deck
    if not idle.loaded or idle.finished:
        online_ctrl._decks.load_idle(md)

    return jsonify({
        'status': 'inserted',
        'position': insert_at,
        'track_title': md.title,
        'playlist_length': len(online_ctrl._playlist),
        'titles': [t.title for t in online_ctrl._playlist],
    })

def _strategy_label(s: TransitionType) -> str:
    labels = {
        TransitionType.CLEAN_BLEND: 'Clean Blend (长混低频切换)',
        TransitionType.ECHO_OUT: 'Echo Out (回声尾音)',
        TransitionType.RISER: 'Riser (上升堆积)',
        TransitionType.CUT_SWAP: 'Cut Swap (快速切换/淡入淡出)',
        TransitionType.TRIPLET_SWAP: 'Triplet Swap (三步音量)',
        TransitionType.MELODIC_RESET: 'Melodic Reset (旋律重置)',
    }
    return labels.get(s, s.value)

def _lookup_metadata(track_id: str) -> TrackMetadata:
    item = LIB.get(track_id)
    if item and item.get('metadata_path'):
        return MetadataStorage.load(item['metadata_path'])
    raise KeyError(f'Track not found in library: {track_id}')

def open_browser(): webbrowser.open('http://127.0.0.1:5055')
if __name__=='__main__': Timer(1.2,open_browser).start(); app.run(host='127.0.0.1',port=5055,debug=False,use_reloader=False)
