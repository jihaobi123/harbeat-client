export type Mode='natural'|'relay'
import type {Points} from '../melody-overlap/policy'
export function filterPlan(c:any,mode:Mode){
 const p=c.plan,f=c.filter,bar=f?.sourceBar
 if(!p||!f||![c.pre,c.post,p.start,p.end,p.duration,p.rate,p.window?.start,p.window?.end,f.sourceStart].every(Number.isFinite)||c.pre<0||c.post<=0||p.duration<=0||p.rate<=0||Math.abs(p.rate-1)>.05||Math.abs(p.end-p.start-p.duration)>.002||Math.abs((p.window.end-p.window.start)/p.rate-p.duration)>.002)throw Error('Invalid frozen source clock')
 if(f.type!=='highpass'||f.startHz!==20||f.endHz!==1800||!Number.isFinite(f.Q)||Math.abs(f.Q-Math.SQRT1_2)>1e-12||f.edgeSeconds!==.02||!bar?.valid||!Array.isArray(bar.beats)||bar.beats.length!==4||![bar.start,bar.end,...bar.beats].every(Number.isFinite)||bar.end<=bar.start||Math.abs(bar.beats[0]-bar.start)>.001||bar.beats.some((x:number,i:number)=>x<bar.start||x>=bar.end||i>0&&x<=bar.beats[i-1])||Math.abs(bar.start-f.sourceStart)>.065||Math.abs(bar.end-p.end)>.065)throw Error('Invalid fixed final-bar filter evidence')
 const end=c.pre+p.duration,start=c.pre+f.sourceStart-p.start
 if(start<c.pre||start+.02>=end)throw Error('Filter outside original final bar')
 const a:Points=[[0,1],[c.pre,1],[end,0]],b:Points=[[0,0],[c.pre,0],[end,1]]
 return {start,end,a,b,Q:f.Q,Qdb:20*Math.log10(f.Q),mix:(mode==='relay'?[[0,0],[start,0],[start+.02,1],[end,1]]:[[0,0]]) as Points,frequency:(mode==='relay'?[[0,20],[start,20],[end,1800]]:[[0,20]]) as Points}
}
