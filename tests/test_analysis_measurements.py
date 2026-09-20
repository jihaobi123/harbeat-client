import json
import numpy as np
import pytest


def test_dynamics_gain_invariance_silence_and_section_difference():
    from analysis_platform.measurements import dynamics
    sr=22050
    t=np.arange(sr*4)/sr
    y=np.sin(2*np.pi*440*t)*.1
    y[sr*2:]*=2
    sections=[{'start':0,'end':2,'label':'verse'},{'start':2,'end':4,'label':'chorus'}]
    a=dynamics(y,sr,sections); b=dynamics(y*.1,sr,sections)
    assert a['rms_p95_p5_db']==pytest.approx(b['rms_p95_p5_db'],abs=.02)
    assert a['sections'][1]['delta_rms_db']==pytest.approx(6.0206,abs=.02)
    assert a['sections'][1]['delta_lufs']==pytest.approx(6.0206,abs=.02)
    z=dynamics(np.zeros(sr),sr,[])
    assert z['rms_p95_p5_db'] is None and z['relative_silence_ratio']==1
    assert z['integrated_lufs'] is None
    json.dumps(z,allow_nan=False)


def test_onsets_respect_real_time_and_silence():
    from analysis_platform.measurements import onset_statistics
    sr=22050; y=np.zeros(sr*10)
    rng=np.random.default_rng(3)
    for sec in range(1,10): y[sec*sr:sec*sr+400]=rng.normal(0,.2,400)
    result=onset_statistics(y,sr)
    assert 8<=result['count']<=10
    assert result['events_per_minute']==pytest.approx(result['count']*6)
    assert len(result['windows'])==2 and result['windows'][-1]['end']==10
    assert onset_statistics(np.zeros(sr),sr)['count']==0


def test_chords_preserve_no_chord_and_unknown_tail():
    from analysis_platform.chords import normalize_segments
    r=normalize_segments([(0,1,'N'),(1,2,'C:maj'),(2,3,'A:min')],3.05)
    assert [s['label'] for s in r]==['N','C:maj','A:min','unknown']
    assert r[-1]['end']==3.05
    assert all(s['confidence'] is None for s in r)


def test_emotion_time_weighting_gaps_and_hysteresis():
    from analysis_platform.emotion_summary import summarize
    pts=[{'start':0,'end':1,'valence':-.5,'arousal':0},
         {'start':1,'end':3,'valence':.5,'arousal':1},
         {'start':8,'end':9,'valence':-.5,'arousal':0}]
    r=summarize(pts,[{'start':0,'end':3,'label':'intro'}],10)
    assert r['covered_seconds']==4 and r['coverage_ratio']==.4
    assert r['valence_mean']==0 and r['arousal_mean']==.5
    assert r['polarity_switches']==1  # gaps do not count as switches
    assert r['sections'][0]['arousal_mean']==pytest.approx(2/3)
    assert summarize([],[],10)['valence_mean'] is None


def test_core_missing_beats_are_not_fabricated(tmp_path):
    import soundfile as sf
    from analysis_platform.measurements import core_features
    p=tmp_path/'silence.wav';sf.write(p,np.zeros(22050),22050)
    r=core_features(p,{'beats':[],'downbeats':[],'summary':{}},{})
    assert r['rhythm']['status']=='unavailable'
    assert r['tonality']['status']=='unavailable'
    assert r['timbre']['status']=='unavailable'


def test_decode_budget_checked_before_loading():
    from analysis_platform.measurements import check_budget
    from analysis_platform.runner import Unavailable
    from types import SimpleNamespace
    with pytest.raises(Unavailable,match='memory'):
        check_budget(SimpleNamespace(frames=7200*48000,channels=2,samplerate=48000))


def test_partial_timbre_failure_is_not_ready(tmp_path,monkeypatch):
    import soundfile as sf
    from analysis_platform import core_source_snapshot as original
    from analysis_platform.measurements import core_features
    sr=22050;p=tmp_path/'tone.wav';sf.write(p,np.sin(2*np.pi*440*np.arange(sr)/sr)*.1,sr)
    def bad(*args):
        original.logger.warning('partial extraction failed')
        return {'spectral_centroid':400,'spectral_rolloff':0}
    monkeypatch.setattr(original,'timbre_features',bad)
    r=core_features(p,{'beats':[0,.2,.4,.6],'summary':{}},{})
    assert r['timbre']['status']=='failed'
    assert r['rhythm']['data']['bpm'] is None


def test_emotion_summary_rejects_explicit_wrong_audio_identity():
    from analysis_platform.emotion_summary import derive
    from analysis_platform.runner import Unavailable
    base={'audio_sha256':'a'*64,'summary':{'duration':1},'extensions':{'emotion':{'status':'ready','data':{'audio_sha256':'b'*64,'points':[{'start':0,'end':1,'valence':0,'arousal':0}]}}}}
    with pytest.raises(Unavailable):derive(None,base,{})


def test_zero_evidence_tonality_is_failed(tmp_path,monkeypatch):
    import soundfile as sf
    from analysis_platform import core_source_snapshot as original
    from analysis_platform.measurements import core_features
    sr=22050;p=tmp_path/'tone.wav';sf.write(p,np.sin(2*np.pi*440*np.arange(sr)/sr)*.1,sr)
    monkeypatch.setattr(original,'_analyze_key',lambda *args:{'key':'C major','key_confidence':0,'candidates':[{'score':0}]})
    assert core_features(p,{'beats':[],'summary':{}},{})['tonality']['status']=='failed'
