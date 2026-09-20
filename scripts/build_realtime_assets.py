#!/usr/bin/env python3
"""Prepare single-song assets only. All selection, EQ and crossfades happen live."""
from pathlib import Path
import argparse,hashlib,json,math,statistics,subprocess
import soundfile as sf

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def verify_vocals(core,vocal):
 s=vocal.get('source',{})
 if vocal.get('status')!='ready' or not isinstance(vocal.get('intervals'),list) or s.get('track_id')!=core['track_id'] or s.get('analysis_run_id')!=core['analysis_run_id'] or s.get('vocal_sha256')!=core['assets']['stems']['vocals']['sha256']:raise ValueError('vocal source binding mismatch')
 return [[x['start_ms']/1000,x['end_ms']/1000] for x in vocal['intervals']]

def windows(bars,sections,duration):
 starts={0}
 for s in sections:
  idx=min(range(len(bars)),key=lambda i:abs(bars[i]-s['start']))
  if bars[idx]<90:starts.add(idx)
 # Limit the prototype to four genuine entry anchors per song.
 starts=sorted(starts)[:4];result=[]
 for i in starts:
  for n in [2,4]:
   if i+n>=len(bars) or bars[i+n]+12>duration:continue
   start,end=bars[i],bars[i+n]
   role=next((s['label'] for s in sections if s['start']<=start<s['end']),'unclassified')
   result.append({'id':f'w{i}-{n}','start':start,'end':end,'bars':n,'role':role})
 return result

def energy(curve,start,end):
 pairs=[(max(0,min(end,x['end'])-max(start,x['start'])),x['value']) for x in curve]
 den=sum(w for w,v in pairs)
 return sum(w*v for w,v in pairs)/den if den else 0

