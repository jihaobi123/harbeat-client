import numpy as np
import pytest
from analysis_platform.demo_render import mid_eq, fade_curve, validate_pair, compile_set


def test_mid_cut_restores_and_preserves_other_bands():
    sr=16000;t=np.arange(sr*3)/sr
    cut=np.where(t<1,-9,np.where(t<2,-9*(2-t),0))
    for hz,expected in [(100,1),(1000,10**(-9/20)),(6500,1)]:
        x=np.sin(2*np.pi*hz*t)[:,None]*.1;y=mid_eq(x,sr,cut,250,4000)
        ratio=np.linalg.norm(y[sr//4:sr*3//4])/np.linalg.norm(x[sr//4:sr*3//4])
        assert ratio==pytest.approx(expected,abs=.035)
        assert np.max(np.abs(y[sr*2:]-x[sr*2:]))<1e-7


def test_fades_share_handoff_and_no_audio_before_entry():
    t=np.array([0.,1.,1.5,2.,3.])
    b=fade_curve(t,1,2,True);a=fade_curve(t,1,2,False)
    assert np.allclose(a+b,1)
    assert list(b)==[0,0,.5,1,1]


def test_blocked_plan_never_renders_and_preview_is_explicit():
    with pytest.raises(ValueError):validate_pair({'status':'blocked'},True)
    with pytest.raises(ValueError):validate_pair({'status':'needs_review'},False)


def test_set_uses_cumulative_offsets_and_checks_inconsistent_rates():
    def pair(a,b,rate=1):
        return {'status':'ready','a_report_id':a,'b_report_id':b,'entry_sec':80,'handoff_sec':90,
                'mapping':{'a':{'rate':1},'b':{'rate':rate,'playback_start_sec':80,'source_cue_sec':0}},
                'eq':{'b_mid_cut_db':-9,'restore_start_sec':89,'restore_end_sec':90,'low_hz':250,'high_hz':4000},
                'gains':{'a_trim_db':-3,'b_trim_db':-5},'events':[]}
    p=[pair('a','b'),pair('b','c')];tracks=[{'report_id':x,'end_sec':90} for x in 'abc']
    result=compile_set(tracks,p,44100,False)
    assert [x['offset_sec'] for x in result]==[0,80,160]
    assert result[1]['trim_db']==-5
    p[0]['mapping']['b']['rate']=1.1
    with pytest.raises(ValueError,match='rate'):compile_set(tracks,p,44100,False)


def test_preview_keeps_sources_and_does_not_claim_human_review():
    import copy
    from test_dj_preprocessing import fixture_report
    from analysis_platform.demo_preview import candidate
    r=fixture_report();r['timeline']['downbeats']=r['timeline']['downbeats'][4:];original=copy.deepcopy(r)
    d=candidate(r)
    assert r==original
    assert d['preview_estimation']['human_confirmed'] is False
    assert d['review']['status']=='not_reviewed'
    assert d['roles']['incoming']['status']=='needs_review'
    assert d['anchors']['intro_start']['source']=='automatic_preview_snap_not_human_review'


def test_prefix_requires_explicit_silent_policy():
    from test_dj_preprocessing import fixture_report,confirmed
    from analysis_platform.dj_plan import plan
    a=confirmed(fixture_report());b=confirmed(fixture_report())
    b['roles']['incoming']['start_sec']=.1
    assert any(x['code']=='intro_has_prefix' for x in plan(a,b)['issues'])
    assert not any(x['code']=='intro_has_prefix' for x in plan(a,b,intro_prefix_policy='silent_preroll')['issues'])
