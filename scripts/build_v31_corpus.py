#!/usr/bin/env python3
"""Build a report-bound listening corpus; no cross-track audio is rendered here."""
import argparse,copy,hashlib,json,statistics,subprocess,sys
from pathlib import Path
from build_auto_protected import candidates
from build_protected_assets import grid,merged
from build_decision_evidence import attach

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def select(rows,seed_ids,count=20):
 valid=[r for r in rows if r.get('eligible')]
 chosen=[r for i in seed_ids for r in valid if r['track_id']==i]
 if len(chosen)!=len(seed_ids):raise ValueError('Frozen seed unavailable')
 # Maximise diversity in measured tempo/vocal density, with a small style novelty term.
 # Feasible transitions are deliberately absent from this selection function.
 while len(chosen)<count:
  rest=[r for r in valid if r['sha'] not in {x['sha'] for x in chosen}]
  if not rest:raise ValueError(f'Only {len(chosen)} eligible unique tracks')
  def distance(r):
   return min(abs(r['bpm']-x['bpm'])/80+abs(r['vocalCoverage']-x['vocalCoverage']) for x in chosen)+(.2 if r['style'][0]['style'] not in {x['style'][0]['style'] for x in chosen} else 0)
  chosen.append(sorted(rest,key=lambda r:(-distance(r),r['track_id']))[0])
 return chosen

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--job',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--static',type=Path,required=True);ap.add_argument('--reports',type=Path,required=True);ap.add_argument('--nas',type=Path,required=True);ap.add_argument('--plan-only',action='store_true');args=ap.parse_args()
 job,out=args.job,args.out;out.mkdir(parents=True,exist_ok=True);(out/'media').mkdir(exist_ok=True)
 public='/analysis-lab-static/'+out.name+'/'
 frozen=json.loads((job/'v3-catalog.json').read_text());auto=json.loads((job/'auto-catalog.json').read_text());seeds={t['id']:t for t in frozen['tracks']};seed_auto={t['id']:t for t in auto['tracks']}
 rows=json.loads((job/'inventory.json').read_text())['rows'];reports={};prepared={}
 for row in rows:
  row['eligible']=False;row['exclusion']=None
  if not row['style'] or not(row['style'][0]['parent']=='Hip Hop' or row['style'][0]['style'] in ['Trap','Grime']):row['exclusion']='不属于本次模型风格候选范围';continue
  try:
   rp=job/'reports'/(row['id']+'.json') if row['track_id'] in seeds else args.reports/(row['id']+'.json')
   raw=rp.read_bytes();r=json.loads(raw);c=r['documents']['core'];a=c['analysis'];master=c['assets']['master'];va=r['documents']['vocal_activity'];signals=r['extensions']['dj_signals']['data']
   assert va['status']=='ready' and va['source']['track_id']==c['track_id'] and va['source']['analysis_run_id']==c['analysis_run_id'] and va['source']['vocal_sha256']==c['assets']['stems']['vocals']['sha256'],'人声绑定缺失'
   assert master['sha256']==row['sha'] and r['id']==row['id'],'音频标识不一致'
   duration=min(150,master['duration_ms']/1000);bars=[x/1000 for x in a['beat_grid']['bars_ms'] if x/1000<duration];bpm=a['tempo']['bpm']
   assert len(bars)>4 and abs(240/statistics.median([y-x for x,y in zip(bars,bars[1:])])/bpm-1)<.05,'拍网格与速度不一致'
   source=(args.nas/master['storage_key']).resolve();assert source.is_relative_to(args.nas.resolve()) and source.is_file(),'源文件不存在'
   assert sha(source)==master['sha256'],'源文件指纹不符'
   tid=c['track_id'];top=row['style'][0]
   t=copy.deepcopy(seeds[tid]) if tid in seeds else dict(id=tid,title=r['title'],bpm=bpm,duration=duration,style=top['style'],styleScore=top['score'],bars=bars,sections=[dict(start=x['start_ms']/1000,end=x['end_ms']/1000,label=x['label']) for x in a['sections']['items']],vocals=[[x['start_ms']/1000,x['end_ms']/1000] for x in va['intervals']],energy=[dict(start=x['start_ms']/1000,end=x['end_ms']/1000,value=x['value']) for x in a['energy']['curve']],windows=[],warnings=['模型段落、拍网格均非人工真值']+(['BPM 待确认'] if a['tempo'].get('needs_review') else []),reportId=r['id'],provenance=dict(masterSha256=master['sha256'],reportSha256=hashlib.sha256(raw).hexdigest(),runId=c['analysis_run_id'],sectionSource=a['sections']['source'],vocalSha256=c['assets']['stems']['vocals']['sha256']))
   g=copy.deepcopy(seed_auto[tid]) if tid in seed_auto else copy.deepcopy(t)
   if tid not in seed_auto:g['sections']=merged(g['sections']);g['bars']=grid([x/1000 for x in a['beat_grid']['beats_ms']],bars,duration)
   ev=candidates(g,signals);prepared[tid]=(t,g,ev,source);reports[r['id']]=(raw,r);row['eligible']=True
  except (KeyError,TypeError,ValueError,AssertionError,OSError) as e:row['exclusion']=str(e) or type(e).__name__
 chosen=select(rows,list(seeds));selected={r['track_id'] for r in chosen}
 audit=dict(schema='harbeat.v31.corpus-selection.v1',selection='原六首 + BPM/人声密度/模型风格差异；未以可混成功率筛选',previewLimitSec=150,rows=[{k:r.get(k) for k in ['title','track_id','sha','bpm','vocalCoverage','style','eligible','exclusion']}|{'selected':r['track_id'] in selected} for r in rows],selectedCount=len(chosen))
 (out/'corpus-audit.json').write_text(json.dumps(audit,ensure_ascii=False))
 baselines=[];guards=[];evidence={};sources={}
 def ordinary_windows(t):
  bars=t['bars'];starts={0}
  for s in t['sections']:
   i=min(range(len(bars)),key=lambda i:abs(bars[i]-s['start']))
   if bars[i]<90:starts.add(i)
  return [dict(id=f'w{i}-{n}',start=bars[i],end=bars[i+n],bars=n,role=next((s['label'] for s in t['sections'] if s['start']<=bars[i]<s['end']),'unclassified'),energy=0,variants={}) for i in sorted(starts)[:4] for n in [2,4] if i+n<len(bars) and bars[i+n]+12<=t['duration']]
 for row in chosen:
  t,g,ev,source=prepared[row['track_id']];baselines.append(t);guards.append(g);evidence[t['id']]=ev;sources[t['id']]=source
  if t['id'] not in seeds:
   t['windows']=ordinary_windows(t)
   for w in t['windows']:
    weighted=[(max(0,min(min(t['duration'],w['end']+16),x['end'])-max(w['end'],x['start'])),x['value']) for x in t['energy']]
    denominator=sum(length for length,value in weighted)
    w['energy']=sum(length*value for length,value in weighted)/denominator if denominator else 0
  if t['id'] not in seed_auto:g['windows']=[{k:e[k] for k in ['start','end','bars','role']}|dict(id=wid,energy=0,variants={}) for wid,e in ev['windows'].items()]
 count=sum(1 for group in [baselines,guards] for b in group for w in b['windows'] for a in group if b['id']!=a['id'] and a['id'] not in w['variants'] and .8<=(w['end']-w['start'])/(w['bars']*240/a['bpm'])<=1.2)
 print('PLAN',len(chosen),'tracks',count,'new variants',[(t['title'],len(t['windows']),len(evidence[t['id']]['exits'])) for t in guards],flush=True)
 if args.plan_only:return
 commands=[];source_shas={}
 def encode(source,filter):
  
  if str(source) not in source_shas:source_shas[str(source)]=sha(source)
  recipe=dict(sourceSha256=source_shas[str(source)],filter=filter,format='flac-s16-stereo-44100-frame4096-v1');key=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest();dest=out/'media'/(key+'.flac');meta=dest.with_suffix('.json')
  if dest.exists() and meta.exists():
   cached=json.loads(meta.read_text())
   if sha(dest)==cached['sha256']:return cached
  
  import shutil
  if shutil.disk_usage(out).free<600*1024*1024:raise RuntimeError('剩余空间低于 600 MB，停止生成，保留既有版本')
  tmp=dest.with_suffix('.part.flac');subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(source),'-vn','-af',filter,'-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16','-frame_size','4096',str(tmp)],check=True,timeout=180);tmp.replace(dest)
  duration=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(dest)]))['format']['duration']);asset=dict(url=public+'media/'+dest.name,sha256=sha(dest),duration=duration,bytes=dest.stat().st_size,recipe=recipe);meta.write_text(json.dumps(asset));commands.append(recipe);return asset
 for t,g in zip(baselines,guards):
  if t['id'] not in seeds:t['native']=encode(sources[t['id']],f'atrim=end={t["duration"]:.6f},asetpts=PTS-STARTPTS');t['duration']=t['native']['duration'];g['native']=copy.deepcopy(t['native']);g['duration']=t['duration']
  native=args.static/t['native']['url'].removeprefix('/analysis-lab-static/');assert sha(native)==t['native']['sha256']
  for typ,b in [('v3',t),('protected',g)]:
   source=sources[t['id']] if typ=='v3' else native
   for w in b['windows']:
    for a in baselines:
     if a['id']==b['id'] or a['id'] in w['variants']:continue
     duration=w['bars']*240/a['bpm'];rate=(w['end']-w['start'])/duration
     if not .8<=rate<=1.2:continue
     precision=6 if typ=='v3' else 9
     filt=f'atrim=start={w["start"]:.{precision}f}:end={w["end"]:.{precision}f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
     asset=encode(source,filt);assert abs(asset['duration']-duration)<.00003;w['variants'][a['id']]=dict(asset,rate=rate)
  print('BUILT',t['title'],flush=True)
 for name,doc in [('v3-catalog.json',dict(schema='harbeat.v31.v3-reference.v1',tracks=baselines)),('auto-catalog.json',dict(schema='harbeat.protected.auto.v1',policy='acoustic-v1',tracks=guards,evidence=evidence))]:
  path=out/name;path.write_text(json.dumps(doc));attached=attach(path,reports,out,public,public+'evidence/');path.write_text(json.dumps(attached,ensure_ascii=False,separators=(',',':')))
 (out/'asset-build.json').write_text(json.dumps(dict(singleSongOnly=True,newRecipes=commands,ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0])))
 print('DONE',flush=True)
if __name__=='__main__':main()
