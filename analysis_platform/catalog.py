"""Read existing producers; never mutate their DB, files, names or model output."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from .media import MediaRegistry
from .report import build_report
from .store import Store
from .extension_history import collect as collect_extensions, restore as restore_extensions
from .stems import attach_cached, cache_path, measure_stems


def read_document(path, expected_hash=None):
    raw = Path(path).read_bytes()
    if expected_hash and hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError('source file checksum mismatch: '+Path(path).name)
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('expected source object')
    return result


def below(root, relative):
    path = (Path(root)/relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('source reference escapes configured root')
    return path


def registered(registry, path, sha=None):
    try:
        return registry.register(path, sha)
    except (OSError, ValueError, RuntimeError) as exc:
        return {'status':'unavailable', 'reason':str(exc)}


def import_manifest(path, root, store, registry, expected_hash=None, related_documents=None, extension_history=None):
    doc = read_document(path, expected_hash)
    assets, source = {}, doc.get('source', {})
    raw_assets = doc.get('assets', {})
    entries = {'master':raw_assets.get('master', {})}
    entries.update(raw_assets.get('stems', {}))
    entries.update({'drum_'+k:v for k,v in raw_assets.get('drum_stems', {}).items() if isinstance(v,dict)})
    for name, entry in entries.items():
        if isinstance(entry,dict) and entry.get('storage_key'):
            assets[name] = registered(registry, below(root,entry['storage_key']),entry.get('sha256'))
    docs = {**(related_documents or {}), 'core':doc}
    track, run = doc.get('track_id'), doc.get('analysis_run_id')
    if track and run:
        pointer_path = below(root, f'published/vocal_activity/{track}/{run}/latest.json')
        if pointer_path.is_file():
            pointer = read_document(pointer_path)
            expected_manifest = pointer.get('manifest_sha256')
            if expected_manifest and expected_manifest != hashlib.sha256(Path(path).read_bytes()).hexdigest():
                docs['source_binding_notes'] = {'vocal_activity':'manifest checksum differs; not attached'}
            elif pointer.get('vocal_activity_storage_key'):
                docs['vocal_activity'] = read_document(below(root,pointer['vocal_activity_storage_key']),pointer.get('vocal_activity_sha256'))
    audio = {'name':source.get('title') or source.get('original_filename') or track,
             'duration':source.get('duration_ms',0)/1000, 'assets':assets,
             'binding':'published_manifest_reference', 'hash_verification':'source_declared', 'catalog_track_id':track,
             'sha256':source.get('input_sha256') or raw_assets.get('master',{}).get('sha256')}
    attach_cached(store,docs,assets)
    report = restore_extensions(build_report(docs, {}, audio), collect_extensions(store) if extension_history is None else extension_history)
    store.save_report(report)
    return report


def import_library(row, data_root, store, registry, extension_history=None):
    original = dict(row)
    source_path = original.pop('source_path', '')
    original.pop('user_id', None)
    original.pop('platform_url', None)
    docs = {'core':original}
    def resolve_path(path):
        p=Path(path)
        old='/home/mark/harbeat/data/music-files/'
        if not p.exists() and str(p).startswith(old):
            p=Path(data_root).parent/'music-files'/str(p)[len(old):]
        return p
    assets={'master':registered(registry,resolve_path(source_path),row.get('original_sha256'))} if source_path else {}
    for name,path in (row.get('stems') or {}).items():
        if isinstance(path,str):assets[name]=registered(registry,resolve_path(path),(row.get('stems_sha256') or {}).get(name))
    sha=row.get('original_sha256')
    # Sidecars may promote their hash to report identity. If the DB has no input
    # hash, verify the actual master before accepting any sidecar on this track.
    if not sha and assets.get('master',{}).get('id'):
        sha=registry.verify(assets['master']['id'])
    # Newer sidecars carry full input hashes. Never attach a mismatched recording.
    notes={};unverified={}
    for name in ['songformer-sections','edm-structure','instrument-analysis']:
        path=below(data_root,str(name)+'/'+str(row['id'])+'.json')
        if not path.is_file():continue
        sidecar=read_document(path)
        side_hash=sidecar.get('audio_sha256') or sidecar.get('audio_fingerprint')
        if not sha or not side_hash:
            notes[name]='原曲或独立结果缺少可核验指纹，仅作历史参考';unverified[name]=sidecar;continue
        if sha and side_hash and not sha.startswith(side_hash):
            notes[name]='音频指纹不一致，仅作历史参考';unverified[name]=sidecar;continue
        if sidecar.get('track_id')!=row['id']:
            notes[name]='曲目 ID 不一致，未合并';continue
        docs[name]=sidecar
    if notes:docs['source_binding_notes']=notes
    if unverified:docs['unverified_sidecars']={'status':'reference_only','note':'这些结果未通过同曲指纹核验，不用于当前分析的时间轴或准确率评估','sources':unverified}
    archives=[]
    for path in (Path(data_root)/'bar-annotations').rglob(str(row['id'])+'.json'):
        archive=read_document(path)
        if archive.get('track_id')==row['id']:archives.append(archive)
    if archives:
        docs['historical_annotations']={'status':'reference_only',
            'note':'历史人工标注，保留原始版本和时间轴指纹；未校验当前时间轴，不自动用作准确率评估',
            'sets':archives}
    audio={'name':row.get('title'), 'duration':row.get('duration'), 'assets':assets,
           'binding':'library_record_reference', 'hash_verification':'source_declared', 'catalog_track_id':str(row['id'])}
    if sha:audio['sha256']=sha
    attach_cached(store,docs,assets)
    report=restore_extensions(build_report(docs,{},audio), collect_extensions(store) if extension_history is None else extension_history);store.save_report(report)
    return report


def sync_catalog(store, registry, nas_root, library_snapshot=None, progress=None):
    nas_root=Path(nas_root);reports=[];errors=[]
    pointers=sorted((nas_root/'preprocess/published/tracks').glob('*/latest.json'))
    library=[]
    if library_snapshot and Path(library_snapshot).is_file():
        library=json.loads(Path(library_snapshot).read_text())
    total=len(pointers)+len(library); by_hash={}
    extension_history=collect_extensions(store)
    for index, (kind,item) in enumerate([('library',r) for r in library]+[('nas',p) for p in pointers]):
        if progress:progress(index,total)
        try:
            if kind=='nas':
                pointer=read_document(item)
                manifest_path=below(nas_root/'preprocess',pointer['manifest_storage_key'])
                manifest=read_document(manifest_path,pointer.get('manifest_sha256'))
                related=by_hash.get(manifest.get('source',{}).get('input_sha256'),{})
                report=import_manifest(manifest_path,nas_root/'preprocess',store,registry,pointer.get('manifest_sha256'),related,extension_history)
            else:
                report=import_library(item,nas_root/'data',store,registry,extension_history)
                if report['audio'].get('sha256'):
                    by_hash[report['audio']['sha256']]={('library' if k=='core' else k):v for k,v in report['documents'].items() if k!='separated_stem_activity'}
            reports.append(report['id'])
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            errors.append({'source':str(item) if kind=='nas' else item.get('id'), 'reason':str(exc)})
    result={'status':'completed' if not errors else 'completed_with_errors','total':total,'imported':len(reports),
            'report_ids':reports,'errors':errors,'updated_at':datetime.now(timezone.utc).isoformat()}
    store.write(store.root/'catalog-status.json',result)
    if progress:progress(total,total)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--nas-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--library-snapshot',type=Path)
    parser.add_argument('--measure-stems', action='store_true')
    args=parser.parse_args();store=Store(args.output)
    result=sync_catalog(store,MediaRegistry(store,[args.nas_root]),args.nas_root,args.library_snapshot,
                        progress=lambda n,total:print(f'{n}/{total}',flush=True) if n%20==0 else None)
    print(json.dumps({k:v for k,v in result.items() if k!='report_ids'},ensure_ascii=False))
    if args.measure_stems:
        registry=MediaRegistry(store,[args.nas_root])
        measurement={'status':'running','total':len(result['report_ids']),'processed':0,'measured':0,'unavailable':0,'errors':[]}
        def checkpoint(**values):
            measurement.update(values,updated_at=datetime.now(timezone.utc).isoformat())
            store.write(store.root/'catalog-measurement.json',measurement)
        for i,identifier in enumerate(result['report_ids']):
            report=store.get_report(identifier);assets=report['audio'].get('assets',{})
            checkpoint(processed=i,current_title=report['title'],current_stem=None)
            if not any(assets.get(n,{}).get('id') for n in ('vocals','drums','bass','other')):
                measurement['unavailable']+=1;continue
            try:
                path=cache_path(store,assets)
                if not path.is_file():store.write(path,measure_stems(assets,registry,on_progress=lambda name:checkpoint(current_stem=name)))
                docs=report['documents'];attach_cached(store,docs,assets)
                enriched=build_report(docs,report['extensions'],report['audio']);store.save_report(enriched)
                measurement['measured']+=1
                print(json.dumps({'measured':i+1,'total':len(result['report_ids']),'report_id':enriched['id'],'title':enriched['title']},ensure_ascii=False),flush=True)
            except (OSError,ValueError,RuntimeError) as exc:
                measurement['errors'].append({'title':report['title'],'reason':str(exc)})
                print(json.dumps({'title':report['title'],'stem_error':str(exc)},ensure_ascii=False),flush=True)
        checkpoint(status='completed',processed=len(result['report_ids']),current_title=None,current_stem=None)


if __name__=='__main__':main()
