"""Source-only drum measurements and deterministic one-bar replacement helpers."""
import numpy as np,subprocess
SR=44100

def rms(x):return float(np.sqrt(np.mean(x.astype(np.float64)**2))) if len(x) else 0.
def cv(values):
 x=np.asarray(values,dtype=float);return float(np.std(x)/(np.mean(x)+1e-12))
def classify_profile(early_rms,target_rms,early_active,target_active,target_cv):
 if not np.isfinite([early_rms,target_rms,early_active,target_active,target_cv]).all() or early_rms<.01:return None
 ratio=target_rms/early_rms
 if ratio<=.5 or target_active<=.5 and early_active>=.75:return 'thinning'
 if .8<=ratio<=1.25 and target_active>=.75 and target_cv<=.6:return 'stable'
 return None

def choose_source_bar(bars,evidence,target_start,threshold):
 eligible=[]
 for i,(b,e) in enumerate(zip(bars,evidence)):
  beats=b.get('beats',[])
  if not b.get('valid') or len(beats)!=4 or b['end']>target_start+.000001 or len(e['beatRms'])!=4:continue
  if e['rms']<.01 or min(e['beatRms'])<threshold or cv(e['beatRms'])>.6:continue
  eligible.append({'index':i,'cv':cv(e['beatRms']),'start':b['start'],'end':b['end']})
 return min(eligible,key=lambda x:(x['cv'],-x['end'])) if eligible else None

def stretch_bar(source,frames):
 if frames<=0 or len(source)==0:raise ValueError('empty loop bar')
 # Supply the following repeated bar as WSOLA lookahead; retain exactly one target bar.
 cmd=['ffmpeg','-v','error','-nostdin','-threads','1','-f','f32le','-ar',str(SR),'-ac','2','-i','pipe:0','-af','atempo='+str(len(source)/frames),'-f','f32le','-acodec','pcm_f32le','pipe:1']
 pcm=np.frombuffer(subprocess.check_output(cmd,input=np.concatenate([source,source]).astype('<f4').tobytes()),dtype='<f4').reshape(-1,2)
 if len(pcm)<frames or not np.isfinite(pcm).all():raise ValueError('incomplete stretched loop')
 return pcm[:frames].copy()

def build_loop_drums(natural,source_range,targets,stretch=stretch_bar,fade_frames=221,seam_frames=32):
 if natural.ndim!=2 or natural.shape[1]!=2 or not np.isfinite(natural).all() or not targets:raise ValueError('invalid drum PCM')
 s,e=source_range
 if s<0 or e<=s or e>targets[0][0] or targets[-1][1]>len(natural) or any(b<=a for a,b in targets) or any(targets[i][1]!=targets[i+1][0] for i in range(len(targets)-1)):raise ValueError('invalid fixed loop range')
 out=natural.copy();source=natural[s:e].copy()
 for a,b in targets:
  bar=stretch(source,b-a)
  if bar.shape!=(b-a,2) or not np.isfinite(bar).all():raise ValueError('invalid stretched bar')
  out[a:b]=bar
 a,b=targets[0][0],targets[-1][1];k=min(max(0,fade_frames),b-a)
 if k:weight=np.arange(k,dtype=np.float32)[:,None]/k;out[a:a+k]=natural[a:a+k]*(1-weight)+out[a:a+k]*weight
 for boundary,_ in targets[1:]:
  radius=min(max(0,seam_frames//2),boundary-a,b-boundary-1)
  if radius:
   lo,hi=boundary-radius,boundary+radius;out[lo:hi+1]=np.linspace(out[lo],out[hi],hi-lo+1)
 return out
