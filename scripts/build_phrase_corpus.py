#!/usr/bin/env python3
"""Add report-bound acoustic phrase evidence; never overwrite original reports/audio."""
import argparse,copy,hashlib,json,subprocess,sys,shutil,gzip
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis_platform.phrase_alignment import analyze_alignment

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def entry_windows(t):
 a=t['alignment'];bars=a['bars'];valid={round(v['start'],6):v for v in bars if v['valid']};times=sorted(set(x for v in bars if v['valid'] for x in [v['start'],v['end']]))
 out={}
 for phrase in a['phrases']:
  index=next((i for i,x in enumerate(times) if x>phrase['start']),len(times))-1
  for stop in [index,index+1]:
   for n in [1,2,4]:
    begin=stop-n
    if begin<0 or stop>=len(times):continue
    start,end=times[begin],times[stop]
    if start>phrase['start']-.02 or end+12>t['duration']:continue
    if any(round(times[j],6) not in valid or abs(valid[round(times[j],6)]['end']-times[j+1])>.001 for j in range(begin,stop)):continue
    if any(p['start']<start+.02 and p['tailEnd']>start for p in a['phrases']):continue
    section=next((s for s in t['sections'] if s['start']<=start+.001 and s['end']>=end-.001),None)
    if not section:continue
    wid=f'phrase-{begin}-{n}'
    out[wid]=dict(id=wid,start=start,end=end,bars=n,role=section['label'],energy=0,variants={},candidatePhraseId=phrase['id'])
 # Retain varied early/middle/late entries. The cap is resource policy, not a quality ranking.
 rows=sorted(out.values(),key=lambda x:(x['start'],x['bars']))
 if len(rows)>12:rows=[rows[round(i*(len(rows)-1)/11)] for i in range(12)]
 return rows

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,required=True);ap.add_argument('--reports',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--static',type=Path,required=True);ap.add_argument('--evidence-only',action='store_true');args=ap.parse_args()
 source=json.loads((args.base/'auto-catalog.json').read_text());baseline=json.loads((args.base/'v3-catalog.json').read_text());old={t['id']:t for t in baseline['tracks']};args.out.mkdir(parents=True,exist_ok=True);media=args.out/'media';media.mkdir(exist_ok=True)
 tracks=[];audit=[];public='/analysis-lab-static/'+args.out.name+'/'
 for original in source['tracks']:
  t=copy.deepcopy(original);rp=args.reports/(t['reportId']+'.json');assert sha(rp)==t['provenance']['reportSha256'],'report identity differs';r=json.loads(rp.read_text());signals=r['extensions']['dj_signals']['data'];t['alignment']=analyze_alignment(t,signals)
  # Preserve source analysis; only this derived catalog gets additional entries.
  t['windows']=copy.deepcopy(old[t['id']]['windows']);known={(round(w['start'],5),round(w['end'],5)) for w in t['windows']}
  t['windows'] += [w for w in entry_windows(t) if (round(w['start'],5),round(w['end'],5)) not in known]
  tracks.append(t);audit.append(dict(id=t['id'],title=t['title'],status=t['alignment']['status'],phrases=len(t['alignment']['phrases']),exits=len(t['alignment']['exits']),sectionExits=sum(x['sectionAligned'] for x in t['alignment']['exits']),windows=len(t['windows']),conflicts=len(t['alignment']['conflicts'])))
  print('EVIDENCE',audit[-1],flush=True)
 doc={'schema':'harbeat.phrase_catalog.v1','tracks':tracks,'audit':audit,'sourceCatalog':'../v31-candidate-20260923/auto-catalog.json','limitations':['声学候选不是歌词语义或人工真值','当前仍为原20首最多150秒试听素材','没有改变旧报告和旧音频']}
 (args.out/'catalog.json').write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':')))
 if args.evidence_only:return
 rendered=0
 for b in tracks:
  native=(args.static/b['native']['url'].removeprefix('/analysis-lab-static/')).resolve();assert native.is_relative_to(args.static.resolve()) and sha(native)==b['native']['sha256']
  for w in b['windows']:
   for a in tracks:
    if a['id']==b['id'] or a['id'] in w['variants']:continue
    duration=w['bars']*240/a['bpm'];rate=(w['end']-w['start'])/duration
    if not .8<=rate<=1.2:continue
    recipe={'source':b['native']['sha256'],'start':w['start'],'end':w['end'],'rate':rate,'duration':duration,'codec':'flac-s16-44100-v1'};key=hashlib.sha256(json.dumps(recipe,sort_keys=True).encode()).hexdigest();dest=media/(key+'.flac');meta=media/(key+'.json')
    if dest.exists() and meta.exists() and sha(dest)==json.loads(meta.read_text())['sha256']:asset=json.loads(meta.read_text())
    else:
     if shutil.disk_usage(media).free<900*1024*1024:raise RuntimeError('剩余空间低于900MB，保留旧版本并停止')
     filt=f'atrim=start={w["start"]:.9f}:end={w["end"]:.9f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={duration:.9f},atrim=end={duration:.9f}'
     tmp=dest.with_suffix('.part.flac');subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(native),'-af',filt,'-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16',str(tmp)],check=True,timeout=120);tmp.replace(dest)
     actual=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(dest)]))['format']['duration']);assert abs(actual-duration)<1/44100
     asset={'url':public+'media/'+dest.name,'sha256':sha(dest),'duration':actual,'bytes':dest.stat().st_size,'rate':rate,'recipe':recipe};meta.write_text(json.dumps(asset));rendered+=1
    w['variants'][a['id']]=asset
  print('ASSETS',b['title'],rendered,flush=True)
 (args.out/'catalog.json').write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':')))
 (args.out/'catalog.json.gz').write_bytes(gzip.compress((args.out/'catalog.json').read_bytes(),mtime=0))
 baseline_bytes=(args.base/'auto-catalog.json').read_bytes()
 (args.out/'baseline.json').write_bytes(baseline_bytes)
 (args.out/'baseline.json.gz').write_bytes(gzip.compress(baseline_bytes,mtime=0))
 (args.out/'build-audit.json').write_text(json.dumps({'sourcePreserved':True,'singleSongOnly':True,'rows':audit,'newAudioAssets':rendered},ensure_ascii=False,indent=2))
 print('COMPLETE',rendered,flush=True)
if __name__=='__main__':main()
