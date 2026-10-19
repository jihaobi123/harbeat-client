"""Endpoint-preserving, channel-coherent local WSOLA. No mixing or normalization."""
import numpy as np

def validate_map(source,target,duration):
    x=np.asarray(source,dtype=float);y=np.asarray(target,dtype=float)
    if x.ndim!=1 or y.shape!=x.shape or len(x)<3 or not np.isfinite(np.r_[x,y,duration]).all() or duration<=0:raise ValueError('invalid time map')
    if max(abs(x[0]),abs(y[0]),abs(x[-1]-duration),abs(y[-1]-duration))>1e-6 or np.any(np.diff(x)<=0) or np.any(np.diff(y)<=0):raise ValueError('time map must preserve fixed source endpoints and order')
    rates=np.diff(x)/np.diff(y)
    if np.any(rates<.85) or np.any(rates>1.15) or np.max(np.abs(x-y))>.065+1e-9:raise ValueError('unsafe local correction')
    return x,y

def warp_shared(pcm,sr,source,target):
    pcm=np.asarray(pcm,dtype=np.float32);n=len(pcm);duration=n/sr
    x,y=validate_map(source,target,float(source[-1]))
    if pcm.ndim!=2 or pcm.shape[1]<2 or not np.isfinite(pcm).all() or abs(duration-x[-1])>1/sr:raise ValueError('invalid source PCM clock')
    if np.array_equal(x,y):return pcm.copy()
    frame=max(128,round(sr*.032));frame+=frame%2;hop=frame//4;pad=frame;search=max(1,round(sr*.0125));step=max(1,round(sr*.00025))
    padded=np.pad(pcm,((pad,pad),(0,0)));window=np.hanning(frame).astype(np.float32);out=np.zeros((n+2*pad,pcm.shape[1]),dtype=np.float64);weights=np.zeros(n+2*pad,dtype=np.float64)
    # One analysis position for all channels preserves master/vocal additivity.
    for center in range(0,n+hop,hop):
        ideal=round(np.interp(min(center,n)/sr,y,x)*sr)+pad-frame//2
        ideal=max(0,min(len(padded)-frame,ideal));dest=center+pad-frame//2
        index=ideal
        if center>frame and center<n-frame:
            known=weights[dest:dest+frame]>.05
            if known.any():
                reference=np.zeros((frame,2));reference[known]=out[dest:dest+frame,:2][known]/weights[dest:dest+frame,None][known]
                scores=[]
                for candidate in range(max(0,ideal-search),min(len(padded)-frame,ideal+search)+1,step):
                    value=padded[candidate:candidate+frame,:2];den=np.linalg.norm(value[known])*np.linalg.norm(reference[known]);score=float(np.sum(value[known]*reference[known])/den) if den>1e-10 else -abs(candidate-ideal)/max(1,search)
                    scores.append((score,-abs(candidate-ideal),candidate))
                if scores:index=max(scores)[2]
        block=padded[index:index+frame];out[dest:dest+frame]+=block*window[:,None];weights[dest:dest+frame]+=window
    result=(out[pad:pad+n]/np.maximum(weights[pad:pad+n,None],1e-8)).astype(np.float32)
    # Fixed source boundary samples and shared10ms ramps; no new cue or gap.
    edge=min(round(sr*.01),n//4);ramp=np.linspace(0,1,edge,dtype=np.float32)[:,None]
    result[:edge]=pcm[:edge]*(1-ramp)+result[:edge]*ramp;result[-edge:]=result[-edge:]*(1-ramp)+pcm[-edge:]*ramp
    result[:8]=pcm[:8];result[-8:]=pcm[-8:]
    if not np.isfinite(result).all():raise ValueError('nonfinite rendered audio')
    return result
