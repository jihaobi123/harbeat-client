import copy
import importlib.util
from pathlib import Path

import pytest


def api():
    assert importlib.util.find_spec('analysis_platform'), 'independent analysis platform package is required'
    from analysis_platform.report import build_report
    return build_report


def test_report_preserves_all_input_and_millisecond_precision():
    raw = {'source': {'duration_ms': 12345}, 'analysis': {
        'beat_grid': {'beats_ms': [123, 623], 'downbeats_ms': [123]},
        'tempo': {'bpm': 120}, 'sections': {'items': [{'start_ms': 123, 'end_ms': 12345, 'label': 'drop'}]},
        'future_feature': {'nested': [1, 2, 3]}}}
    before = copy.deepcopy(raw)
    report = api()({'manifest': raw}, {}, {})
    assert raw == before
    assert report['documents']['manifest'] == raw
    assert report['timeline']['beats'] == [.123, .623]
    assert report['timeline']['sections'][0]['start'] == .123
    assert report['summary']['bpm'] == 120


def test_missing_is_not_zero_and_extension_does_not_override_core():
    report = api()({'core': {'key': 'Am', 'phrase_map': []}}, {
        'emotion': {'status': 'unavailable', 'reason': 'weights missing'},
        'repeat': {'status': 'ready', 'data': {'sections': [{'label': 'chorus'}]}}}, {})
    assert report['summary']['bpm'] is None
    assert report['summary']['key'] == 'Am'
    assert report['timeline']['sections'] == []
    assert report['extensions']['emotion']['status'] == 'unavailable'


def test_report_handles_track_analysis_and_rejects_bad_numbers():
    report = api()({'track': {'audio': {'duration_sec': 20}, 'timeline': {'beat_times_sec': [0.1, 0.6]},
        'track_summary': {'bpm': {'value': 120}}, 'sections': []}}, {}, {})
    assert report['summary']['bpm'] == 120
    assert report['timeline']['beats'] == [.1, .6]
    with pytest.raises(ValueError):
        api()({'core': {'bpm': float('nan')}}, {}, {})


def test_source_audio_hash_binding_is_preserved_and_mismatch_rejected():
    report = api()({'core': {'audio_sha256': 'a'*64, 'duration': 2}}, {}, {})
    assert report['audio']['sha256'] == 'a'*64
    with pytest.raises(ValueError):
        api()({'core': {'audio_sha256': 'a'*64}, 'instruments': {'audio_sha256': 'b'*64}}, {}, {})


def test_evaluation_needs_same_audio_and_one_to_one_events():
    api()
    from analysis_platform.evaluation import event_metrics, compare_annotations
    assert event_metrics([1, 1.01, 1.02], [1], .07)['precision'] == pytest.approx(1/3)
    with pytest.raises(ValueError):
        compare_annotations({'audio': {'sha256': 'a'}}, {'audio_sha256': 'b'})


def test_extension_failure_preserves_other_modules(tmp_path):
    api()
    from analysis_platform.runner import run_modules
    def success(*args): return {'points': [{'time': 0, 'value': .2}]}
    def failure(*args): raise RuntimeError('intentional test failure')
    result = run_modules(Path('unused'), {}, {}, {'ok': success, 'bad': failure})
    assert result['ok']['status'] == 'ready'
    assert result['bad']['status'] == 'failed'
    assert 'intentional' in result['bad']['reason']


def test_model_class_filter_keeps_indices():
    api()
    from analysis_platform.model_worker import select_instruments, emotion_points
    assert select_instruments(['guitar', 'voice', 'piano'], [.8, .99, .1], .35) == [{'label': 'guitar', 'score': .8}]
    points = emotion_points([[5, 9], [1, 5]], 1.6)
    assert points[0]['valence'] == 0 and points[0]['arousal'] == 1
    assert all(p['end'] <= 1.6 for p in points)


def test_roughness_silence_and_gain_invariance():
    from analysis_platform.features import roughness_points
    import numpy as np
    sr = 22050
    t = np.arange(sr) / sr
    y = np.sin(2*np.pi*440*t) + .5*np.sin(2*np.pi*470*t)
    a = roughness_points(y, sr)
    b = roughness_points(y * .3, sr)
    assert a[0]['value'] == pytest.approx(b[0]['value'], abs=1e-5)
    assert all(p['value'] is None for p in roughness_points(np.zeros(sr), sr))
    assert a[-1]['end'] <= 1


