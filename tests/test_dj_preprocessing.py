import copy
import pytest
from analysis_platform.report import build_report


def fixture_report(intro=16, chorus=16, bpm=120):
    step=60/bpm
    duration=80*step/.5
    scale=step/.5
    return build_report({'core':{'bpm':bpm,'beat_points':[i*step for i in range(161)],
        'downbeats':[i*4*step for i in range(41)],'time_signature':{'numerator':4,'denominator':4},
        'sections':[{'start':0,'end':intro*scale,'label':'intro'},
                    {'start':intro*scale,'end':32*scale,'label':'verse'},
                    {'start':32*scale,'end':(32+chorus)*scale,'label':'chorus'}]},
        'vocal_activity':{'status':'ready','time_origin':'master_audio_start','duration_ms':round(duration*1000),
                          'intervals':[{'start_ms':1000,'end_ms':2000},{'start_ms':33000,'end_ms':34000}]}},
        {'dj_signals':{'status':'ready','data':{'audio_sha256':'a'*64,'duration':duration,
            'local_loudness':[{'start':i*.5,'end':i*.5+3,'lufs':-15.0} for i in range(int((duration-3)/.5)+1)],
            'sample_peak_dbfs':-3,'rms_points':[], 'vocals':{'status':'unavailable'}}}},
        {'sha256':'a'*64,'hash_verification':'verified','duration':duration})


def confirmed(report):
    from analysis_platform.dj_contract import build
    data=build(report)
    return build(report,{'source_fingerprint':data['source_fingerprint'],'revision':1,
        'anchors':{},'confirmations':{'structure':True,'grid':True,'vocals':True}})


def test_adjacent_chorus_segments_form_one_episode_and_sources_remain_unchanged():
    from analysis_platform.dj_contract import build
    r=fixture_report();r['documents']['core']['sections'][-1]['end']=40
    r['documents']['core']['sections'].append({'start':40,'end':48,'label':'chorus'})
    original=copy.deepcopy(r)
    result=build(r)
    assert result['anchors']['chorus_end']['raw_sec']==48
    assert result['roles']['outgoing']['bar_count']==8
    assert result['roles']['outgoing']['status']=='needs_review'
    assert r==original


def test_songformer_source_is_selected_and_intro_followed_by_chorus_is_not_verse():
    from analysis_platform.dj_contract import build
    r=fixture_report();r['documents']['songformer-sections']={'status':'ready','segments':[
        {'start':0,'end':16,'label':'intro'},{'start':16,'end':32,'label':'chorus'},
        {'start':32,'end':48,'label':'verse'}]}
    d=build(r)
    assert d['structure']['source']=='songformer-sections'
    assert 'intro_not_followed_by_verse' in [x['code'] for x in d['roles']['incoming']['issues']]


def test_missing_meter_and_unknown_vocals_never_mean_ready_or_silence():
    from analysis_platform.dj_contract import build
    r=fixture_report();del r['documents']['core']['time_signature'];del r['documents']['vocal_activity']
    d=build(r)
    assert d['grid']['status']=='blocked'
    assert d['vocals']['status']=='unavailable'
    assert d['vocals']['intervals'] is None


def test_out_of_range_vocal_intervals_are_not_silently_read_as_silence():
    from analysis_platform.dj_contract import build
    r=fixture_report();r['documents']['vocal_activity']['intervals']=[{'start_ms':90000,'end_ms':91000}]
    assert build(r)['vocals']['status']=='unavailable'


def test_malformed_fallback_vocals_cannot_mark_a_plan_ready():
    from analysis_platform.dj_contract import build
    r=fixture_report();del r['documents']['vocal_activity']
    r['extensions']['dj_signals']['data']['vocals']={'status':'candidate','intervals':None}
    d=confirmed(r)
    assert d['vocals']['status']=='unavailable'
    assert d['roles']['outgoing']['status']=='blocked'


def test_grid_review_flag_can_be_resolved_by_explicit_listening_confirmation():
    r=fixture_report();r['documents']['core']['beat_needs_review']=True
    assert confirmed(r)['roles']['outgoing']['status']=='ready'


def test_intro_semantic_conflict_visible_even_when_grid_snap_fails():
    from analysis_platform.dj_contract import build
    r=fixture_report();r['documents']['core']['sections'][0]['end']=15.5
    assert 'intro_not_followed_by_verse' in [v['code'] for v in build(r)['roles']['incoming']['issues']]


def test_misaligned_boundary_keeps_raw_value_and_requires_review():
    from analysis_platform.dj_contract import build
    r=fixture_report();r['documents']['core']['sections'][-1]['end']=47.5
    d=build(r)
    assert d['anchors']['chorus_end']['raw_sec']==47.5
    assert d['anchors']['chorus_end']['suggested_sec']==48
    assert d['anchors']['chorus_end']['usable_sec'] is None
    assert d['roles']['outgoing']['status']=='blocked'


def test_partial_bar_and_mismatched_downbeat_are_rejected():
    from analysis_platform.dj_contract import build
    r=fixture_report();r['documents']['core']['beat_points'].remove(33.5)
    d=build(r)
    assert any(not b['complete'] for b in d['grid']['bars'])
    assert d['roles']['outgoing']['status']=='blocked'


