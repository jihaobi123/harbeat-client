import {correction,type Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export function cutCurves(pre:number,duration:number,edge:number,mode:Mode){
 if(![pre,duration,edge].every(Number.isFinite)||pre<=edge||duration<=edge||edge<=0||edge>.01)throw Error('短切边缘超出固定范围')
 const end=pre+duration,a:Points=[[0,1],[pre,1],[end,0]],b:Points=[[0,0],[pre,0],[end,1]]
 const bedA:Points=mode==='relay'?[[0,1],[pre-edge,1],[pre,0],[end,0]]:a
 const bedB:Points=mode==='relay'?[[0,0],[pre,0],[pre+edge,1]]:b
 return {a:{master:bedA,voice:a,correction:correction(a,bedA)},b:{master:bedB,voice:b,correction:correction(b,bedB)}}
}
export function validateBoundary(c:any){
 const p=c.plan,m=c.boundary,bpm=c.bpm,r=bpm?.[1]/bpm?.[0],finite=(v:unknown)=>typeof v==='number'&&Number.isFinite(v)
 if(!m||m.voicePolicy!=='original-linear-fades'||m.sectionTruth!=='model-candidate'||!bpm?.every((x:number)=>finite(x)&&x>0)||Math.abs(bpm[1]-bpm[0])<20||Math.min(Math.abs(r-1),Math.abs(1/r-1))<.18||Math.min(Math.abs(r/2-1),Math.abs(r/.5-1))<.1)throw Error('本轮只纳入远离近速与半倍速的大跨度候选')
 if(![p?.start,p?.end,p?.duration,p?.window?.start,p?.window?.end,c.pre,c.post,c.cutEdgeSeconds,m.aDownbeat,m.bDownbeat,m.aSection?.start,m.aSection?.end,m.bSection?.start,m.bSection?.end].every(finite)||p.rate!==1||c.pre<=0||c.post<=0||p.start<c.pre||p.duration<=2.5||p.duration>=8||c.cutEdgeSeconds!==.005||Math.abs(p.end-p.start-p.duration)>.00001||Math.abs(p.window.end-p.window.start-p.duration)>.00001||p.start!==m.aDownbeat||p.window.start!==m.bDownbeat||Math.abs(m.aSection.end-p.start)>.15||Math.abs(m.bSection.start-p.window.start)>.15)throw Error('固定原速接点或段落候选不成立')
 const a=m.aObservedBar
 if(!a?.valid||!Array.isArray(a.beats)||a.beats.length!==4||![a.start,a.end,...a.beats].every(finite)||a.end<=a.start||Math.abs(a.start-a.beats[0])>.001||Math.abs(a.start-p.start)>.065||a.beats.some((v:number,j:number)=>v<a.start||v>=a.end||j>0&&v<=a.beats[j-1]))throw Error('A 原始锚点缺少相邻实际小节依据')
 if(!Array.isArray(m.bBars)||m.bBars.length!==2||p.window.bars!==2)throw Error('B 必须从两个完整实际小节开始')
 m.bBars.forEach((b:any,i:number)=>{if(!b.valid||![b.start,b.end,...b.beats].every(finite)||b.end<=b.start||b.beats.length!==4||Math.abs(b.start-b.beats[0])>.001||b.beats.some((v:number,j:number)=>v<b.start||v>=b.end||j>0&&v<=b.beats[j-1])||i===0&&b.start!==p.window.start||i===1&&Math.abs(b.start-m.bBars[0].end)>.001)throw Error('B 实际小节不完整')})
 if(Math.abs(m.bBars[1].end-p.window.end)>.00001)throw Error('B 小节终点与固定来源不一致')
 for(const k of ['aProtected','bProtected'])if(!Array.isArray(m[k])||m[k].some((x:any)=>!Array.isArray(x)||x.length!==2||!x.every(finite)||x[1]<=x[0]))throw Error('人声保护依据无效')
 if(m.aProtected.some(([s,e]:number[])=>s<p.end+.08&&e>p.start-.3)||m.bProtected.some(([s,e]:number[])=>s<p.window.start-.001&&e>p.window.start-.08))throw Error('固定接点仍有受保护人声或截断短语')
 cutCurves(c.pre,p.duration,c.cutEdgeSeconds,'relay')
}
