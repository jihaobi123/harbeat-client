"""One complete provisional vocal activity segment, one fixed safe replay."""
import math
import numpy as np
def plan_retrigger(c,a,b):
 p=c['plan'];pre=c['pre'];origin=p['start']-pre;e=a.get('selected')
 if not e or c.get('baselineBass')!='reference' or not all(math.isfinite(x) for x in [pre,c['post'],p['start'],p['end'],p['duration'],p['rate']]) or pre<0 or c['post']<=0 or p['duration']<=0 or p['rate']<=0 or abs(p['end']-p['start']-p['duration'])>.002:raise ValueError('invalid original plan')
 for side,t in [('a',a),('b',b)]:
  if any(t['source'].get(k)!=c['sourceVerification'][side].get(k) for k in ['vocalSha256','masterSha256','runId','manifestSha256']):raise ValueError('source binding mismatch')
 s,en=e['start']-.03,e['tailEnd']+.03;duration=en-s;trigger=pre+p['duration'];end=trigger+duration
 if not all(math.isfinite(x) for x in [s,en]) or not .15<=duration<=3 or s-.5<origin or en+.5>p['end'] or end+.3>trigger+c['post']:raise ValueError('whole candidate too long or outside cached context')
 for t,point in [(a,p['end']),(b,p['window']['end'])]:
  if not t.get('bars') or min(abs(x-point) for x in t['bars'])>.065:raise ValueError('fixed handoff lacks raw-bar evidence')
 incoming=[p['window']['end'],p['window']['end']+duration];outgoing=[p['end'],p['end']+duration]
 for label,t,(lo,hi) in [('outgoing',a,outgoing),('incoming',b,incoming)]:
  cov=t.get('coverage',{})
  if not all(isinstance(cov.get(k),(int,float)) and math.isfinite(cov[k]) for k in ['start','end']) or cov['start']>lo-.3 or cov['end']<hi+.3:raise ValueError(label+' replay extends beyond observed voice coverage')
  intervals=[(x['start'],x['tailEnd']) for x in t['report']['candidates']+t['report']['rejected']]+list(t['vad'])
  if any(u<hi+.3 and v>lo-.3 for u,v in intervals):raise ValueError(label+' protected voice overlaps replay')
 if a['coverage']['start']>s-.5 or a['coverage']['end']<en+.5:raise ValueError('cue context unobserved')
 return dict(schema='harbeat.vocal-retrigger-window.v1',sourceStart=s,sourceEnd=en,duration=duration,sourceOrigin=origin,contextStart=s-.5,contextEnd=en+.5,trigger=trigger,replayEnd=end,count=1,edgeSeconds=.005,quietPadSeconds=.3,incomingSupport=incoming,outgoingSupport=outgoing,captureGainPolicy='original-a-linear-at-source',status='requires-human-cut-review',source=c['sourceVerification'],outgoingCoverage=a['coverage'],incomingCoverage=b['coverage'])
def capture_phrase(audio,sr,c,fx):
 x=np.asarray(audio);p=c['plan'];origin=p['start']-c['pre']
 if not isinstance(sr,(int,float)) or not math.isfinite(sr) or sr<=0 or x.shape!=(round((c['pre']+p['duration'])*sr),2) or not np.isfinite(x).all():raise ValueError('invalid frozen stereo source')
 first=round((fx['sourceStart']-origin)*sr);last=round((fx['sourceEnd']-origin)*sr)
 if first<0 or last>len(x) or first>=last:raise ValueError('capture outside original source')
 time=(np.arange(first,last)/sr)+origin;gain=np.clip((p['end']-time)/p['duration'],0,1);out=x[first:last].astype('float64')*gain[:,None]
 edge=round(fx['edgeSeconds']*sr)
 if edge<2 or edge*2>=len(out):raise ValueError('capture edge invalid')
 out[:edge]*=np.linspace(0,1,edge)[:,None];out[-edge:]*=np.linspace(1,0,edge)[:,None]
 return out.astype('float32')
