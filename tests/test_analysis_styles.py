import numpy as np
import pytest
from analysis_platform.genre import summarize_genre
from analysis_platform.embedding_cache import cached_embedding


def test_raw_scores_weighted_by_patch_count_and_parent_max():
    result = summarize_genre(['Electronic---House','Electronic---Techno','Hip Hop'], [
        (0,30,np.array([[.8,.3,.2],[.6,.5,.4]])), (30,31,np.array([[.2,.1,.9]]))])
    assert [x['score'] for x in result['scores']] == pytest.approx([1.6/3,.9/3,1.5/3])
    assert result['parents'][0]['label'] == 'Electronic'
    assert result['parents'][0]['score'] == pytest.approx(1.6/3)
    assert len(result['segments']) == 2
    assert sum(x['score'] for x in result['scores']) != pytest.approx(1)


def test_bad_model_output_is_not_presented_as_genre():
    for scores in [np.array([[np.nan,.1]]), np.array([[1.2,.1]]), np.array([[.1]])]:
        with pytest.raises(ValueError): summarize_genre(['a','b'],[(0,30,scores)])


def test_embedding_cache_invalidates_and_recovers(tmp_path):
    calls=[]
    def compute(): calls.append(1); return np.ones((2,1280),dtype=np.float32)
    a,hit=cached_embedding(tmp_path,{'audio':'a','protocol':'v1'},compute)
    assert not hit
    assert cached_embedding(tmp_path,{'audio':'a','protocol':'v1'},compute)[1]
    assert not cached_embedding(tmp_path,{'audio':'b','protocol':'v1'},compute)[1]
    for path in tmp_path.glob('*.npy'):path.write_bytes(b'broken')
    assert not cached_embedding(tmp_path,{'audio':'a','protocol':'v1'},compute)[1]
    assert len(calls)==3


def test_style_provenance_excludes_reference_and_recognizes_old_manual():
    from analysis_platform.styles import evidence
    from analysis_platform.report import build_report
    r=build_report({'core':{'genre_profile':{'manual_primary_style':'hiphop','genres':[{'name':'hiphop','confidence':1,'source':'manual'}]},'dance_style_scores':{'house':72}},
        'unverified_sidecars':{'status':'reference_only','genre_profile':{'method':'audio_features','primary_genre':'jazz'}}})
    e=evidence(r)
    assert len(e['manual'])==1 and e['manual'][0]['labels']==['hiphop']
    assert e['rules']==[] and len(e['dance'])==1
    assert r['documents']['core']['genre_profile']['genres'][0]['confidence']==1


def test_human_review_persists_across_versions_and_rejects_stale_write(tmp_path):
    from analysis_platform.styles import review, save_review, ReviewConflict
    from analysis_platform.report import build_report
    from analysis_platform.store import Store
    s=Store(tmp_path)
    r=build_report({'core':{'bpm':100}},audio={'sha256':'a'*64})
    new=build_report(r['documents'],{'genre':{'status':'ready','data':{}}},r['audio'])
    assert review(s,r)['revision']==0
    saved=save_review(s,r,{'expected_revision':0,'labels':['Hip Hop---Boom Bap'],'status':'confirmed','note':'听完确认'})
    assert review(s,new)==saved
    with pytest.raises(ReviewConflict):save_review(s,new,{'expected_revision':0,'labels':['House'],'status':'confirmed'})
    with pytest.raises(ValueError):save_review(s,new,{'expected_revision':1,'labels':[],'status':'confirmed'})
    assert review(s,new)['revision']==1