def test_per_bar_vocal_coverage_uses_intersection_not_whole_song_density():
    from analysis_platform.dj_contract import build
    d=build(fixture_report())
    assert d['grid']['bars'][0]['vocal_active_sec']==1
    assert d['grid']['bars'][0]['vocal_ratio']==.5
    assert d['grid']['bars'][1]['vocal_active_sec']==0
    r=fixture_report();del r['documents']['vocal_activity']
    assert build(r)['grid']['bars'][0]['vocal_ratio'] is None


def test_revision_becomes_stale_when_source_changes_but_not_unrelated_extension():
    from analysis_platform.dj_contract import build
    r=fixture_report();saved={'source_fingerprint':build(r)['source_fingerprint'],'revision':1,
        'confirmations':{'structure':True,'grid':True,'vocals':True}}
    assert build(r,saved)['roles']['outgoing']['status']=='ready'
    r['extensions']['genre']={'status':'ready','data':{'top':[]}}
    assert build(r,saved)['review']['status']=='current'
    r['documents']['core']['sections'][-1]['end']=46
    assert build(r,saved)['review']['status']=='stale'
    assert build(r,saved)['roles']['outgoing']['status']!='ready'


def test_replacing_vocal_asset_invalidates_review_and_old_fallback():
    from analysis_platform.dj_contract import build
    r=fixture_report();del r['documents']['vocal_activity']
    r['audio']['assets']={'vocals':{'id':'old'}}
    r['extensions']['dj_signals']['data']['vocals']={'status':'candidate','intervals':[], 'asset':{'id':'old'}}
    saved={'source_fingerprint':build(r)['source_fingerprint'],'confirmations':{'structure':True,'grid':True,'vocals':True}}
    r['audio']['assets']['vocals']['id']='new'
    d=build(r,saved)
    assert d['review']['status']=='stale'
    assert d['vocals']['status']=='unavailable'


@pytest.mark.parametrize('a_chorus,b_intro,case,b_start',[(16,16,'equal',0),(24,16,'a_longer',0)])
def test_transition_uses_source_to_playback_mapping(a_chorus,b_intro,case,b_start):
    from analysis_platform.dj_plan import plan
    a=confirmed(fixture_report(chorus=a_chorus))
    b=confirmed(fixture_report(intro=b_intro,bpm=100))
    p=plan(a,b,target_bpm=120)
    assert p['status']=='ready'
    assert p['case']==case
    assert p['mapping']['b']['rate']==pytest.approx(1.2)
    assert p['mapping']['b']['source_cue_sec']==b_start
    assert p['handoff_sec']==32+a_chorus
    assert p['entry_sec']==32+a_chorus-b_intro
    assert p['events'][-1]['actual_sec'] is None


def test_long_intro_requires_explicit_policy_and_four_bar_tail_is_exact():
    from analysis_platform.dj_plan import plan
    a=confirmed(fixture_report(chorus=8));b=confirmed(fixture_report(intro=24))
    p=plan(a,b)
    assert p['status']=='blocked'
    assert 'long_intro_policy_required' in [x['code'] for x in p['issues']]
    p=plan(a,b,long_intro_policy='silent_preroll')
    assert p['entry_sec']==32
    assert p['mapping']['b']['playback_start_sec']==16
    assert p['mapping']['b']['source_at_entry_sec']==16
    assert p['eq']['restore_start_sec']==39


def test_both_sections_have_vocals_but_actual_overlap_is_independently_reported():
    from analysis_platform.dj_plan import plan
    a=confirmed(fixture_report());b=confirmed(fixture_report())
    p=plan(a,b)
    assert p['eq']['b_mid_cut_db']<0
    assert p['vocal_overlap']['rule_triggered'] is True
    assert p['vocal_overlap']['simultaneous_intervals']  # both are 33..34 on common clock


def test_small_tempo_variation_cannot_accumulate_unbounded_phase_error():
    from analysis_platform.dj_plan import plan
    a=confirmed(fixture_report());b=confirmed(fixture_report(bpm=119))
    p=plan(a,b,target_bpm=120)
    assert p['mapping']['max_beat_error_ms']<1


def test_review_api_revision_lock_and_no_source_mutation(tmp_path):
    from fastapi.testclient import TestClient
    from analysis_platform.server import create_app
    from analysis_platform.store import Store
    r=fixture_report();Store(tmp_path).save_report(r)
    with TestClient(create_app(tmp_path,run_workers=False)) as c:
        url='/api/analysis-lab/reports/'+r['id']
        d=c.get(url+'/dj').json()
        payload={'expected_revision':0,'source_fingerprint':d['source_fingerprint'],
                 'confirmations':{'structure':True,'grid':True,'vocals':True},'anchors':{},'note':'试听校准'}
        assert c.post(url+'/dj-review',json=payload).status_code==200
        assert c.post(url+'/dj-review',json=payload).status_code==409
        assert c.get(url).json()['source_hashes']==r['source_hashes']
        assert c.get(url+'/dj').json()['roles']['outgoing']['status']=='ready'
