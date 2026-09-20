import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


def test_media_registry_rejects_unregistered_and_escaped_paths(tmp_path):
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    root=tmp_path/'nas';root.mkdir()
    registry=MediaRegistry(Store(tmp_path/'store'), [root])
    outside=tmp_path/'private.wav';sf.write(outside,np.zeros(16000),16000)
    with pytest.raises(ValueError):registry.register(outside)
    (root/'escape.wav').symlink_to(outside)
    with pytest.raises(ValueError):registry.register(root/'escape.wav')
    path=root/'vocals.wav';sf.write(path,np.ones(16000)*.2,16000)
    asset=registry.register(path)
    assert registry.resolve(asset['id']) == path
    with pytest.raises(FileNotFoundError):registry.resolve('a'*64)
    sf.write(path,np.ones(20000)*.4,16000)
    with pytest.raises(ValueError,match='changed'):registry.resolve(asset['id'])


def test_real_stem_measurement_preserves_missing_as_unknown(tmp_path):
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    from analysis_platform.stems import measure_stems
    root=tmp_path/'nas';root.mkdir();path=root/'vocals.wav'
    sf.write(path,np.concatenate([np.zeros(16000),np.ones(16000)*.5]),16000)
    registry=MediaRegistry(Store(tmp_path/'store'),[root]);asset=registry.register(path)
    result=measure_stems({'vocals':asset},registry,window_sec=1)
    assert result['stem_activity_windows'][0]['vocals']==0
    assert result['stem_activity_windows'][1]['vocals'] == pytest.approx(1)
    assert 'drums' not in result['stem_activity_windows'][0]
    assert result['method']=='separated_audio_rms_p95'


def test_all_sources_supply_stem_views_without_rewriting_primary():
    from analysis_platform.report import build_report
    core={'bpm':123,'future_feature':{'original':True}}
    secondary={'method':'separated_audio_rms_p95','stem_activity_windows':[{'start':0,'end':2,'vocals':.4}]}
    r=build_report({'core':core,'separated_stem_activity':secondary})
    assert r['documents']['core']==core
    assert r['timeline']['stems'][0]['vocals']==.4
    assert r['view_sources']['stems']=='separated_stem_activity'


def test_nas_manifest_keeps_all_fields_and_registers_stems(tmp_path):
    from analysis_platform.catalog import import_manifest
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    root=tmp_path/'nas';root.mkdir();store=Store(tmp_path/'store');registry=MediaRegistry(store,[root])
    for n in ['master','vocals']:sf.write(root/(n+'.wav'),np.ones(16000)*.1,16000)
    manifest={'schema_name':'same_style_track_preprocess','track_id':'track-1','source':{'title':'Real','duration_ms':1000},
        'analysis':{'tempo':{'bpm':120},'energy':{'curve':[{'start_ms':0,'end_ms':1000,'value':.5}]},'future_metric':[1,2]},
        'assets':{'master':{'storage_key':'master.wav'},'stems':{'vocals':{'storage_key':'vocals.wav'}}}}
    path=root/'manifest.json';path.write_text(json.dumps(manifest))
    r=import_manifest(path,root,store,registry)
    assert r['documents']['core']==manifest
    assert r['audio']['assets']['vocals']['id']
    assert r['summary']['bpm']==120
    assert r['timeline']['energy'][0]['value']==.5


def test_stereo_energy_does_not_cancel_opposite_channels(tmp_path):
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    from analysis_platform.stems import measure_stems
    root=tmp_path/'nas';root.mkdir();path=root/'vocals.wav'
    sf.write(path,np.tile([.5,-.5],(16000,1)),16000)
    registry=MediaRegistry(Store(tmp_path/'store'),[root])
    result=measure_stems({'vocals':registry.register(path)},registry)
    assert result['stem_activity_windows'][0]['vocals_rms']==pytest.approx(.5)


def test_library_without_sha_does_not_adopt_mismatched_sidecar(tmp_path):
    from analysis_platform.catalog import import_library
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    import hashlib
    root=tmp_path/'nas';root.mkdir();path=root/'original.wav'
    sf.write(path,np.ones(16000)*.1,16000)
    side=root/'instrument-analysis';side.mkdir()
    (side/'track1.json').write_text(json.dumps({'track_id':'track1','audio_sha256':'f'*64}))
    store=Store(tmp_path/'store');registry=MediaRegistry(store,[root])
    result=import_library({'id':'track1','title':'Track','source_path':str(path),'stems':{}},root,store,registry)
    assert result['audio']['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert 'instrument-analysis' not in result['documents']
    assert '指纹不一致' in result['documents']['source_binding_notes']['instrument-analysis']


def test_registered_audio_range_auth_and_upload_preserve_stem_association(tmp_path,monkeypatch):
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    from analysis_platform.server import create_app
    from analysis_platform.report import build_report
    from fastapi.testclient import TestClient
    import hashlib
    root=tmp_path/'nas';root.mkdir();path=root/'original.wav'
    sf.write(path,np.ones(16000)*.1,16000)
    blob=path.read_bytes();sha=hashlib.sha256(blob).hexdigest()
    store=Store(tmp_path/'store');registry=MediaRegistry(store,[root]);asset=registry.register(path,sha)
    report=build_report({'core':{'bpm':120}},audio={'sha256':sha,'assets':{'master':asset,'vocals':asset},'catalog_track_id':'keep-me'})
    store.save_report(report)
    monkeypatch.setenv('ANALYSIS_MEDIA_ROOTS',str(root));monkeypatch.setenv('ANALYSIS_RELAY_TOKEN','s'*40)
    headers={'x-analysis-relay-token':'s'*40}
    with TestClient(create_app(store.root,run_workers=False),base_url='http://localhost') as client:
        assert client.get('/api/analysis-lab/media/'+asset['id']).status_code==401
        result=client.get('/api/analysis-lab/media/'+asset['id'],headers={**headers,'Range':'bytes=0-99'})
        assert result.status_code==206 and result.content==blob[:100]
        assert client.get('/api/analysis-lab/media/'+'a'*64,headers=headers).status_code==404
        job=client.post('/api/analysis-lab/jobs',headers=headers,data={'report_id':report['id']},files={'audio':('original.wav',blob,'audio/wav')}).json()
        assert job['audio']['assets']==report['audio']['assets']
        assert job['audio']['catalog_track_id']=='keep-me'


def test_index_upgrade_includes_old_reports_when_worker_saves_first(tmp_path):
    from analysis_platform.store import Store
    from analysis_platform.report import build_report
    store=Store(tmp_path)
    old=build_report({'core':{'title':'old'}});new=build_report({'core':{'title':'new'}})
    store.write(store.path('reports',old['id']),old)
    store.save_report(new)
    assert {r['title'] for r in store.reports()}=={'old','new'}


def test_sidecar_without_fingerprint_is_reference_only(tmp_path):
    from analysis_platform.catalog import import_library
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    root=tmp_path/'nas';root.mkdir();side=root/'instrument-analysis';side.mkdir()
    (side/'track1.json').write_text(json.dumps({'track_id':'track1','bars':[]}))
    store=Store(tmp_path/'store')
    result=import_library({'id':'track1','original_sha256':'a'*64},root,store,MediaRegistry(store,[root]))
    assert 'instrument-analysis' not in result['documents']
    assert result['documents']['unverified_sidecars']['sources']['instrument-analysis']=={'track_id':'track1','bars':[]}
