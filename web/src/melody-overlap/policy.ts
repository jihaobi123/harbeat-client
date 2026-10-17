export type Points=[number,number][]
export type Mode='reference'|'short'
export function valueAt(points:Points,t:number){
 if(t<=points[0][0])return points[0][1]
 for(let i=1;i<points.length;i++){const [end,value]=points[i], [start,previous]=points[i-1];if(t<=end)return previous+(value-previous)*(t-start)/(end-start)}
 return points.at(-1)![1]
}
export function correction(layer:Points,melody:Points):Points{
 return [...new Set([...layer,...melody].map(p=>p[0]))].sort((a,b)=>a-b).map(t=>[t,valueAt(layer,t)-valueAt(melody,t)])
}
export function finalBar(bars:{start:number;end:number;beats:number[];valid:boolean}[],start:number,end:number){
 if(![start,end].every(Number.isFinite)||end<=start)throw Error('固定计划的范围无效')
 const bar=bars.find(b=>Math.abs(b.end-end)<=.065)
 if(!bar||!bar.valid||!Number.isFinite(bar.start)||!Number.isFinite(bar.end)||bar.start<start||bar.start>=bar.end||bar.beats.length!==4||Math.abs(bar.beats[0]-bar.start)>.001||bar.beats.some((v,i)=>!Number.isFinite(v)||v<bar.start||v>=bar.end||i>0&&v<=bar.beats[i-1]))throw Error('固定接点内缺少完整、已核验的末尾小节')
 return bar.start
}
export function curves(pre:number,duration:number,shortStart:number,mode:Mode){
 if(![pre,duration,shortStart].every(Number.isFinite)||pre<0||duration<=0||shortStart<0||shortStart>=duration)throw Error('分轨交接时刻无效')
 const end=pre+duration
 const a:Points=[[0,1],[pre,1],[end,0]],b:Points=[[0,0],[pre,0],[end,1]]
 return {a:{voice:a,drums:a,melody:mode==='short'?[[0,1],[pre+shortStart,1],[end,0]] as Points:a},b:{voice:b,drums:b,melody:mode==='short'?[[0,0],[pre+shortStart,0],[end,1]] as Points:b}}
}
