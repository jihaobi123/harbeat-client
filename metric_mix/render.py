"""Jointly aligned source arrays; signed stem corrections and original EQ controls."""
import math
import numpy as np
from scipy.signal import lfilter

def curve(n,sr,points):
 t=np.arange(n)/sr
 return np.interp(t,[x[0] for x in points],[x[1] for x in points]).astype('float64')[:,None]

def biquad(kind,hz,db,q,sr):
 A=10**(db/40);w=2*np.pi*hz/sr;c=np.cos(w);s=np.sin(w)
 if kind=='peak':
  alpha=s/(2*q);b=[1+alpha*A,-2*c,1-alpha*A];a=[1+alpha/A,-2*c,1-alpha/A]
 else:
  alpha=s/2*np.sqrt(2);u=2*np.sqrt(A)*alpha
  if kind=='low':b=[A*((A+1)-(A-1)*c+u),2*A*((A-1)-(A+1)*c),A*((A+1)-(A-1)*c-u)];a=[(A+1)+(A-1)*c+u,-2*((A-1)+(A+1)*c),(A+1)+(A-1)*c-u]
  else:b=[A*((A+1)+(A-1)*c+u),-2*A*((A-1)+(A+1)*c),A*((A+1)+(A-1)*c-u)];a=[(A+1)-(A-1)*c+u,2*((A-1)-(A+1)*c),(A+1)-(A-1)*c-u]
 return np.asarray(b)/a[0],np.asarray(a)/a[0]

def eq_stems(stems,points,sr,duration,side,restore):
 keys=list(stems);x=np.concatenate([stems[k] for k in keys],axis=1).astype('float64');y=x.copy()
 for kind,hz,q in [('low',140,.7071),('high',3600,.7071),('peak',1200,1.05)]:
  band='mid' if kind=='peak' else kind;zi=np.zeros((2,x.shape[1]));out=np.empty_like(y)
  for i in range(0,len(y),64):
   db=float(np.interp(i/sr,[p['t'] for p in points],[p[band] for p in points]));b,a=biquad(kind,hz,db,q,sr);out[i:i+64],zi=lfilter(b,a,y[i:i+64],axis=0,zi=zi)
  y=out
 wet=curve(len(x),sr,[(0,0),(.02,1)]) if side=='a' else curve(len(x),sr,[(0,1),(restore,1),(duration,0)])
 y=y*wet+x*(1-wet)
 return {k:y[:,j*2:j*2+2] for j,k in enumerate(keys)}

def highpass_variable(x,sr,start,end):
 # Warm the filter before enabling its signed correction. WebAudio Q is -3.0103dB.
 state=np.zeros((2,x.shape[1]));out=np.empty_like(x,dtype='float64')
 for i in range(0,len(x),64):
  t=i/sr;f=20*90**min(1,max(0,(t-start)/(end-start)));w=2*np.pi*f/sr;c=np.cos(w);alpha=np.sin(w)/(2*math.sqrt(.5));a=np.array([1+alpha,-2*c,1-alpha]);b=np.array([(1+c)/2,-(1+c),(1+c)/2]);out[i:i+64],state=lfilter(b/a[0],a/a[0],x[i:i+64],axis=0,zi=state)
 return out

def mix_candidates(stems,case,sr=44100):
 d=case['duration'];n=round(d*sr);a=stems['a'];b=stems['b']
 if any(x.shape!=(n,2) or not np.isfinite(x).all() for s in [a,b] for x in s.values()):raise ValueError('Aligned finite stereo arrays required')
 if case.get('eq'):
  a=eq_stems(a,case['eq']['a'],sr,d,'a',case.get('restore',max(0,d-.5)));b=eq_stems(b,case['eq']['b'],sr,d,'b',case.get('restore',max(0,d-.5)))
 ga=curve(n,sr,[(0,1),(d,0)]);gb=1-ga;original=a['master']*ga+b['master']*gb;out={'original':original}
 if 'bass' in a and 'bass' in b:
  t=case['bassTiming'];ba=curve(n,sr,[(0,1),(t['duckStart'],1),(t['swapStart'],.5),(t['swapEnd'],0),(d,0)]);bb=curve(n,sr,[(0,0),(t['swapStart'],0),(t['swapEnd'],1),(d,1)])
  delta=a['bass']*(ba-ga)+b['bass']*(bb-gb);out['bass']=original+delta
 if 'other' in a:
  start=case['lastBarStart'];hp=highpass_variable(a['other'],sr,start,d);enable=curve(n,sr,[(0,0),(start,0),(min(start+.02,d),1),(d,1)]);filter_delta=(hp-a['other'])*ga*enable;out['filter']=original+filter_delta
  gy=curve(n,sr,[(0,1),(start,0),(d,0)]);out['yield']=original+a['other']*(gy-ga)
  if 'bass' in out:out['bass_filter']=out['bass']+filter_delta
 if case.get('vocalExit') and 'vocals' in a and 'vocals' in b:
  v=case['vocalExit'];va=curve(n,sr,[(0,1),(v['fadeStart'],1),(v['fadeEnd'],0),(d,0)]);vb=gb.copy();vb[np.arange(n)/sr<v['fadeEnd']+.08]=0
  # The gate guarantees B has no vocal activity before restore; smooth the delta anyway.
  blend=curve(n,sr,[(0,0),(v['fadeEnd'],0),(min(d,v['fadeEnd']+.08),1),(d,1)]);vb=gb*blend
  out['vocal']=original+a['vocals']*(va-ga)+b['vocals']*(vb-gb)
 return {k:(np.concatenate([x,case['body']],axis=0)*.60).astype('float32') if case.get('body') is not None else (x*.60).astype('float32') for k,x in out.items()}
