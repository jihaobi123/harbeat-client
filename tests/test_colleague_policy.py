from types import SimpleNamespace as NS
import pytest
try:
    from analysis_platform.colleague_policy import load_policy
except ImportError:
    load_policy=None

def make_bundle(name,bpm,intro_end,chorus_end):
    return NS(track=NS(id=name,title=name,bpm=bpm,key='5A',duration_seconds=120,
        drum_profile=NS(sound_tags=frozenset(),all_hits=()),sections=[
            NS(name='intro',start_time_seconds=0,end_time_seconds=intro_end),
            NS(name='verse',start_time_seconds=intro_end,end_time_seconds=40),
            NS(name='chorus',start_time_seconds=40,end_time_seconds=chorus_end)]))

def test_original_transition_rules_and_vocal_window_presence():
    assert load_policy is not None,'colleague policy adapter missing'
    api=load_policy({'a':[x*2.4 for x in range(51)],'b':[x*2.4 for x in range(51)]})
    a=make_bundle('a',100,9.6,79.2);b=make_bundle('b',100,9.6,79.2)
    # Separate vocal occurrences still trigger the ORIGINAL both-window policy.
    t=api['transition_for_pair'](1,a,b,{'a':[(71000,72000)],'b':[(8000,9000)]})
    assert t.both_vocal
    assert t.case=='case_2_a_chorus_longer_than_b_intro'
    assert t.entry_rate==1
    assert t.overlap_seconds==9.6
    assert t.restore_half_bar_seconds==1.2

def test_long_intro_case_keeps_original_tail_selection():
    assert load_policy is not None,'colleague policy adapter missing'
    api=load_policy({'a':[x*2.4 for x in range(51)],'b':[x*2.4 for x in range(51)]})
    a=make_bundle('a',100,9.6,48);b=make_bundle('b',100,24,79.2)
    t=api['transition_for_pair'](1,a,b,{'a':[],'b':[]})
    assert t.case=='case_3_a_chorus_shorter_than_b_intro'
    assert t.b_entry_ms>0
    assert t.a_chorus_bars< t.b_intro_bars

def test_grid_adapter_never_invents_missing_bar_positions():
    assert load_policy is not None,'colleague policy adapter missing'
    api=load_policy({'a':[1.,3.4,5.8]})
    a=make_bundle('a',100,9.6,79.2)
    assert api['snap_to_bar'](a.track,2.1)==1.
    assert api['snap_to_bar'](a.track,2.1,mode='ceil')==3.4
    with pytest.raises(ValueError):api['snap_to_bar'](a.track,0,mode='floor')

def test_original_v3_mid_duck_is_applied_and_body_restored(tmp_path):
    import numpy as np
    import soundfile as sf
    from analysis_platform.demo_v3 import load_renderer
    from analysis_platform.colleague_policy import SOURCE
    api=load_renderer(SOURCE);sr=44100;t=np.arange(5*sr)/sr
    x=.1*np.sin(2*np.pi*1200*t);source=tmp_path/'source.wav';sf.write(source,np.column_stack([x,x]),sr,subtype='FLOAT')
    ys=[]
    for duck in [False,True]:
        output=tmp_path/(str(duck)+'.wav')
        api['render_segment'](ffmpeg='ffmpeg',source_path=source,output_path=output,entry_ms=0,exit_ms=5000,incoming_source_overlap_ms=2000,incoming_rate=1,outgoing_overlap_seconds=0,mid_duck=duck,restore_half_bar_seconds=.5,final_track=False)
        ys.append(sf.read(output)[0])
    early=[np.sqrt(np.mean(y[int(.3*sr):sr]**2)) for y in ys]
    assert early[1]/early[0]==pytest.approx(10**(-5/20),abs=.002)
    assert np.array_equal(ys[0][3*sr:4*sr],ys[1][3*sr:4*sr])
