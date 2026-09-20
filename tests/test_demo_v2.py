import numpy as np
import pytest
from analysis_platform import demo_render


def test_vocal_conflict_requires_intersection_and_unknown_is_not_silence():
    from analysis_platform.demo_v2 import vocal_decision
    with pytest.raises(ValueError,match='unknown'):vocal_decision(None,[],0,10)
    result=vocal_decision([{'start':1,'end':3}],[{'start':7,'end':9}],0,10)
    assert not result['triggered']
    result=vocal_decision([{'start':1,'end':4}],[{'start':3,'end':6}],0,10)
    assert result['triggered'] and result['simultaneous_sec']>=1


def test_degraded_drums_have_zero_routing_weight():
    from analysis_platform.demo_v2 import drum_similarity
    a={'kick':{'pattern_16':'K...K...K...K...','status':'degraded'}}
    assert drum_similarity(a,a)['weight']==0


def test_route_search_visits_every_track_and_skips_blocked_edges():
    from analysis_platform.demo_v2 import rank_routes
    pairs={(i,j):{'status':'needs_review','route_score':{'total':float(j==i+1)}} for i in range(3) for j in range(3) if i!=j}
    pairs[0,2]['status']='blocked'
    routes=rank_routes(3,pairs)
    assert routes[0]['order']==[0,1,2]
    assert all(sorted(r['order'])==[0,1,2] for r in routes)
    assert not any([0,2]==r['order'][k:k+2] for r in routes for k in range(2))


def test_low_eq_is_attenuation_only_and_restores_exactly():
    assert hasattr(demo_render,'low_eq'), 'low-band automation missing'
    sr=16000;t=np.arange(sr*2)/sr;cut=np.where(t<1,-7.,0.)
    for hz,expected in [(50,10**(-7/20)),(2000,1)]:
        x=np.sin(2*np.pi*hz*t)[:,None]*.1
        y=demo_render.low_eq(x,sr,cut,140)
        assert np.linalg.norm(y[4000:12000])/np.linalg.norm(x[4000:12000])==pytest.approx(expected,abs=.06)
        assert np.max(abs(y[sr:]-x[sr:]))<1e-7
    with pytest.raises(ValueError):demo_render.low_eq(x,sr,np.ones(len(x)),140)


def test_calibration_tie_never_claims_semantic_accuracy():
    from analysis_platform.demo_calibration import compare_grids
    ticks=np.arange(0,20,.5);onsets=ticks+.01
    result=compare_grids(ticks,ticks+.002,onsets,20)
    assert result['winner']=='inconclusive'
    assert result['human_confirmed'] is False
    assert result['semantic_section_verified'] is False


def test_acoustic_grid_comparison_can_detect_large_timing_offset():
    from analysis_platform.demo_calibration import compare_grids
    ticks=np.arange(0,20,.5);result=compare_grids(ticks,ticks+.15,ticks+.01,20)
    assert result['winner']=='platform'


def test_rendered_low_automation_events_follow_sample_clock(tmp_path):
    import hashlib,shutil
    import soundfile as sf
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg unavailable')
    sr=44100;t=np.arange(sr*6)/sr;source=tmp_path/'source.wav';sf.write(source,np.column_stack([.03*np.sin(2*np.pi*80*t),.03*np.sin(2*np.pi*1000*t)]),sr)
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    pair={'status':'needs_review','a_report_id':'a','b_report_id':'b','a_title':'A','b_title':'B','entry_sec':4.,'handoff_sec':6.,'overlap_bars':1,
          'mapping':{'a':{'rate':1},'b':{'rate':1,'playback_start_sec':4.,'source_cue_sec':0}},
          'gains':{'a_trim_db':0,'b_trim_db':0},'eq':{'b_mid_cut_db':0,'restore_start_sec':5.5,'restore_end_sec':6.,'low_hz':250,'high_hz':4000},
          'low_eq':{'cutoff_hz':140,'b_cut_db':-7,'a_end_cut_db':-9,'entry_sec':4.,'handoff_sec':6.,'b_restore_start_sec':5.5,'b_restore_end_sec':6.},
          'events':[{'name':'开始可听交接','planned_sec':4.},{'name':'完成交接：A 静音 / B 释放','planned_sec':6.}]}
    tracks=[{'title':x,'report_id':x,'path':str(source),'audio_sha256':sha,'end_sec':6.} for x in ('a','b')]
    result=demo_render.render({'tracks':tracks,'pairs':[pair]},tmp_path/'out',preview=True)
    events={e['name']:e for e in result['events']}
    assert abs(events['B 低频开始恢复']['actual_sec']-5.5)<=1/sr+1e-9
    assert abs(events['B 低频恢复正常']['actual_sec']-6.)<=1/sr+1e-9
    assert abs(events['A 低频开始衰减']['actual_sec']-4.)<=1/sr+1e-9
    assert float(result['mp3_levels']['input_tp'])<=-1


def test_ready_snare_clap_schema_can_contribute_to_route_score():
    from analysis_platform.demo_v2 import drum_similarity
    a={k:{'pattern_16':'X...X...X...X...','status':'ready'} for k in ('kick','snare_clap','hihat')}
    result=drum_similarity(a,a)
    assert result['weight']>0 and result['score']==1