def encode(source,dest,filters,commands):
 recipe={'source_sha256':sha(source),'filter':filters,'format':'flac-s16-stereo-44100-frame4096-v1'}
 record=dest.with_suffix('.recipe.json');valid=False
 try:
  old=json.loads(record.read_text());valid=dest.exists() and old.get('recipe')==recipe and old.get('asset_sha256')==sha(dest) and sf.info(dest).frames>0
 except (OSError,RuntimeError,ValueError):pass
 if not valid:
  temporary=dest.with_suffix('.part.flac')
  cmd=['ffmpeg','-nostdin','-y','-v','error','-i',str(source),'-vn','-af',filters,'-ar','44100','-ac','2','-c:a','flac','-sample_fmt','s16','-frame_size','4096',str(temporary)]
  subprocess.run(cmd,check=True,timeout=180)
  temporary.replace(dest)
  record.write_text(json.dumps({'recipe':recipe,'asset_sha256':sha(dest)}))
 commands.append({'asset':dest.name,'source_name':source.name,'filter':filters,'reused':valid})
 info=sf.info(dest)
 return {'url':'media/'+dest.name,'sha256':sha(dest),'duration':info.duration,'bytes':dest.stat().st_size,'frames':info.frames,'sampleRate':info.samplerate}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
 base=args.data_dir;out=args.output;media=out/'media';media.mkdir(parents=True,exist_ok=True)
 plan=json.loads((base/'listen/plan.json').read_text());rows=json.loads((base/'inputs/inputs.json').read_text());tracks=[];sources={};commands=[]
 for chosen in plan['tracks']:
  x=next(x for x in rows if x['report_id']==chosen['report_id']);rp=base/'inputs/reports'/(x['report_id']+'.json');source=base/'inputs'/x['relative_path']
  if sha(rp)!=x['report_file_sha256'] or sha(source)!=x['sha256']:raise ValueError('source identity mismatch')
  r=json.loads(rp.read_text());c=r['documents']['core'];a=c['analysis'];tid=c['track_id'];sources[tid]=source
  if c['assets']['master']['sha256']!=x['sha256']:raise ValueError('master mismatch')
  duration=min(150,c['assets']['master']['duration_ms']/1000);bars=[v/1000 for v in a['beat_grid']['bars_ms'] if v/1000<duration]
  bpm=a['tempo']['bpm'];grid_bpm=240/statistics.median([y-z for z,y in zip(bars,bars[1:])])
  if abs(grid_bpm/bpm-1)>.05:raise ValueError('grid tempo inconsistency')
  sections=[{'start':s['start_ms']/1000,'end':s['end_ms']/1000,'label':s['label']} for s in a['sections']['items']]
  curve=[{'start':v['start_ms']/1000,'end':v['end_ms']/1000,'value':v['value']} for v in a['energy']['curve']]
  style=r['extensions']['genre']['data']['top'][0];native=encode(source,media/(tid+'.flac'),f'atrim=end={duration:.6f},asetpts=PTS-STARTPTS',commands)
  t={'id':tid,'title':r['title'],'bpm':bpm,'duration':native['duration'],'style':style['style'],'styleScore':style['score'],'native':native,'bars':bars,'sections':sections,'vocals':verify_vocals(c,r['documents']['vocal_activity']),'energy':curve,'windows':windows(bars,sections,native['duration']),'warnings':['段落与小节未经人工确认','能量使用已有局部曲线作启发式比较，未作跨曲感知校准']+(['原始 BPM 标记待确认'] if a['tempo'].get('needs_review') else []),'reportId':r['id'],'provenance':{'masterSha256':x['sha256'],'reportSha256':x['report_file_sha256'],'runId':c['analysis_run_id'],'sectionSource':a['sections']['source'],'vocalSha256':c['assets']['stems']['vocals']['sha256']}}
  tracks.append(t);print('Native',t['title'],flush=True)
 for b in tracks:
  for w in b['windows']:
   w['energy']=energy(b['energy'],w['end'],min(b['duration'],w['end']+16));w['variants']={}
   for a in tracks:
    if a['id']==b['id']:continue
    length=w['bars']*240/a['bpm'];rate=(w['end']-w['start'])/length
    if not .8<=rate<=1.2:continue
    dest=media/(b['id']+'-'+w['id']+'-'+a['id'][6:]+'.flac')
    filt=f"atrim=start={w['start']:.6f}:end={w['end']:.6f},asetpts=PTS-STARTPTS,atempo={rate:.9f},apad=whole_dur={length:.9f},atrim=end={length:.9f}"
    asset=encode(sources[b['id']],dest,filt,commands);asset['rate']=rate;asset['mapping']='source interval → FFmpeg atempo → exact target-length trim/pad; no EQ or pair mixing';w['variants'][a['id']]=asset
  print('Entry assets',b['title'],flush=True)
 doc={'schema':'harbeat.realtime_v3.assets.v1','version':'V3 Live Preview 0.1','tracks':tracks,'policy':{'gain':.76,'aBassDb':-9,'bBassDb':-7,'aTrebleDb':-1.4,'bTrebleDb':1.2,'midDb':-5,'midHz':1200,'midQ':1.05,'lowHz':140,'highHz':3600},'limitations':['只提供六首既有 Hip-Hop 曲目，风格筛选为模型 Trap/Grime 候选','每首最多前150秒；不包含整场预渲染音频','浏览器 Biquad EQ 与自有保护限幅不同于原 FFmpeg 实现，不宣称波形完全相同','仅进入窗口保调变速，交接后正文恢复原速；所有跨曲 EQ 和淡化在浏览器实时执行','AudioWorklet 到点记录不是声卡／蓝牙输出实测','后台挂起会暂停音频时钟；原生手机后台播放未在此版本实现']}
 (out/'catalog.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2));(out/'asset-build.json').write_text(json.dumps({'commands':commands,'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],'assets_are_single_song_only':True},ensure_ascii=False,indent=2))
 print('Done',len(tracks),sum(len(w['variants']) for t in tracks for w in t['windows']),flush=True)
if __name__=='__main__':main()
