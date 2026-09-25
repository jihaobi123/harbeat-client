import type {Track} from '../realtime/planner'
import {requireBoundVocals} from '../vocal-overlap/planner'
import {localBeatGate} from '../continuous/beatAlignment'
export type BridgeCue={start:number;end:number;duration:number;rate:number;bEntry:number;bEnd:number;bVoiceStart:number;aVoiceEnd:number;bars:number}
export type Points=[number,number][]
export function validateBridge(a:Track,b:Track,p:BridgeCue){
 requireBoundVocals(a);requireBoundVocals(b)
 if([p.start,p.end,p.duration,p.rate,p.bEntry,p.bEnd,p.bVoiceStart,p.aVoiceEnd,p.bars].some(n=>!Number.isFinite(n))||p.rate<.94||p.rate>1.06||p.duration<5||p.duration>24||p.start<4||p.end>a.duration||p.bEntry<0||p.bEnd+10*p.rate+.5>b.duration||![2,4,8].includes(p.bars)||Math.abs(p.end-p.start-p.duration)>.002||Math.abs((p.bEnd-p.bEntry)/p.rate-p.duration)>.002)throw Error('接点或变速范围无效')
 const problem=localBeatGate(a,b,{start:p.start,end:p.end,rate:p.rate,duration:p.duration,window:{id:'bridge',start:p.bEntry,end:p.bEnd,bars:p.bars,variants:{},role:'inst',energy:0}})
 if(problem)throw Error(problem)
 const bVoice=b.vocals!.find(([s,e])=>s>=p.bEnd+.15&&e-s>.6)
 if(b.vocals!.some(([s,e])=>s<p.bEnd+.15&&e>p.bEntry-.3)||!bVoice||Math.abs(bVoice[0]-p.bVoiceStart)>.001||p.bVoiceStart>p.bEnd+2)throw Error('下一首没有完整的无人声铺入段')
 const aVoice=a.vocals!.filter(([s,e])=>s<p.end&&e>p.start)
 const coverage=aVoice.reduce((n,[s,e])=>n+Math.max(0,Math.min(e,p.end)-Math.max(s,p.start)),0)
 const lastEnd=Math.max(...aVoice.map(x=>x[1]))
 if(coverage<2||Math.abs(lastEnd-p.aVoiceEnd)>.001||p.end-lastEnd<.5||p.end-lastEnd>3||lastEnd<p.start+.55*p.duration)throw Error('上一首人声没有合适的收尾空间')
}
export function bridgeCurves(p:BridgeCue,pre:number){
 const end=pre+p.duration,bedEnd=pre+p.duration*.4,voiceEnd=pre+p.aVoiceEnd-p.start+.15
 return {aBed:[[0,1],[pre,1],[bedEnd,0],[end,0]] as Points,
  aVoice:[[0,1],[voiceEnd,1],[end,0]] as Points,
  bBed:[[0,0],[pre,0],[bedEnd,1],[end,1]] as Points,
  bVoice:[[0,0],[end-.2,0],[end,1]] as Points}
}
export function valueAt(points:Points,t:number){let last=points[0];if(t<=last[0])return last[1];for(const p of points.slice(1)){if(p[0]>t)return last[1]+(p[1]-last[1])*(t-last[0])/(p[0]-last[0]);last=p}return last[1]}