def test_selected_module_preserves_extensions(tmp_path, monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from analysis_platform.server import create_app
    from analysis_platform.store import Store
    def run(*args, **kwargs):
        assert kwargs['modules']==['genre']
        return {'genre':{'status':'ready','data':{'top':[]}}}
    monkeypatch.setattr('analysis_platform.server.run_modules',run)
    import hashlib
    sha=hashlib.sha256(b'fake').hexdigest()
    s=Store(tmp_path);s.path('audio',sha,'.audio').write_bytes(b'fake')
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        r=c.post('/api/analysis-lab/import',json={'documents':{'core':{'custom':[1,2]}},'extensions':{'emotion':{'status':'ready','data':{'keep':42}}},'audio':{'sha256':sha}}).json()
        job=c.post('/api/analysis-lab/reports/'+r['id']+'/modules/genre').json()
        for _ in range(50):
            j=c.get('/api/analysis-lab/jobs/'+job['id']).json()
            if j['status']=='completed':break
            time.sleep(.01)
        new=c.get('/api/analysis-lab/reports/'+j['report_id']).json()
        assert new['extensions']['emotion']==r['extensions']['emotion']
        assert new['source_hashes']==r['source_hashes']
        assert c.post('/api/analysis-lab/reports/'+r['id']+'/modules/anything').status_code==422
        saved=c.post('/api/analysis-lab/reports/'+r['id']+'/style-review',json={'expected_revision':0,'labels':['House'],'status':'confirmed'})
        assert saved.status_code==200
        assert c.get('/api/analysis-lab/reports/'+new['id']+'/styles').json()['review']['revision']==1
        assert c.post('/api/analysis-lab/reports/'+new['id']+'/style-review',json={'expected_revision':0,'labels':['Jazz'],'status':'confirmed'}).status_code==409


def test_review_identity_alias_after_verified_upload_and_audit_asset_only(tmp_path):
    from analysis_platform.styles import review, save_review, bind_review_identity, audit
    from analysis_platform.report import build_report
    from analysis_platform.store import Store
    s=Store(tmp_path)
    r=build_report({'core':{'bpm':100}},audio={'assets':{'master':{'id':'b'*64}}})
    later=build_report(r['documents'],{'genre':{'status':'ready','data':{}}},r['audio'])
    s.save_report(r);s.save_report(later)
    assert audit(s)['coverage']['tracks']==1
    saved=save_review(s,r,{'expected_revision':0,'labels':['Folk, World, & Country---Country'],'status':'confirmed'})
    verified={**r['audio'],'sha256':'a'*64,'hash_verification':'verified'}
    bind_review_identity(s,r,verified)
    new=build_report(r['documents'],audio=verified)
    assert review(s,new)==saved and review(s,r)==saved
    s.save_report(new)
    assert audit(s)['coverage']['tracks']==1
    updated=save_review(s,new,{'expected_revision':1,'labels':['Country'],'status':'confirmed'})
    assert review(s,r)==updated


def test_spotify_merged_evidence_not_counted_as_audio_rules():
    from analysis_platform.styles import evidence
    from analysis_platform.report import build_report
    e=evidence(build_report({'core':{'genre_profile':{'method':'spotify_audio_merged','genres':[{'name':'house','confidence':1,'source':'spotify'}]}}}))
    assert len(e['metadata'])==1 and e['rules']==[]


def test_old_hashless_report_cannot_rebind_another_recording(tmp_path):
    from analysis_platform.styles import bind_review_identity, save_review, review
    from analysis_platform.report import build_report
    from analysis_platform.store import Store
    store=Store(tmp_path);r=build_report({'core':{'duration':3}})
    saved=save_review(store,r,{'expected_revision':0,'labels':['House'],'status':'confirmed'})
    bind_review_identity(store,r,{'sha256':'a'*64})
    with pytest.raises(ValueError):bind_review_identity(store,r,{'sha256':'b'*64})
    assert review(store,{**r,'audio':{'sha256':'a'*64}})==saved
    assert review(store,{**r,'audio':{'sha256':'b'*64}})['revision']==0


def test_source_refresh_preserves_same_audio_model_and_invalidates_changed_sections(tmp_path):
    from analysis_platform.extension_history import collect,restore
    from analysis_platform.report import build_report
    from analysis_platform.store import Store
    store=Store(tmp_path);sha='a'*64
    original=build_report({'core':{'title':'before','sections':[{'start':0,'end':30,'label':'verse'}]}},
        {'genre':{'status':'ready','data':{'audio_sha256':sha}},'repeat':{'status':'ready','data':{'keep':True}}},
        {'sha256':sha,'hash_verification':'verified'})
    store.save_report(original)
    new=build_report({'core':{'title':'after','sections':[{'start':0,'end':15,'label':'intro'}]}},audio={'sha256':sha})
    restored=restore(new,collect(store))
    assert restored['extensions']['genre']==original['extensions']['genre']
    assert 'repeat' not in restored['extensions']
    assert restored['documents']==new['documents']
    other=build_report(new['documents'],audio={'sha256':'b'*64})
    assert restore(other,collect(store))['extensions']=={}


def test_catalog_does_not_carry_explicitly_conflicting_model_identity():
    from analysis_platform.extension_history import restore
    from analysis_platform.report import build_report
    sha='a'*64
    old=build_report({'core':{'title':'old'}},{'genre':{'status':'ready','data':{'audio_sha256':'b'*64}}}, {'sha256':sha,'hash_verification':'verified'})
    new=build_report({'core':{'title':'new'}},audio={'sha256':sha})
    assert restore(new,{sha:[old]})['extensions']=={}


def test_wrong_declared_audio_blocks_inference(tmp_path, monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from analysis_platform.server import create_app
    from analysis_platform.store import Store
    calls=[]
    monkeypatch.setattr('analysis_platform.server.run_modules',lambda *a,**k:calls.append(1))
    s=Store(tmp_path);s.path('audio','a'*64,'.audio').write_bytes(b'wrong audio')
    with TestClient(create_app(tmp_path),base_url='http://localhost') as c:
        r=c.post('/api/analysis-lab/import',json={'documents':{'core':{'title':'mismatch'}},'audio':{'sha256':'a'*64}}).json()
        j=c.post('/api/analysis-lab/reports/'+r['id']+'/modules/genre').json()
        for _ in range(50):
            j=c.get('/api/analysis-lab/jobs/'+j['id']).json()
            if j['status']=='failed':break
            time.sleep(.01)
        assert j['status']=='failed' and '指纹' in j['reason']
        assert not calls and len(c.get('/api/analysis-lab/reports').json())==1