def test_repeat_clusters_do_not_name_chorus(tmp_path):
    from analysis_platform.features import repeat_sections
    import numpy as np
    import soundfile as sf
    sr = 22050
    t = np.arange(sr*2) / sr
    a = np.sin(2*np.pi*261.63*t)
    b = np.sin(2*np.pi*369.99*t)
    p = tmp_path / 'test.wav'
    sf.write(p, np.concatenate([a,b,a]), sr)
    result = repeat_sections(p, {'sections': [{'start': i*2, 'end': (i+1)*2, 'label': 'custom'} for i in range(3)]}, {})
    assert result['segments'][0]['cluster'] == result['segments'][2]['cluster']
    assert all(s['label'] == 'custom' for s in result['segments'])


def test_unavailable_emotion_is_not_evaluated_as_zero():
    from analysis_platform.evaluation import compare_annotations
    report=api()({'core':{'audio_sha256':'a'*64}}, {'emotion':{'status':'unavailable','data':None}})
    result=compare_annotations(report,{'audio_sha256':'a'*64,'emotion':[{'time':1,'valence':0,'arousal':.5}]})
    assert result['status'] == 'not_evaluated'
    assert result['metrics'] == {}


def test_module_results_are_checkpointed_before_next_module():
    from analysis_platform.runner import run_modules
    events=[]
    run_modules(Path('unused'), {}, {}, {'first':lambda *args:{'value':1},'second':lambda *args:{'value':2}},
                progress=lambda name:events.append(('start',name)),on_result=lambda name,result:events.append(('saved',name,result['status'])))
    assert events == [('start','first'),('saved','first','ready'),('start','second'),('saved','second','ready')]


def test_partial_source_coverage_is_visible_without_filling_missing_sections():
    report=api()({'core':{'sections':[{'start':0,'end':420,'label':'custom'}]}},audio={'duration':2291.54})
    assert report['diagnostics']['section_end_sec'] == 420
    assert report['diagnostics']['warnings']
    assert report['timeline']['sections'] == [{'start':0,'end':420,'label':'custom'}]


def test_container_contract_mounts_external_audio_and_models(tmp_path):
    import json
    from analysis_platform.container_runtime import command,cleanup
    request=tmp_path/'request.json'
    audio=tmp_path/'nas'/'music'/'track.wav';models=tmp_path/'nas'/'weights'
    request.write_text(json.dumps({'audio':str(audio),'config':{'models_dir':str(models)}}))
    cmd,cid=command(['-m','analysis_platform.model_worker','emotion',str(request),str(tmp_path/'output.json')],tmp_path/'repo')
    assert f'{audio.parent}:{audio.parent}:ro' in cmd
    assert f'{models}:{models}:ro' in cmd
    assert '--cidfile' in cmd
    cid.write_text('not-a-container-id')
    cleanup(cid)  # malformed IDs never become Docker arguments


def test_worker_timeout_cleans_recorded_container(tmp_path,monkeypatch):
    import subprocess
    from analysis_platform.runner import run_worker
    import analysis_platform.container_runtime as runtime
    cleaned=[]
    monkeypatch.setattr(runtime,'cleanup',lambda p:cleaned.append(p.name))
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('model',1)
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(subprocess.TimeoutExpired):run_worker('emotion',tmp_path/'a.wav',{}, {'timeout_sec':1})
    assert cleaned == ['container.cid']
def test_native_decode_downmixes_in_blocks_and_checks_memory_before_decode(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf
    from types import SimpleNamespace
    from analysis_platform.native_audio import load_audio
    path = tmp_path/'stereo.wav'
    frames = np.stack([np.full(16000, .25), np.full(16000, .75)], axis=1)
    sf.write(path, frames, 16000, subtype='FLOAT')
    output = load_audio(path, lambda **kwargs: lambda x: x)
    assert output.shape == (16000,)
    assert np.allclose(output, .5)
    monkeypatch.setattr(sf, 'info', lambda p: SimpleNamespace(frames=300_000_000, samplerate=96000, duration=3125))
    monkeypatch.setattr(sf, 'blocks', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('must not decode')))
    import pytest
    with pytest.raises(ValueError, match='内存'):
        load_audio(path, None)
