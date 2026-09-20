import numpy as np
import soundfile as sf
import pytest


def test_decoder_fallback_checks_duration_and_preserves_provenance(tmp_path,monkeypatch):
    import analysis_platform.dj_signals as m
    from types import SimpleNamespace
    p=tmp_path/'audio.wav';sf.write(p,np.zeros(16000),16000)
    real=m._read_power
    def fail_original(path,k_weight=False):
        if str(path)==str(p):raise sf.LibsndfileError(1,'decoder tail failure')
        return real(path,k_weight)
    def transcode(args,**kwargs):
        sf.write(args[-1],np.zeros(16000),16000,subtype='FLOAT')
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(m,'_read_power',fail_original)
    monkeypatch.setattr(m.subprocess,'run',transcode)
    d=m.analyze(p,{'audio_sha256':'a'*64},{})
    assert d['decoder']=='ffmpeg_pcm_f32le_strict'
    assert d['duration']==1 and d['audio_sha256']=='a'*64
    def wrong_length(args,**kwargs):
        sf.write(args[-1],np.zeros(18000),16000)
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(m.subprocess,'run',wrong_length)
    with pytest.raises(ValueError,match='duration'):m.analyze(p,{}, {})


def test_streaming_power_preserves_antiphase_and_marks_silence_unknown_loudness(tmp_path):
    from analysis_platform.dj_signals import analyze
    sr=16000;t=np.arange(sr*4)/sr;y=.1*np.sin(2*np.pi*440*t)
    path=tmp_path/'audio.wav';sf.write(path,np.column_stack([y,-y]),sr,subtype='FLOAT')
    d=analyze(path,{'audio_sha256':'a'*64},{})
    assert d['rms_points'][20]['rms_dbfs']==pytest.approx(-23.01,abs=.1)
    assert len(d['local_loudness'])==3
    assert d['local_loudness'][0]['lufs'] is not None
    assert d['vocals']['status']=='unavailable'
    sf.write(path,np.zeros(sr*4),sr)
    s=analyze(path,{'audio_sha256':'a'*64},{})
    assert s['sample_peak_dbfs'] is None
    assert all(p['lufs'] is None for p in s['local_loudness'])
    assert s['silence_intervals']==[{'start':0.,'end':4.}]


def test_fine_vocal_candidates_keep_alignment_and_method_limits(tmp_path):
    from analysis_platform.dj_signals import analyze
    sr=16000;master=tmp_path/'master.wav';stem=tmp_path/'vocal.wav'
    y=np.zeros(sr*4);y[sr:sr*2]=.3*np.sin(2*np.pi*300*np.arange(sr)/sr)
    sf.write(master,y,sr);sf.write(stem,y,sr)
    d=analyze(master,{'audio_sha256':'a'*64,'stem_paths':{'vocals':str(stem)},'stem_assets':{'vocals':{'id':'asset'}}},{})
    assert d['vocals']['status']=='candidate'
    assert d['vocals']['intervals'][0]['start']==pytest.approx(1,abs=.05)
    assert d['vocals']['intervals'][0]['end']==pytest.approx(2,abs=.05)
    assert d['vocals']['confirmed'] is False
    sf.write(stem,y[:sr*2],sr)
    assert analyze(master,{'audio_sha256':'a'*64,'stem_paths':{'vocals':str(stem)}},{})['vocals']['status']=='unavailable'


def test_k_weighted_3s_matches_ungated_meter_for_steady_tone(tmp_path):
    import pyloudnorm as pyln
    from analysis_platform.dj_signals import analyze
    sr=22050;t=np.arange(sr*5)/sr;y=np.column_stack([.1*np.sin(2*np.pi*1000*t)]*2)
    p=tmp_path/'tone.wav';sf.write(p,y,sr,subtype='FLOAT')
    d=analyze(p,{'audio_sha256':'a'*64},{})
    assert d['local_loudness'][0]['lufs']==pytest.approx(pyln.Meter(sr).integrated_loudness(y[:sr*3]),abs=.1)
    assert d['window_sec_actual']==pytest.approx(round(sr*.05)/sr)
