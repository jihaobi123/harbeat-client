"""Prepare report-bound master/vocal excerpts; never mix tracks offline."""
import argparse, hashlib, json, pathlib, struct, subprocess
import numpy as np
SR=44100

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for data in iter(lambda:f.read(1024*1024),b''):h.update(data)
 return h.hexdigest()

def checked_source(root,asset):
 root=root.resolve();path=(root/asset['storage_key']).resolve()
 if root not in path.parents:raise ValueError('source outside NAS root')
 if sha(path)!=asset['sha256']:raise ValueError('source hash mismatch')
 return path

def stretch_pair(master,vocal,start,duration,rate):
 # One four-channel WSOLA operation: content-dependent shifts must be shared.
 # Extra source tail absorbs atempo window latency before exact frame cropping.
 cmd=['ffmpeg','-v','error','-nostdin','-threads','1']
 for source in (master,vocal):cmd+=['-ss',str(start),'-t',str((duration+.75)*rate),'-i',str(source)]
 cmd+=['-filter_complex',f'[0:a]aresample={SR},aformat=sample_fmts=flt:channel_layouts=stereo[m];[1:a]aresample={SR},aformat=sample_fmts=flt:channel_layouts=stereo[v];[m][v]amerge=inputs=2,atempo={rate}[out]', '-map','[out]','-f','f32le','-acodec','pcm_f32le','pipe:1']
 data=np.frombuffer(subprocess.check_output(cmd),dtype='<f4').reshape(-1,4)
 frames=round(duration*SR)
 if len(data)<frames or not np.isfinite(data).all():raise ValueError('incomplete or invalid rendered audio')
 return data[:frames,:2].copy(),data[:frames,2:].copy()

def write_float(path,data):
 raw=data.astype('<f4').tobytes();fmt=struct.pack('<HHIIHH',3,2,SR,SR*8,8,32)
 path.write_bytes(b'RIFF'+struct.pack('<I',36+len(raw))+b'WAVEfmt '+struct.pack('<I',16)+fmt+b'data'+struct.pack('<I',len(raw))+raw)
 return dict(url='audio/'+path.name,sha256=sha(path),bytes=path.stat().st_size,duration=len(data)/SR,frames=len(data),sampleRate=SR,channels=2,peak=float(np.max(np.abs(data))))

def render(args):
 selection_bytes=args.selection.read_bytes();selection_hash=hashlib.sha256(selection_bytes).hexdigest()
 data=json.loads(selection_bytes);tracks={t['id']:t for t in data['tracks']};out=args.output;audio=out/'audio';audio.mkdir(parents=True,exist_ok=True)
 sources={};evidence={}
 for tid,t in tracks.items():
  rp=args.reports/(t['reportId']+'.json')
  if sha(rp)!=t['provenance']['reportSha256']:raise ValueError('report changed '+tid)
  report=json.loads(rp.read_text());core=report['documents']['core'];master=core['assets']['master'];vocal=core['assets']['stems']['vocals']
  if core['track_id']!=tid or core['analysis_run_id']!=t['provenance']['runId'] or master['sha256']!=t['provenance']['masterSha256'] or vocal['sha256']!=t['provenance']['vocalSha256']:raise ValueError('source binding mismatch '+tid)
  if report['audio']['assets']['master']['channels']!=2 or report['audio']['assets']['vocals']['channels']!=2:raise ValueError('stereo sources required')
  sources[tid]=(checked_source(args.nas,master),checked_source(args.nas,vocal))
  evidence[tid]=dict(reportId=t['reportId'],**t['provenance'])
  print('verified',t['title'],flush=True)
 result=[]
 for c in data['cases']:
  assets={}
  for side,start,duration,rate in [('a',c['start']-4,4+c['duration'],1),('b',c['bEntry'],c['duration']+10,c['rate'])]:
   m,v=stretch_pair(*sources[c[side]],start,duration,rate)
   for kind,pcm in [('master',m),('vocal',v)]:assets[side+kind.title()]=write_float(audio/(c['id']+'-'+side+'-'+kind+'.wav'),pcm)
  result.append(dict(id=c['id'],assets=assets,sources={k:evidence[c[k]] for k in ('a','b')}))
  print('rendered',c['id'],flush=True)
 (out/'rendered.json').write_text(json.dumps(dict(schema='harbeat.vocal-bridge-assets.v1',selectionSha256=selection_hash,cases=result),ensure_ascii=False,indent=2))
 print('bytes',sum(p.stat().st_size for p in audio.iterdir()),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--selection',type=pathlib.Path,required=True);p.add_argument('--nas',type=pathlib.Path,required=True);p.add_argument('--reports',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);render(p.parse_args())
