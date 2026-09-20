from analysis_platform.report import build_report
from analysis_platform.store import Store


def test_missing_only_selection_deduplicates_tracks_and_preserves_completed(tmp_path):
    from analysis_platform.coverage import latest_reports, missing_modules
    s=Store(tmp_path)
    a=build_report({'core':{'bpm':120}}, {}, {'catalog_track_id':'one','sha256':'a'*64})
    s.save_report(a)
    b=build_report(a['documents'],{'core_features':{'status':'ready','data':{}}},a['audio']);s.save_report(b)
    assert len(latest_reports(s))==1
    assert missing_modules(b,['core_features','chords'])==['chords']
    failed=build_report(a['documents'],{'chords':{'status':'failed','reason':'timeout'}},a['audio'])
    assert missing_modules(failed,['chords'])==['chords']


def test_refresh_does_not_reuse_section_measurements_after_boundaries_change():
    from analysis_platform.extension_history import restore
    old=build_report({'core':{'sections':[{'start':0,'end':4}]}},{'measurements':{'status':'ready','data':{'audio_sha256':'a'*64}}},{'sha256':'a'*64})
    new=build_report({'core':{'sections':[{'start':0,'end':2}]}},{},{'sha256':'a'*64})
    assert 'measurements' not in restore(new,{'a'*64:[old]})['extensions']


def test_emotion_summary_uses_new_emotion_not_old_curve():
    from analysis_platform.runner import run_modules
    def fresh(*args):return {'duration':2,'points':[{'start':0,'end':2,'valence':.8,'arousal':.7}]}
    from analysis_platform.emotion_summary import derive
    r=run_modules(None,{'summary':{'duration':2},'extensions':{'emotion':{'status':'failed'}}},{},implementations={'emotion':fresh,'emotion_summary':derive})
    assert r['emotion_summary']['status']=='ready'
    assert r['emotion_summary']['data']['valence_mean']==.8


def test_failed_emotion_summary_does_not_crash_catalog_refresh():
    from analysis_platform.extension_history import restore
    audio={'sha256':'b'*64,'hash_verification':'verified'}
    old=build_report({'core':{}},{'emotion_summary':{'status':'unavailable','data':None,'reason':'no curve'}},audio)
    new=build_report({'core':{}},{},audio)
    assert 'emotion_summary' not in restore(new,{'b'*64:[old]})['extensions']


def test_partial_core_failure_remains_pending():
    from analysis_platform.coverage import missing_modules
    r=build_report({'core':{}},{'core_features':{'status':'ready','data':{'timbre':{'status':'failed','data':None}}}})
    assert missing_modules(r,['core_features'])==['core_features']


def test_queued_results_merge_compatible_latest_extensions(tmp_path):
    from analysis_platform.extension_history import merge_latest
    s=Store(tmp_path);audio={'sha256':'c'*64,'catalog_track_id':'t'}
    original=build_report({'core':{'bpm':120}}, {}, audio);s.save_report(original)
    first=build_report(original['documents'],{'chords':{'status':'ready','data':{}}},audio);s.save_report(first)
    merged=merge_latest(s,original,{'measurements':{'status':'ready','data':{}}},audio)
    assert set(merged)=={'chords','measurements'}
    other=build_report({'core':{'bpm':60}},{'genre':{'status':'ready','data':{}}},audio);s.save_report(other)
    merged=merge_latest(s,original,{'measurements':{'status':'ready','data':{}}},audio)
    assert 'genre' not in merged


def test_batch_executes_missing_only_and_persists_coverage(tmp_path,monkeypatch):
    import json
    import analysis_platform.backfill as batch
    store=Store(tmp_path)
    source=build_report({'core':{'duration':1}},{'chords':{'status':'ready','data':{}}},{'catalog_track_id':'one','sha256':'d'*64})
    store.save_report(source);posts=[]
    class Response:
        status_code=200
        text=''
        def __init__(self,data):self.data=data
        def json(self):return self.data
        def raise_for_status(self):pass
    class Client:
        def __init__(self,*a,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,url):
            if url=='/jobs':return Response([])
            return Response(self.job)
        def post(self,url,json):
            posts.append(url);module=url.rsplit('/',1)[-1]
            report=build_report(source['documents'],{**source['extensions'],module:{'status':'ready','data':{}}},source['audio']);store.save_report(report)
            self.job={'id':'e'*32,'status':'completed','report_id':report['id'],'module_results':{module:{'status':'ready','data':{}}}}
            return Response(self.job)
    monkeypatch.setattr(batch.httpx,'Client',Client)
    batch.run(tmp_path,'http://localhost',[('test',['chords','measurements'])])
    state=json.loads((tmp_path/'backfill-status.json').read_text())
    assert len(posts)==1 and posts[0].endswith('/measurements')
    assert state['status']=='completed' and state['source_hash_changes']==[]
    assert state['coverage']['modules']['measurements']['ready']==1
