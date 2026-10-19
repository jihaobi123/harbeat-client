import type {Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
const validBar=(b:any)=>!!b?.valid&&Array.isArray(b.beats)&&b.beats.length===4&&[b.start,b.end,...b.beats].every(Number.isFinite)&&b.end>b.start&&Math.abs(b.beats[0]-b.start)<=.001&&b.beats.every((t:number,i:number)=>t>=b.start&&t<b.end&&(!i||t>b.beats[i-1]))
export function accentPlan(c:any,mode:Mode){
 const p=c.plan,f=c.accent
 if(!['natural','relay'].includes(mode)||c.baselineBass!=='reference'||!p||!f||![c.pre,c.post,...c.bpm,p.start,p.end,p.duration,p.rate,p.window?.start,p.window?.end].every(Number.isFinite)||c.pre<0||c.post<=0||c.bpm.some((x:number)=>x<=0)||p.duration<=0||p.rate<=0||Math.abs(p.rate-1)>.05||Math.abs(p.end-p.start-p.duration)>.002||Math.abs((p.window.end-p.window.start)/p.rate-p.duration)>.002)throw Error('Invalid frozen source clock')
 const sr=44100,end=c.pre+p.duration,start=Math.round((c.pre+f.targetBar?.start-p.start)*sr)/sr,finish=Math.round(end*sr)/sr
 if(!validBar(f.sourceBar)||!validBar(f.targetBar)||typeof f.donorTrackId!=='string'||!f.donorTrackId||[p.from,p.to].includes(f.donorTrackId)||f.targetBar.start<p.start||Math.abs(f.targetBar.end-p.end)>.065||![f.start,f.finish,f.duration,f.rate,f.frames,f.sourceStart,f.sourceEnd,f.sourceOrigin].every(Number.isFinite)||f.start!==start||f.finish!==finish||f.frames!==Math.round((finish-start)*sr)||!Number.isInteger(f.frames)||Math.abs(f.duration-f.frames/sr)>1e-12||f.duration<=.01||f.sourceStart!==f.sourceBar.start||f.sourceEnd!==f.sourceBar.end||f.sourceStart<f.sourceOrigin||Math.abs(f.rate-(f.sourceEnd-f.sourceStart)/f.duration)>1e-12||Math.abs(f.rate-1)>.06||f.relativeGain!==.25||f.edgeSeconds!==.005||f.count!==1||f.lookaheadSeconds!==1)throw Error('Invalid fixed third drum bar')
 const errors=f.sourceBar.beats.map((t:number,i:number)=>Math.abs((t-f.sourceStart)/f.rate-(f.targetBar.beats[i]-f.targetBar.start)))
 if(!Array.isArray(f.mappedBeatErrors)||f.mappedBeatErrors.length!==4||errors.some((v:number,i:number)=>v>.065||Math.abs(v-f.mappedBeatErrors[i])>1e-9)||start<c.pre||finish>end+1/sr)throw Error('Unusable donor beat mapping')
 const a:Points=[[0,1],[c.pre,1],[end,0]],b:Points=[[0,0],[c.pre,0],[end,1]]
 return {start,finish,end,a,b,cGain:mode==='relay'?.25:0}
}
