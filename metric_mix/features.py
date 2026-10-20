import numpy as np

def rms(x):return float(np.sqrt(np.mean(np.asarray(x,dtype='float64')**2))) if len(x) else 0.
def chroma(x,sr):
 mono=np.mean(x,axis=1);n=min(len(mono),32768)
 if n<1024 or rms(mono)<1e-6:return None
 # Multiple observed windows, not a whole-track key label.
 profile=np.zeros(12)
 for at in range(0,max(1,len(mono)-n+1),n):
  y=mono[at:at+n];power=np.abs(np.fft.rfft(y*np.hanning(len(y))))**2;f=np.fft.rfftfreq(len(y),1/sr);valid=(f>=40)&(f<=4000);midi=np.round(69+12*np.log2(f[valid]/440)).astype(int);np.add.at(profile,midi%12,power[valid])
 return profile/np.linalg.norm(profile) if np.linalg.norm(profile)>1e-10 else None

def overlap(a,b,sr):
 n=min(len(a),len(b));size=round(sr*.125);scores=[]
 for i in range(0,n,size):
  ga=1-(i+size/2)/n;gb=1-ga;pa=rms(a[i:i+size]);pb=rms(b[i:i+size])
  if pa<10**(-45/20) or pb<10**(-45/20):scores.append(0.);continue
  x,y=pa*ga,pb*gb;scores.append(2*min(x,y)/(x+y+1e-12))
 return float(np.clip(np.mean(scores),0,1)) if scores else None

def describe(stems,case,sr):
 m={'stemAvailable':{k:k in stems['a'] and k in stems['b'] for k in ['bass','other','vocals']},'vocalSafe':case.get('vocalExit') is not None,'vocalBenefit':case.get('vocalBenefit',0)}
 for stem,prefix in [('bass','bass'),('other','other')]:
  a,b=stems['a'].get(stem),stems['b'].get(stem)
  if a is None or b is None:m[prefix+'Overlap']=None;m[prefix+'Difference']=None;continue
  m[prefix+'Overlap']=overlap(a,b,sr);ca,cb=chroma(a,sr),chroma(b,sr);m[prefix+'Difference']=float(np.clip(1-np.dot(ca,cb),0,1)) if ca is not None and cb is not None else None
 m['definitions']={'overlap':'125ms数字RMS与原渐混增益计算的同时可闻平衡代理；0–1，不是冲突概率','difference':'短片段FFT音高分布余弦差异；不是调性标签或和弦不协和真值','vocalSafe':'同源VAD与能量尾部、后续空隙及B进入检查；不保证歌词语义结束'}
 return m

def render_stats(x,sr):
 block=round(sr*.25);db=[20*np.log10(max(rms(x[i:i+block]),1e-9)) for i in range(0,len(x),block)];diff=np.diff(db)
 return {'peak':float(np.max(np.abs(x))),'rmsDbfs':20*np.log10(max(rms(x),1e-9)),'maximumBlockJumpDb':float(max(0,np.max(diff))) if len(diff) else 0,'maximumBlockDropDb':float(max(0,-np.min(diff))) if len(diff) else 0,'unit':'digital RMS;not perceived loudness'}
