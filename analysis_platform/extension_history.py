"""Carry compatible supplemental results across source catalog refreshes."""
from .report import build_report


def collect(store):
    history={}
    for item in store.reports():
        sha=item.get('audio',{}).get('sha256')
        if not sha:continue
        old=store.get_report(item['id'])
        if old['extensions']:history.setdefault(sha,[]).append(old)
    return history


def restore(report, history):
    sha=report['audio'].get('sha256');extensions={};seen=set()
    for old in history.get(sha,[]) if sha else []:
        for name,value in old['extensions'].items():
            if name in seen:continue
            seen.add(name)
            data=value.get('data') or {}
            result_sha=data.get('audio_sha256')
            verified=(result_sha==sha) if result_sha else old['audio'].get('hash_verification')=='verified'
            if not verified:continue
            if name in ('repeat','measurements','emotion_summary') and old['timeline']['sections']!=report['timeline']['sections']:continue
            if name=='core_features' and old['timeline']!=report['timeline']:continue
            if name=='dj_signals' and old['audio'].get('assets',{}).get('vocals',{}).get('id')!=report['audio'].get('assets',{}).get('vocals',{}).get('id'):continue
            extensions[name]=value
    if 'emotion_summary' in extensions:
        from .report import digest
        if (extensions['emotion_summary'].get('data') or {}).get('source_emotion_sha256') != digest(extensions.get('emotion',{})):
            extensions.pop('emotion_summary')
    return build_report(report['documents'],extensions,report['audio']) if extensions else report


def merge_latest(store, source, incoming, audio):
    """Merge queued completions only when audio and original document hashes match."""
    merged=dict(source['extensions'])
    for item in store.reports():
        if item.get('audio',{}).get('sha256') != audio.get('sha256'):continue
        candidate=store.get_report(item['id'])
        if candidate['source_hashes']!=source['source_hashes']:continue
        merged.update(candidate['extensions']);break
    merged.update(incoming)
    signal=merged.get('dj_signals',{}).get('data') or {}
    measured=signal.get('vocal_asset_id',(signal.get('vocals',{}).get('asset') or {}).get('id'))
    expected=audio.get('assets',{}).get('vocals',{}).get('id')
    if measured!=expected:merged.pop('dj_signals',None)
    if 'emotion_summary' in merged:
        from .report import digest
        summary=merged['emotion_summary']
        if summary.get('status')=='ready' and (summary.get('data') or {}).get('source_emotion_sha256')!=digest(merged.get('emotion',{})):
            merged.pop('emotion_summary')
    return merged
