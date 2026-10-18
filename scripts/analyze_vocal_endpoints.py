"""Reproducible research runner; use model and pitch environments separately."""
import argparse, hashlib, json, pathlib, subprocess

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def prepare(root,nas):
 contexts={'Attention':(140,163,146.73543537414966,155.887),'After LIKE':(145,164,150.2,157.88),'24K Magic (1)':(191,212,196.30802721088435,205.28),'HIPHOP':(24,42,27.22,36.28)}
 if (root/'context-request.json').exists():contexts=json.loads((root/'context-request.json').read_text())
 records=[]
 for t in json.loads((root/'tracks.json').read_text()):
  start,end,cs,ce=contexts[t['title']];v=t['provenance'];m=nas/'published/tracks'/t['id']/'runs'/v['runId']/'manifest.json';d=json.loads(m.read_text());a=d['assets']['stems']['vocals'];source=(nas/a['storage_key']).resolve()
  binding=t['preprocessing']['vocalActivity']['source']
  if nas.resolve() not in source.parents or sha(m)!=binding['manifest_sha256'] or sha(source)!=v['vocalSha256'] or a['sha256']!=v['vocalSha256'] or d['assets']['master']['sha256']!=v['masterSha256']:raise ValueError('source mismatch')
  dest=root/(t['id']+'.wav')
  subprocess.run(['ffmpeg','-v','error','-y','-ss',str(start),'-t',str(end-start),'-i',str(source),'-ar','16000','-ac','1','-c:a','pcm_f32le',str(dest)],check=True)
  records.append(dict(id=t['id'],title=t['title'],start=start,end=end,cueStart=cs,cueEnd=ce,source=dict(v,manifestSha256=sha(m)),contextSha256=sha(dest),
    vad=[[x['start_ms']/1000,x['end_ms']/1000] for x in t['preprocessing']['vocalActivity']['intervals']],bars=t['bars'],bpm=t['bpm']))
 (root/'contexts.json').write_text(json.dumps(records,indent=2));print('prepared',len(records),flush=True)

def binding(c):return {k:c[k] for k in ['id','start','end','contextSha256']}

def model(root):
 import numpy as np, soundfile as sf, essentia, essentia.streaming as es, tensorflow as tf
 def graph(path,inp,outs):
  g=tf.Graph();gd=tf.compat.v1.GraphDef();gd.ParseFromString(path.read_bytes())
  with g.as_default():tf.import_graph_def(gd,name='')
  session=tf.compat.v1.Session(graph=g,config=tf.compat.v1.ConfigProto(intra_op_parallelism_threads=2,inter_op_parallelism_threads=1,device_count={'GPU':0}))
  ti=g.get_tensor_by_name(inp+':0');to=[g.get_tensor_by_name(n+':0') for n in outs];print(inp,ti.shape,[(x.name,str(x.shape)) for x in to],flush=True)
  return lambda x:session.run(to,{ti:x})
 receipt=json.loads((root/'models/receipt.json').read_text())
 for f in receipt['files']:
  if sha(root/'models'/f['file'])!=f['sha256']:raise ValueError('official weight receipt mismatch')
 backbone=graph(root/'models/audioset-yamnet-1.pb','melspectrogram',['embeddings','activations'])
 head=graph(root/'models/voice_instrumental-audioset-yamnet-1.pb','model/Placeholder',['model/Softmax'])
 classes=json.loads((root/'models/audioset-yamnet-1.json').read_text())['classes'];selected=['Speech','Singing','Rapping','Humming','Choir','Breathing']
 for c in json.loads((root/'contexts.json').read_text()):
  p=root/(c['id']+'.wav')
  if sha(p)!=c['contextSha256']:raise ValueError('context changed')
  audio,sr=sf.read(p,dtype='float32');assert sr==16000
  if abs(len(audio)/sr-(c['end']-c['start']))>.002:raise ValueError('incomplete context')
  pool=essentia.Pool();src=es.VectorInput(audio);cut=es.FrameCutter(frameSize=400,hopSize=160);mel=es.TensorflowInputVGGish();pack=es.VectorRealToTensor(shape=[-1,1,96,64],patchHopSize=48,lastPatchMode='repeat')
  src.data>>cut.signal;cut.frame>>mel.frame;mel.bands>>pack.frame;pack.tensor>>(pool,'patches');essentia.run(src)
  patches=np.concatenate(pool['patches'],axis=0)
  # Frozen graph signature: [batch,96,64]; remove Essentia tensor channel axis.
  em,events=backbone(patches[:,0]);voice=head(em)[0][:,1]
  values=[dict(start=c['start']+i*.48,end=min(c['end'],c['start']+i*.48+.96),voice=float(v),events={k:float(events[i,classes.index(k)]) for k in selected}) for i,v in enumerate(voice) if c['start']+i*.48<c['end']]
  (root/(c['id']+'-model.json')).write_text(json.dumps(dict(context=binding(c),models=receipt,frames=values,patchSeconds=.96,hopSeconds=.48,timeResolution='coarse patch support; not precise vocal boundaries',normalized=False)))
  print(c['title'],len(values),'voice range',float(min(voice)),float(max(voice)),flush=True)

def pitch(root):
 import numpy as np, soundfile as sf, librosa
 for c in json.loads((root/'contexts.json').read_text()):
  p=root/(c['id']+'.wav')
  if sha(p)!=c['contextSha256']:raise ValueError('context changed')
  audio,sr=sf.read(p,dtype='float32');hop=256
  f0,flag,prob=librosa.pyin(audio,fmin=librosa.note_to_hz('C2'),fmax=librosa.note_to_hz('C7'),sr=sr,frame_length=2048,hop_length=hop)
  modelpath=root/(c['id']+'-model.json');modeldoc=json.loads(modelpath.read_text())
  if modeldoc.get('context')!=binding(c):raise ValueError('stale model output')
  coarse=modeldoc['frames'];frames=[]
  for i in range(int(len(audio)/sr/.05)):
   t=i*.05;block=audio[int(t*sr):int((t+.05)*sr)];j=min(len(prob)-1,round(t*sr/hop));absolute=c['start']+t
   scores=[x['voice'] for x in coarse if x['start']<=absolute<x['end']]
   frames.append(dict(t=round(absolute,6),rms=float(np.sqrt(np.mean(block.astype('float64')**2))),voiced=float(prob[j]) if flag[j] else 0,f0=float(f0[j]) if np.isfinite(f0[j]) else None,voice=max(scores,default=0)))
  (root/(c['id']+'-frames.json')).write_text(json.dumps(dict(context=binding(c),modelOutputSha256=sha(modelpath),frames=frames,method='librosa.pyin C2-C7 2048/256; 50ms source RMS; centered pitch frames')))
  print('pitch',c['title'],len(frames),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','model','pitch']);p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--nas',type=pathlib.Path,default=pathlib.Path('/mnt/nas/harbeat/preprocess'));a=p.parse_args()
 if a.mode=='prepare':prepare(a.root,a.nas)
 elif a.mode=='model':model(a.root)
 else:pitch(a.root)
