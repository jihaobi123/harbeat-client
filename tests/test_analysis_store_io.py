import errno,json,threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from analysis_platform.store import Store


def test_job_listing_retries_transient_smb_metadata_failure(tmp_path,monkeypatch):
    from pathlib import Path
    store=Store(tmp_path);identifier='c'*32
    store.save_job({'id':identifier,'status':'completed'})
    original=Path.stat;calls=[]
    def stat(path,*args,**kwargs):
        if path.name==identifier+'.json':
            calls.append(path)
            if len(calls)==1:raise FileNotFoundError(errno.ENOENT,'SMB delete pending')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'stat',stat)
    assert store.jobs()[0]['id']==identifier
    assert len(calls)==2


def test_short_smb_replace_denial_retries_same_staged_payload(tmp_path,monkeypatch):
    import analysis_platform.store as module
    store=Store(tmp_path);path=store.path('jobs','a'*32);store.write(path,{'status':'running'})
    original=module.os.replace;calls=[]
    def replace(src,dst):
        calls.append(src)
        if len(calls)==1:raise PermissionError(errno.EACCES,'SMB target temporarily open')
        return original(src,dst)
    monkeypatch.setattr(module.os,'replace',replace)
    store.write(path,{'status':'completed','payload':[1,2]})
    assert len(calls)==2 and calls[0]==calls[1]
    assert json.loads(path.read_text())['status']=='completed'


def test_permanent_replace_failure_keeps_recoverable_staged_result(tmp_path,monkeypatch):
    import analysis_platform.store as module
    store=Store(tmp_path);path=store.path('jobs','a'*32);store.write(path,{'status':'old'})
    def denied(*args):raise PermissionError(errno.EACCES,'still open')
    monkeypatch.setattr(module.os,'replace',denied)
    with pytest.raises(PermissionError):store.write(path,{'status':'computed'})
    staged=list(path.parent.glob('.write-*'))
    assert len(staged)==1 and json.loads(staged[0].read_text())=={'status':'computed'}


def test_job_reader_is_closed_before_same_store_replaces_record(tmp_path,monkeypatch):
    import analysis_platform.store as module
    from pathlib import Path
    store=Store(tmp_path);identifier='b'*32;store.save_job({'id':identifier,'status':'running'})
    read_started=threading.Event();release=threading.Event();replacing=threading.Event()
    old_read=Path.read_text;old_replace=module.os.replace
    def slow_read(p,*args,**kwargs):
        data=old_read(p,*args,**kwargs);read_started.set();release.wait(2);return data
    def replace(*args):replacing.set();return old_replace(*args)
    monkeypatch.setattr(Path,'read_text',slow_read);monkeypatch.setattr(module.os,'replace',replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader=pool.submit(store.get_job,identifier);assert read_started.wait(1)
        writer=pool.submit(store.save_job,{'id':identifier,'status':'completed'})
        try:assert not replacing.wait(.1),'writer must wait until reader closes'
        finally:release.set()
        reader.result();writer.result()


def test_slow_job_history_does_not_block_unrelated_song_read(tmp_path,monkeypatch):
    from pathlib import Path
    store=Store(tmp_path);jobid='d'*32;reportid='e'*64
    store.save_job({'id':jobid,'status':'completed'})
    reportpath=store.path('reports',reportid);store.write(reportpath,{'title':'available'})
    started=threading.Event();release=threading.Event();original=Path.read_text
    def slow(path,*args,**kwargs):
        if path.name==jobid+'.json':started.set();release.wait(2)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        history=pool.submit(store.jobs);assert started.wait(1)
        song=pool.submit(store.read,reportpath)
        try:assert song.result(timeout=.3)=={'title':'available'}
        finally:release.set()
        history.result()


def test_unchanged_job_history_reuses_summaries_and_refreshes_changes(tmp_path,monkeypatch):
    from pathlib import Path
    store=Store(tmp_path);jid='f'*32
    store.save_job({'id':jid,'status':'running','module_results':{'huge':'data'}})
    assert store.jobs()[0]['status']=='running'
    original=Path.read_text;reads=[]
    def observe(path,*args,**kwargs):reads.append(path);return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',observe)
    assert store.jobs()[0]['status']=='running'
    assert reads==[]
    store.save_job({'id':jid,'status':'completed'})
    assert store.jobs()[0]['status']=='completed'
