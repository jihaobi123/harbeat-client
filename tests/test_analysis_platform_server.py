from pathlib import Path
import json

from fastapi.testclient import TestClient


def test_upload_job_persists_sources_and_bad_origin_is_blocked(tmp_path):
    from analysis_platform.server import create_app
    with TestClient(create_app(tmp_path, run_workers=False), base_url='http://localhost') as client:
        response = client.post('/api/analysis-lab/import', json={'documents': {'core': {'bpm': 120, 'custom': [1, 2]}}})
        assert response.status_code == 200
        report = response.json()
        assert report['documents']['core']['custom'] == [1, 2]
        assert client.get('/api/analysis-lab/reports').json()[0]['id'] == report['id']
        assert client.get('/api/analysis-lab/reports/' + report['id']).json()['source_hashes'] == report['source_hashes']
        assert client.post('/api/analysis-lab/import', headers={'origin': 'https://evil.example'}, json={}).status_code == 403
        assert client.get('/api/analysis-lab/reports/../../etc/passwd').status_code == 404


def test_bad_json_and_audio_binding_do_not_publish(tmp_path):
    from analysis_platform.server import create_app
    with TestClient(create_app(tmp_path, run_workers=False), base_url='http://localhost') as client:
        assert client.post('/api/analysis-lab/import', json={'documents': {}}).status_code == 422
        assert client.post('/api/analysis-lab/jobs', data={'report_id': 'missing'}, files={'audio': ('a.wav', b'bad', 'audio/wav')}).status_code == 422


def test_store_marks_interrupted_jobs_and_preserves_report(tmp_path):
    from analysis_platform.store import Store
    from analysis_platform.report import build_report
    store = Store(tmp_path)
    report = build_report({'core': {'key': 'Am'}}, {}, {})
    store.save_report(report)
    store.save_job({'id': 'a'*32, 'status': 'running'})
    store.recover()
    assert store.get_job('a'*32)['status'] == 'interrupted'
    assert store.get_report(report['id'])['documents']['core']['key'] == 'Am'


def test_relay_requires_secret_and_exact_origin(tmp_path, monkeypatch):
    from analysis_platform.server import create_app
    monkeypatch.setenv('ANALYSIS_RELAY_TOKEN', 'test-' + 'a'*40)
    monkeypatch.setenv('ANALYSIS_PUBLIC_ORIGIN', 'https://analysis.example.com')
    with TestClient(create_app(tmp_path), base_url='https://analysis.example.com') as client:
        assert client.get('/api/analysis-lab/reports').status_code == 401
        headers={'x-analysis-relay-token':'test-'+'a'*40}
        assert client.get('/api/analysis-lab/reports',headers=headers).status_code == 200
        assert client.post('/api/analysis-lab/import',headers={**headers,'origin':'https://analysis.example.com.evil.test'},json={}).status_code == 403
        raw={'bpm':120,'unknown':[None,1]}
        response=client.post('/api/analysis-lab/import',headers={**headers,'origin':'https://analysis.example.com'},json={'documents':{'core':raw},'audio':{'name':'original title'}})
        assert response.status_code == 200
        assert response.json()['documents']['core'] == raw
        assert response.json()['title'] == 'original title'


def test_uploaded_audio_is_verified_and_cannot_replace_bound_audio(tmp_path):
    import hashlib,io
    import numpy as np
    import soundfile as sf
    from analysis_platform.server import create_app
    audio=io.BytesIO();sf.write(audio,np.zeros(16000),16000,format='WAV');blob=audio.getvalue()
    sha=hashlib.sha256(blob).hexdigest()
    with TestClient(create_app(tmp_path,run_workers=False),base_url='http://localhost') as client:
        report=client.post('/api/analysis-lab/import',json={'documents':{'core':{'audio_sha256':sha,'duration':1}}}).json()
        job=client.post('/api/analysis-lab/jobs',data={'report_id':report['id']},files={'audio':('real.wav',blob,'audio/wav')})
        assert job.status_code == 200
        assert job.json()['audio']['binding'] == 'hash_verified'
        assert client.get('/api/analysis-lab/audio/'+sha).content == blob
        rerun=client.post('/api/analysis-lab/reports/'+report['id']+'/rerun')
        assert rerun.status_code == 200 and rerun.json()['audio']['sha256'] == sha
        report2=client.post('/api/analysis-lab/import',json={'documents':{'core':{'audio_sha256':'b'*64,'duration':1}}}).json()
        assert client.post('/api/analysis-lab/jobs',data={'report_id':report2['id']},files={'audio':('other.wav',blob,'audio/wav')}).status_code == 422


def test_remote_status_is_authenticated_and_identifies_execution_host(tmp_path, monkeypatch):
    from analysis_platform.server import create_app
    monkeypatch.setenv('ANALYSIS_RELAY_TOKEN', 's'*40)
    with TestClient(create_app(tmp_path), base_url='http://localhost') as client:
        assert client.get('/api/analysis-lab/status').status_code == 401
        result = client.get('/api/analysis-lab/status', headers={'x-analysis-relay-token':'s'*40})
        assert result.status_code == 200
        assert result.json()['execution_host']
        from analysis_platform.runner import MODULES
        assert result.json()['modules'] == list(MODULES)
        assert result.json()['storage_available_bytes'] > 0


def test_coverage_refreshes_after_manual_result_import(tmp_path):
    from analysis_platform.server import create_app
    (tmp_path/'backfill-status.json').write_text(json.dumps({'status':'completed','coverage':{'tracks':0},'errors':[]}))
    with TestClient(create_app(tmp_path,run_workers=False),base_url='http://localhost') as client:
        url='/api/analysis-lab'
        client.post(url+'/import',json={'documents':{'core':{}},'audio':{'catalog_track_id':'one'}})
        assert client.get(url+'/coverage').json()['coverage']['modules']['chords']['missing']==1
        client.post(url+'/import',json={'documents':{'core':{}},'audio':{'catalog_track_id':'one'},'extensions':{'chords':{'status':'ready','data':{}}}})
        assert client.get(url+'/coverage').json()['coverage']['modules']['chords']['ready']==1
