"""Finite stem-only FX windows; sidecars are experimental eligibility, not quality labels."""
import math
import numpy as np

def plan_vocal_echo(c,a,b):
 p=c['plan'];e=a.get('selected');pre=c['pre'];bpm=c['bpm'][0]
 if not e or not all(math.isfinite(x) for x in [pre,bpm,p['start'],p['end'],p['duration'],p['rate']]) or pre<0 or not 50<=bpm<=220 or p['rate']<=0 or p['duration']<=0 or abs(p['end']-p['start']-p['duration'])>.002:raise ValueError('invalid cue/tempo/endpoint')
 for side,t in [('a',a),('b',b)]:
  if any(t['source'][k]!=c['sourceVerification'][side][k] for k in ['vocalSha256','masterSha256','runId','manifestSha256']):raise ValueError('FX source mismatch')
 beat=60/bpm;origin=p['start']-pre;send_end=e['tailEnd']-origin;send_start=send_end-beat
 taps=[dict(delaySeconds=beat*n,gain=g) for n,g in zip([.5,1,1.5],[.26,.117,.052])]
 wet_start=send_start+taps[0]['delaySeconds'];wet_end=send_end+taps[-1]['delaySeconds']+.04
 if not all(math.isfinite(x) for x in [send_start,send_end,wet_start,wet_end,e['nextOnset']]) or send_start<pre or wet_end>pre+p['duration']-.08 or wet_end+origin>e['nextOnset']-.08:raise ValueError('insufficient quiet-window for finite echo')
 for label,t,s,en in [('outgoing',a,p['start'],p['end']+.08),('incoming',b,p['window']['start']-.3,p['window']['end']+.15)]:
  cov=t.get('coverage',{})
  if not all(isinstance(cov.get(k),(int,float)) and math.isfinite(cov[k]) for k in ['start','end']) or cov['start']>s+1e-6 or cov['end']<en-1e-6:raise ValueError(label+' FX observation coverage missing')
 incoming=[p['window']['start']+(wet_start-pre)*p['rate'],p['window']['start']+(wet_end-pre)*p['rate']]
 if any(x['start']<incoming[1]+.15 and x['tailEnd']>incoming[0]-.15 for x in b['report']['candidates']+b['report']['rejected']):raise ValueError('incoming voice overlaps FX support')
 return dict(schema='harbeat.stem-fx-window.v1',kind='finite-vocal-echo',beatSeconds=beat,sourceOrigin=origin,sendStart=send_start,sendEnd=send_end,wetStart=wet_start,wetEnd=wet_end,taps=taps,edgeSeconds=.01,highpassHz=180,lowpassHz=5000,incomingSourceWindow=incoming,source=c['sourceVerification'],outgoingNextOnset=e['nextOnset'],nextOnsetObserved=e.get('nextOnsetObserved',False),status='experimental-listening-review-required')

def finite_taps(audio,sr,taps):
 x=np.asarray(audio)
 if x.ndim!=2 or x.shape[1]!=2 or not len(x) or not np.isfinite(x).all() or not isinstance(sr,(int,float)) or not math.isfinite(sr) or sr<=0:raise ValueError('finite stereo audio required')
 out=np.zeros(x.shape,dtype=np.float64)
 for tap in taps:
  delay,gain=tap['delaySeconds'],tap['gain']
  if not math.isfinite(delay) or not math.isfinite(gain) or delay<=0 or not 0<=gain<=.5:raise ValueError('invalid finite tap')
  frames=round(delay*sr)
  if frames<1:raise ValueError('delay shorter than one sample')
  if frames<len(x):out[frames:]+=x[:-frames]*gain
 return out

def render_vocal_echo(audio,sr,fx):
 from scipy.signal import butter,sosfilt
 x=np.asarray(audio)
 if sr<12000:raise ValueError('sample rate below FX filter bandwidth')
 duration=len(x)/sr
 if fx['sendStart']<0 or fx['sendEnd']<=fx['sendStart'] or fx['wetEnd']>duration or not np.isfinite(x).all():raise ValueError('FX window outside decoded source')
 filtered=sosfilt(butter(2,[fx['highpassHz'],fx['lowpassHz']],btype='bandpass',fs=sr,output='sos'),x,axis=0)
 time=np.arange(len(x))/sr;edge=fx['edgeSeconds']
 envelope=np.minimum(np.clip((time-fx['sendStart'])/edge,0,1),np.clip((fx['sendEnd']-time)/edge,0,1))
 out=finite_taps(filtered*envelope[:,None],sr,fx['taps'])
 out[time>=fx['wetEnd']]=0
 return out.astype(np.float32)
