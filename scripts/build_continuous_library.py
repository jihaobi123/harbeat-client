#!/usr/bin/env python3
"""Source-bound full-song library, immutable NAS assets, resumable batched encoding.

The accepted entry-window/atempo recipe is retained. Collection and human style
labels are never substituted for model style. Every indexed song stays visible.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FORMAT = 'flac-s16-stereo-44100-frame4096-v1'
SR = 44100

def file_sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def atomic_json(path, value, compressed=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
    temp=path.with_name(path.name+'.part');temp.write_bytes(data);temp.replace(path)
    if compressed:
        temp=path.with_name(path.name+'.gz.part');temp.write_bytes(gzip.compress(data,mtime=0));temp.replace(path.with_name(path.name+'.gz'))

def segment_bounds(frames, sample_rate=SR):
    if not isinstance(frames,int) or frames<=0 or sample_rate<=0:raise ValueError('invalid sample duration')
    rows=[];start=0;end=min(frames,150*sample_rate)
    while start<frames:
        rows.append((start,end));start=end;end=min(frames,end+30*sample_rate)
    return rows

def report_candidates(item, manifest, index):
    master=manifest['assets']['master']['sha256']
    return sorted((row for row in index.values() if row.get('audio',{}).get('sha256')==master and
                   row.get('audio',{}).get('catalog_track_id')==item['track_id']),
                  key=lambda row:(row.get('created_at',''),row['id']),reverse=True)

def bind_core(item, manifest, core):
    if core['track_id']!=item['track_id'] or core['track_id']!=manifest['track_id']:raise ValueError('track binding mismatch')
    if core['analysis_run_id']!=item['analysis_run_id'] or core['analysis_run_id']!=manifest['analysis_run_id']:raise ValueError('analysis run binding mismatch')
    if core['assets']['master']['sha256']!=manifest['assets']['master']['sha256']:raise ValueError('master binding mismatch')
    if core.get('analysis')!=manifest.get('analysis'):raise ValueError('canonical analysis differs from indexed manifest')

def entry_windows(track):
    from scripts.build_vocal_overlap_corpus import ordinary_windows
    limited={**track,'duration':min(track['duration'],track.get('nativeDuration',150))}
    return ordinary_windows(limited)

def variant_recipe(source_sha, window, a_bpm):
    duration=window['bars']*240/a_bpm;rate=(window['end']-window['start'])/duration
    if not .8<=rate<=1.2:return None
    filt=f'atrim=start={window["start"]:.6f}:end={window["end"]:.6f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
    return dict(sourceSha256=source_sha,filter=filt,format=FORMAT)

def recipe_key(recipe):return hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest()

def cached_asset(path,recipe):
    path=Path(path);meta=path.with_suffix('.json')
    try:
        value=json.loads(meta.read_text())
        if value.get('recipe')!=recipe or path.stat().st_size!=value['bytes'] or file_sha(path)!=value['sha256']:return None
        if not isinstance(value.get('duration'),(int,float)) or value['duration']<=0:return None
        return value
    except (OSError,ValueError,KeyError):return None

def library_index(items,tracks,failures,detail_base,prepared=None):
    rows=[]
    for item in items:
        completed=tracks.get(item['track_id'])
        track=completed or (prepared or {}).get(item['track_id'])
        row=dict(id=item['track_id'],title=item['title'],bpm=track.get('bpm') if track else None,
                 duration=track.get('duration') if track else None,style=(track.get('style') if not track.get('style','').startswith('unknown:') else None) if track else None,
                 collection=item['source_collection'],styleLabels=item.get('style_labels',[]),
                 detailUrl=detail_base+item['track_id']+'.json' if completed else None,
                 mixStatus=completed.get('mixStatus','unavailable') if completed and completed.get('playStatus')=='ready' else 'unavailable',
                 playStatus=completed.get('playStatus','unavailable') if completed else 'unavailable')
        reason=failures.get(item['track_id']) or (track or {}).get('reason')
        if reason:row['reason']=reason
        rows.append(row)
    return dict(schema='harbeat.continuous-library.v1',tracks=rows,coverage=dict(indexed=len(items),
                playable=sum(r['playStatus']=='ready' for r in rows),mixReady=sum(r['mixStatus']=='ready' for r in rows),
                unavailable=sum(r['playStatus']!='ready' for r in rows),mixUnavailable=sum(r['mixStatus']!='ready' for r in rows),collections=dict(Counter(r['collection'] for r in rows))))

def prepare_track(item,manifest,raw,report,nas,out,public,verify=True):
    from scripts.build_decision_evidence import attach
    from analysis_platform.phrase_alignment import analyze_alignment
    core=report['documents']['core'];bind_core(item,manifest,core)
    master=core['assets']['master'];source=(nas/master['storage_key']).resolve()
    if not source.is_relative_to(nas.resolve()) or not source.is_file():raise ValueError('published master missing or outside source root')
    if verify and file_sha(source)!=master['sha256']:raise ValueError('master SHA mismatch')
    analysis=core['analysis'];vad=report['documents']['vocal_activity']
    extensions=report.get('extensions') or {}
    signals=(extensions.get('dj_signals') or {}).get('data') or {}
    genre=(extensions.get('genre') or {}).get('data') or {}
    top=(genre.get('top') or [{}])[0]
    measured=signals.get('duration') or report.get('audio',{}).get('assets',{}).get('master',{}).get('duration')
    declared=master['duration_ms']/1000
    if not isinstance(measured,(int,float)) or abs(measured-declared)>.05:raise ValueError('measured source duration missing or disagrees with master')
    duration=measured
    track=dict(id=item['track_id'],title=item['title'],bpm=analysis['tempo']['bpm'],duration=duration,
               style=top.get('style') or ('unknown:'+item['track_id']),styleScore=top.get('score',0),collection=item['source_collection'],
               styleLabels=item.get('style_labels',[]),native={'url':public+'pending.flac'},nativeDuration=min(150,duration),
               bars=[v/1000 for v in analysis['beat_grid']['bars_ms'] if v/1000<duration],
               sections=[dict(start=x['start_ms']/1000,end=x['end_ms']/1000,label=x['label']) for x in analysis['sections']['items']],
               vocals=[[x['start_ms']/1000,x['end_ms']/1000] for x in vad['intervals']],
               energy=[dict(start=x['start_ms']/1000,end=x['end_ms']/1000,value=x['value']) for x in analysis['energy']['curve']],
               windows=[],warnings=['模型段落、拍网格均非人工真值']+(['BPM 待确认'] if analysis['tempo'].get('needs_review') else []),
               reportId=report['id'],provenance=dict(masterSha256=master['sha256'],reportSha256=hashlib.sha256(raw).hexdigest(),
               runId=core['analysis_run_id'],sectionSource=analysis['sections']['source'],vocalSha256=core['assets']['stems']['vocals']['sha256']),
               mixStatus='unavailable',playStatus='unavailable')
    reasons=[]
    if len(track['bars'])<5:reasons.append('insufficient observed bars')
    elif abs(240/statistics.median([y-x for x,y in zip(track['bars'],track['bars'][1:])])/track['bpm']-1)>=.05:reasons.append('beat grid and tempo disagree')
    if vad.get('status')!='ready' or vad.get('unit')!='ms' or vad.get('time_origin')!='master_audio_start':reasons.append('VAD not ready or time origin mismatch')
    if any(vad.get('source',{}).get(k)!=v for k,v in [('track_id',track['id']),('analysis_run_id',core['analysis_run_id']),('vocal_sha256',track['provenance']['vocalSha256'])]):reasons.append('VAD source binding mismatch')
    if genre and genre.get('audio_sha256')!=master['sha256']:reasons.append('model genre source binding mismatch')
    temp=out/'scratch'/(track['id']+'.json');atomic_json(temp,{'tracks':[track]})
    track=attach(temp,{report['id']:(raw,report)},out,public,public+'evidence/')['tracks'][0]
    temp.unlink()
    track['alignment']=analyze_alignment(track,signals)
    if track['alignment']['status']!='candidate' or not track['alignment'].get('bandFrames'):
        reasons.append('dynamic EQ alignment unavailable: '+'; '.join(track['alignment'].get('limitations',[])[-1:]))
    if not reasons:
        track['windows']=entry_windows(track)
        if not track['windows']:reasons.append('no complete ordinary entry window')
    for window in track['windows']:
        weights=[(max(0,min(min(track['nativeDuration'],window['end']+16),v['end'])-max(window['end'],v['start'])),v['value']) for v in track['energy']]
        denominator=sum(n for n,v in weights);window['energy']=sum(n*v for n,v in weights)/denominator if denominator else 0
    if reasons:track['reason']='; '.join(reasons)
    else:track['mixStatus']='ready'
    return track,source

class Renderer:
    def __init__(self,out,registry,reuse_roots=(),batch=24):
        self.out=out;self.registry=registry;self.batch=batch;self.reuse={};self.built=0;self.reused=0
        (out/'media').mkdir(parents=True,exist_ok=True)
        for root in reuse_roots:
            for meta in Path(root).glob('media/*.json'):
                try:
                    value=json.loads(meta.read_text());recipe=value['recipe'];key=recipe_key(recipe)
                    if meta.with_suffix('.flac').is_file():self.reuse[key]=meta.with_suffix('.flac')
                except (OSError,ValueError,KeyError):pass
    def asset(self,path,recipe):
        import soundfile as sf
        info=sf.info(path)
        if info.samplerate!=SR or info.channels!=2:raise ValueError('encoded format mismatch')
        sha=file_sha(path);public=self.registry.register(path,sha)
        # Registry records are atomic and reject changed size/mtime on reads.
        # The browser independently verifies these encoded bytes against SHA.
        return dict(url='/api/analysis-lab/media/'+public['id'],sha256=sha,duration=info.duration,bytes=path.stat().st_size,recipe=recipe)
    def render(self,source,recipes):
        result={};missing=[]
        for recipe in recipes:
            key=recipe_key(recipe)
            if key in result:continue
            path=self.out/'media'/(key+'.flac');value=cached_asset(path,recipe)
            if value is None and key in self.reuse:
                prior=self.reuse[key];value=cached_asset(prior,recipe)
                if value is not None:
                    value=self.asset(prior,recipe);self.reused+=1
            if value is not None:
                result[key]=value
            elif key not in {recipe_key(v) for v in missing}:missing.append(recipe)
        for at in range(0,len(missing),self.batch):
            chunk=missing[at:at+self.batch]
            labels=''.join(f'[in{i}]' for i in range(len(chunk)))
            graph=[f'[0:a]asplit={len(chunk)}'+labels]
            for i,recipe in enumerate(chunk):graph.append(f'[in{i}]'+recipe['filter']+f'[out{i}]')
            cmd=['ffmpeg','-nostdin','-y','-v','error','-threads','1','-i',str(source),'-filter_complex_threads','1','-filter_complex',';'.join(graph)]
            paths=[]
            for i,recipe in enumerate(chunk):
                path=self.out/'media'/(recipe_key(recipe)+'.part.flac');paths.append(path)
                cmd+=['-map',f'[out{i}]','-ar',str(SR),'-ac','2','-c:a','flac','-threads','1','-sample_fmt','s16','-frame_size','4096',str(path)]
            subprocess.run(cmd,check=True,timeout=600)
            for recipe,path in zip(chunk,paths):
                dest=path.with_name(path.name.replace('.part.flac','.flac'));path.replace(dest)
                value=self.asset(dest,recipe);atomic_json(dest.with_suffix('.json'),value)
                result[recipe_key(recipe)]=value;self.built+=1
        return result

def build_track(track,source,all_tracks,renderer,out):
    import soundfile as sf
    started=time.monotonic();track=copy.deepcopy(track)
    # Batch straight from the source. An intermediate PCM conversion changes
    # negotiation/rounding before atempo; each batch decodes once for 24 clips.
    info=sf.info(source)
    if info.samplerate!=SR or info.channels!=2:raise ValueError('source format requires dedicated resampling validation')
    if abs(info.duration-track['duration'])>.05:raise ValueError('decoded full duration disagrees with bound source analysis')
    track['duration']=info.duration;track['nativeDuration']=min(150,info.duration)
    sha=track['provenance']['masterSha256'];bounds=segment_bounds(info.frames,SR)
    native_recipes=[]
    for index,(start,end) in enumerate(bounds):
        filt=f'atrim=end={end/SR:.6f},asetpts=PTS-STARTPTS' if index==0 else f'atrim=start_sample={start}:end_sample={end},asetpts=PTS-STARTPTS'
        native_recipes.append(dict(sourceSha256=sha,filter=filt,format=FORMAT))
    assets=renderer.render(source,native_recipes)
    track['audioSegments']=[]
    for (start,end),recipe in zip(bounds,native_recipes):
        asset=assets[recipe_key(recipe)]
        if abs(asset['duration']-(end-start)/SR)>1/SR:raise ValueError('native segment sample duration mismatch')
        track['audioSegments'].append(dict(start=start/SR,end=end/SR,asset=asset))
    track['native']=track['audioSegments'][0]['asset'];track['playStatus']='ready'
    assignments=[];recipes=[]
    try:
        for window in track['windows']:
            for a in all_tracks:
                if a['id']==track['id']:continue
                recipe=variant_recipe(sha,window,a['bpm'])
                if recipe is None:continue
                recipes.append(recipe);assignments.append((window,a['id'],recipe,window['bars']*240/a['bpm']))
        entry_assets=renderer.render(source,recipes);assets.update(entry_assets)
        for window,a_id,recipe,duration in assignments:
            asset=assets[recipe_key(recipe)]
            if abs(asset['duration']-duration)>.00003:raise ValueError('entry variant duration mismatch')
            window['variants'][a_id]={**asset,'rate':(window['end']-window['start'])/duration}
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        track['mixStatus']='unavailable';track['reason']='entry rendering unavailable: '+str(exc)
        track['windows']=[]
    track.pop('nativeDuration',None)
    # Recipe text stays in immutable manifests, not every same-BPM reference.
    for segment in track['audioSegments']:segment['asset']={k:v for k,v in segment['asset'].items() if k!='recipe'}
    track['native']=track['audioSegments'][0]['asset']
    for window in track['windows']:
        window['variants']={k:{x:y for x,y in v.items() if x!='recipe'} for k,v in window['variants'].items()}
    atomic_json(out/'details'/(track['id']+'.json'),{'track':track},compressed=True)
    return track,dict(id=track['id'],seconds=round(time.monotonic()-started,3),uniqueRecipes=len(assets),segments=len(bounds),variantReferences=len(assignments),mixStatus=track['mixStatus'])

def main():
    p=argparse.ArgumentParser()
    for name in ('index','reports','report-index','nas','out','store'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--public',default='/analysis-lab-static/continuous-live-20260924/')
    p.add_argument('--reuse',action='append',type=Path,default=[])
    p.add_argument('--workers',type=int,default=4);p.add_argument('--batch',type=int,default=24)
    p.add_argument('--audit-only',action='store_true');p.add_argument('--benchmark',type=int,default=0)
    p.add_argument('--skip-source-hash',action='store_true')
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True);(args.out/'scratch').mkdir(exist_ok=True)
    items=json.loads(args.index.read_text())['items'];report_index=json.loads(args.report_index.read_text())
    if len({v['track_id'] for v in items})!=len(items):raise ValueError('duplicate indexed track identity')
    prepared={};sources={};failures={};audit=[]
    for item in items:
        try:
            manifest=json.loads((args.nas/item['manifest_storage_key']).read_text())
            candidates=report_candidates(item,manifest,report_index)
            if not candidates:raise ValueError('no source-matched report')
            rejected=[]
            for candidate in candidates:
                try:
                    raw=(args.reports/(candidate['id']+'.json')).read_bytes();report=json.loads(raw)
                    track,source=prepare_track(item,manifest,raw,report,args.nas,args.out,args.public,not args.skip_source_hash)
                    prepared[item['track_id']]=track;sources[item['track_id']]=source;break
                except (OSError,KeyError,TypeError,ValueError,AssertionError) as exc:rejected.append(str(exc))
            if item['track_id'] not in prepared:raise ValueError('; '.join(dict.fromkeys(rejected)))
            audit.append(dict(id=item['track_id'],title=item['title'],collection=item['source_collection'],mixStatus=track['mixStatus'],reason=track.get('reason'),reportId=track['reportId'],sourceSha256=track['provenance']['masterSha256'],duration=track['duration'],bpm=track['bpm'],windowCount=len(track['windows'])))
        except (OSError,KeyError,TypeError,ValueError,AssertionError) as exc:
            failures[item['track_id']]=str(exc);audit.append(dict(id=item['track_id'],title=item['title'],collection=item['source_collection'],mixStatus='unavailable',reason=str(exc)))
    all_tracks=list(prepared.values())
    recipe_count=sum(len({recipe_key(recipe) for window in b['windows'] for a in all_tracks if a['id']!=b['id'] for recipe in [variant_recipe(b['provenance']['masterSha256'],window,a['bpm'])] if recipe}) for b in all_tracks)
    manifest=dict(schema='harbeat.continuous-library-audit.v1',sourceIndexSha256=file_sha(args.index),rows=audit,indexed=len(items),prepared=len(prepared),mixReady=sum(t['mixStatus']=='ready' for t in all_tracks),sourceMixReady=sum(t['mixStatus']=='ready' for t in all_tracks),uniqueEntryRecipes=recipe_count,failures=failures)
    atomic_json(args.out/'corpus-audit.json',manifest)
    print('AUDIT',json.dumps({k:v for k,v in manifest.items() if k not in ('rows','failures')},ensure_ascii=False),flush=True)
    if args.audit_only:return
    from analysis_platform.media import MediaRegistry
    from analysis_platform.store import Store
    registry=MediaRegistry(Store(args.store),[args.nas.parent])
    renderer=Renderer(args.out,registry,args.reuse,args.batch)
    selected=all_tracks[:args.benchmark] if args.benchmark else all_tracks
    completed={};timings=[];start=time.monotonic()
    def run(track):return build_track(track,sources[track['id']],all_tracks,renderer,args.out)
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures={executor.submit(run,t):t for t in selected}
        for future in as_completed(futures):
            original=futures[future]
            try:
                track,timing=future.result();completed[track['id']]=track;timings.append(timing)
                print('BUILT',json.dumps(dict(title=track['title'],completed=len(completed),**timing),ensure_ascii=False),flush=True)
            except Exception as exc:
                failures[original['id']]=str(exc);print('FAILED',original['id'],str(exc),flush=True)
            atomic_json(args.out/'progress.json',dict(completed=len(completed),total=len(selected),failures=failures,built=renderer.built,reused=renderer.reused,seconds=time.monotonic()-start))
    for row in audit:
        track=completed.get(row['id'])
        if track:
            row.update(playStatus=track['playStatus'],mixStatus=track['mixStatus'],duration=track['duration'],reason=track.get('reason'))
        else:
            row.update(playStatus='unavailable',mixStatus='unavailable',reason=failures.get(row['id'],'assets not generated'))
    index=library_index(items,completed,failures,args.public+'details/',prepared=prepared)
    index['coverage'].update(uniqueAssetsBuilt=renderer.built,assetsReused=renderer.reused,uniqueEntryRecipes=recipe_count)
    manifest.update(coverage=index['coverage'],mixReady=index['coverage']['mixReady'],timings=timings,renderSeconds=round(time.monotonic()-start,3),benchmark=bool(args.benchmark),failures=failures)
    atomic_json(args.out/'library-index.json',index,compressed=True);atomic_json(args.out/'corpus-audit.json',manifest)
    print('DONE',json.dumps(index['coverage'],ensure_ascii=False),flush=True)
    if failures:sys.exit(2)

if __name__=='__main__':main()
