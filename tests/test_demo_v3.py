import copy
import json
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
try:
    from analysis_platform import demo_v3
except ImportError:
    demo_v3 = None

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'mixing/vendor/colleague_demo_v1'

def documents(tmp_path):
    # Synthetic identities let CI check the frozen decisions without private songs.
    peer=json.loads((SOURCE/'mix_plan.json').read_text()); sources=[]
    for i,row in enumerate(peer['tracks']):
        path=tmp_path/f'identity-{i}.bin';path.write_bytes(f'synthetic-{i}'.encode())
        digest=demo_v3.sha256(path);row['track_id']='track-'+digest[:20]
        sources.append({'title':row['title'],'path':str(path),'audio_sha256':digest})
    return peer,sources

def test_original_functions_loaded_and_tamper_rejected(tmp_path):
    assert demo_v3 is not None, "V3 reproduction module is missing"
    api=demo_v3.load_renderer(SOURCE/'algorithm_demo_transition_logic_1_0.py')
    assert api['RENDER_GAIN']==.76
    assert api['FINAL_FADE_SECONDS']==7
    assert api['_atempo_chain'](.9683673469387756)=='atempo=0.968367'
    bad=tmp_path/'changed.py';bad.write_text((SOURCE/'algorithm_demo_transition_logic_1_0.py').read_text()+'\n# changed\n')
    with pytest.raises(ValueError,match='checksum'):demo_v3.load_renderer(bad)

def test_frozen_plan_keeps_peer_decisions_and_full_precision(tmp_path):
    assert demo_v3 is not None, "V3 reproduction module is missing"
    peer,sources=documents(tmp_path);p=demo_v3.compile_plan(peer,sources)
    assert [t['title'] for t in p['tracks']]==[t['title'] for t in peer['tracks']]
    for i,t in enumerate(p['tracks']):
        assert t['render']['entry_ms']==peer['tracks'][i]['render_entry_ms']
        assert t['render']['exit_ms']==peer['tracks'][i]['render_exit_ms']
        assert t['render']['incoming_rate']==peer['tracks'][i]['incoming_rate']
        assert t['render']['final_track']==(i==5)
    assert p['tracks'][1]['render']['incoming_rate'] != peer['transitions'][0]['entry_rate']
    assert p['transitions'][0]['overlap_seconds']==pytest.approx(14.768/(94.9/98))
    assert p['tracks'][1]['render']['restore_half_bar_seconds']==pytest.approx(120/94.9)
    assert p['ranking_recomputed'] is False

def test_missing_or_mismatched_source_never_substituted(tmp_path):
    assert demo_v3 is not None, "V3 reproduction module is missing"
    peer,sources=documents(tmp_path)
    with pytest.raises(ValueError,match='source'):demo_v3.compile_plan(peer,sources[:-1])
    sources=copy.deepcopy(sources);sources[0]['audio_sha256']='0'*64
    with pytest.raises(ValueError,match='identity'):demo_v3.compile_plan(peer,sources)

def test_real_renderer_preserves_original_body_gain_and_tempo(tmp_path):
    assert demo_v3 is not None, "V3 reproduction module is missing"
    api=demo_v3.load_renderer(SOURCE/'algorithm_demo_transition_logic_1_0.py')
    sr=44100;t=np.arange(sr*8)/sr
    x=(.1*np.sin(2*np.pi*997*t)).astype('float32');source=tmp_path/'source.wav'
    sf.write(source,np.column_stack([x,x]),sr,subtype='FLOAT')
    output=tmp_path/'out.wav'
    api['render_segment'](ffmpeg='ffmpeg',source_path=source,output_path=output,entry_ms=0,exit_ms=8000,incoming_source_overlap_ms=2000,incoming_rate=.8,outgoing_overlap_seconds=0,mid_duck=False,restore_half_bar_seconds=.5,final_track=False)
    y,ysr=sf.read(output);assert ysr==sr
    assert abs(len(y)/sr-8.5)<.05
    body=y[int(sr*4):int(sr*5),0]
    assert np.sqrt(np.mean(body**2))==pytest.approx(.1*.76/np.sqrt(2),abs=.0001)
    freq=np.fft.rfftfreq(len(body),1/sr)[np.argmax(abs(np.fft.rfft(body)))]
    assert freq==pytest.approx(997,abs=1)
