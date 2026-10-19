import type {Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export function handoffPlan(c:any,mode:Mode){
 const p=c.plan,h=c.handoff
 if(!['natural','relay'].includes(mode)||!p||!h||![c.pre,c.post,...c.bpm,p.start,p.end,p.duration,p.rate,p.window?.start,p.window?.end].every(Number.isFinite)||c.pre<0||c.post<=0||c.bpm.some((x:number)=>x<=0)||p.duration<=0||Math.abs(p.rate-1)>.05||Math.abs(p.end-p.start-p.duration)>.002||Math.abs((p.window.end-p.window.start)/p.rate-p.duration)>.002)throw Error('Invalid frozen clock')
 const bars=h.bars as number[]
 if(h.frequency!==140||h.maxCutDb!==18||h.rampBeats!==1||!Array.isArray(bars)||bars.length<3||!bars.every((v,i)=>Number.isFinite(v)&&(!i||v>bars[i-1])))throw Error('Invalid low-shelf evidence')
 const beat=60/c.bpm[0],anchors=bars.slice(0,-1).filter((v,i)=>v>=p.start&&bars[i+1]<=p.end+.065&&bars[i+1]-v>=beat)
 if(anchors.length<2||h.earlySource!==anchors[0]||h.lateSource!==anchors.at(-1)||h.lateSource-h.earlySource<beat||Math.abs(bars[bars.indexOf(h.lateSource)+1]-p.end)>.065)throw Error('Unsupported fixed bar anchors')
 const start=c.pre+(mode==='natural'?h.earlySource:h.lateSource)-p.start,finish=start+beat,end=c.pre+p.duration
 if(start<c.pre||finish>end)throw Error('Handoff outside frozen overlap')
 const a:Points=[[0,1],[c.pre,1],[end,0]],b:Points=[[0,0],[c.pre,0],[end,1]]
 return {start,finish,end,beat,a,b,settings:{frequency:140,maxCutDb:18,rampBeats:1},low:{a:[[0,0],[start,0],[finish,-18]] as Points,b:[[0,-18],[start,-18],[finish,0]] as Points}}
}
