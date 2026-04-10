from __future__ import annotations
import json, os, subprocess, webbrowser
from pathlib import Path
from threading import Timer
from uuid import uuid4
import librosa, numpy as np, soundfile as sf
from flask import Flask, jsonify, render_template, request, send_from_directory
from analyzer.extractor import TrackAnalyzer
from analyzer.storage import MetadataStorage
from core.enums import PhraseType
from logic.brain import TransitionPlanner
from logic.playlist import PlaylistPlanner

B=Path(__file__).resolve().parent; S=B.parent/'SongFormer'; SP=S/'.venv'/'Scripts'/'python.exe'; SI=S/'infer_single.py'; SR=S/'src'/'SongFormer'/'test_results'; F=B/'fixtures'
U=B/'temp_uploads'; R=B/'temp_songformer_results'; M=B/'temp_metadata'; O=B/'temp_outputs'
for d in [U,R,M,O]: d.mkdir(exist_ok=True)
app=Flask(__name__,template_folder=str(B/'web'/'templates'),static_folder=str(B/'web'/'static'))
planner=TransitionPlanner(); playlist_planner=PlaylistPlanner(planner); analyzer=TrackAnalyzer(); LIB={}

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
    md=analyzer.analyze(path); res=run_sf(path)
    segs=[{'label':str(s.get('label','unknown')).lower(),'start':f(s.get('start')),'end':f(s.get('end')),'confidence':1.0} for s in res.get('segments',[])]
    return track_payload(md,'uploaded_audio_songformer',segs,{'songformer':{'device':res.get('device'),'task':res.get('task'),'segments':segs}})

def la(path,sr=44100):
    a,src=sf.read(resolve_audio(path),always_2d=True,dtype='float32')
    if src!=sr: a=np.stack([librosa.resample(a[:,i],orig_sr=src,target_sr=sr) for i in range(a.shape[1])],axis=1)
    if a.shape[1]==1: a=np.repeat(a,2,axis=1)
    return a.astype(np.float32,copy=False)

def b2s(beats,bpm): return max(beats,1)*60.0/max(bpm,1.0)
def fades(n):
    p=np.linspace(0.0,1.0,max(n,2),dtype=np.float32); return np.cos(p*np.pi*.5),np.sin(p*np.pi*.5)
def echo(a,sr):
    o=a.copy(); d=int(sr*.25)
    for m,g in [(1,.32),(2,.2),(3,.11)]:
        st=d*m
        if st<len(o): o[st:]+=a[:-st]*g
    return np.clip(o,-1,1)

def apply_transition(audio_a,a_md,a_title,plan,audio_b,b_md,b_title):
    sr=44100; ov=min(int(b2s(plan.overlap_duration_beats,plan.target_bpm)*sr),len(audio_a),len(audio_b))
    ex=min(max(int(plan.mix_start_time*sr),0),max(len(audio_a)-ov,0)); head=audio_a[:ex]; ta=audio_a[ex:ex+ov].copy(); hb=audio_b[:ov].copy(); rb=audio_b[ov:]
    fo,fi=fades(ov)
    if plan.strategy.value=='cut_swap':
        c=max(ov//4,1); fo=np.concatenate([np.ones(c,np.float32),np.zeros(ov-c,np.float32)]); fi=np.concatenate([np.zeros(c,np.float32),np.ones(ov-c,np.float32)])
    elif plan.strategy.value=='echo_out': ta=echo(ta,sr)
    elif plan.strategy.value=='melodic_reset':
        h=ov//2; fo=np.linspace(1,0,ov,dtype=np.float32); fi=np.concatenate([np.linspace(0,.2,h,dtype=np.float32),np.linspace(.2,1,ov-h,dtype=np.float32)])
    mixed=np.vstack([head,(ta*fo[:,None])+(hb*fi[:,None]),rb]).astype(np.float32,copy=False)
    return mixed,{'track_a':a_title,'track_b':b_title,'strategy':plan.strategy.value,'track_a_exit_bar':plan.track_a_exit_bar,'track_b_entry_bar':plan.track_b_entry_bar,'track_a_exit_phrase':a_md.phrase_at_bar(plan.track_a_exit_bar).phrase_type.value if a_md.phrase_at_bar(plan.track_a_exit_bar) else 'unknown','track_b_entry_phrase':b_md.phrase_at_bar(plan.track_b_entry_bar).phrase_type.value if b_md.phrase_at_bar(plan.track_b_entry_bar) else 'unknown','overlap_beats':plan.overlap_duration_beats,'target_bpm':plan.target_bpm,'score':plan.score_breakdown.total_score,'notes':plan.score_breakdown.notes}

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
    current=la(ordered_md[0].path,44100); transitions=[]
    for index,transition in enumerate(playlist_plan.transitions,1):
        current,result=apply_transition(current,ordered_md[index-1],ordered_items[index-1]['title'],transition.plan,la(ordered_md[index].path,44100),ordered_md[index],ordered_items[index]['title'])
        transitions.append(result)
    out=O/f'medley_{uuid4().hex[:8]}.wav'; sf.write(out,np.clip(current,-1,1),44100)
    return {'audio_url':f'/outputs/{out.name}','filename':out.name,'duration_seconds':len(current)/44100,'track_count':len(ordered_items),'ordered_track_ids':playlist_plan.ordered_track_ids,'ordered_titles':playlist_plan.ordered_titles,'average_score':playlist_plan.average_score,'playlist_notes':playlist_plan.notes,'transitions':transitions}

def mix_two(a_item,b_item): return mix_playlist([a_item['track_id'],b_item['track_id']])

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
    return jsonify({'track_a':a.title,'track_b':b.title,'plan':plan.model_dump(mode='json')})

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

def open_browser(): webbrowser.open('http://127.0.0.1:5055')
if __name__=='__main__': Timer(1.2,open_browser).start(); app.run(host='127.0.0.1',port=5055,debug=False,use_reloader=False)
