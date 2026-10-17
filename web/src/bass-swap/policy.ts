import {finalBar,type Points} from '../melody-overlap/policy'
export type Mode='reference'|'swap'
export type Timing={duckStart:number;swapStart:number;swapEnd:number}
type Bar={start:number;end:number;beats:number[];valid:boolean}
export function bassTiming(bars:Bar[],start:number,end:number):Timing{
 const lastStart=finalBar(bars,start,end),i=bars.findIndex(b=>b.start===lastStart),previous=bars[i-1]
 if(!previous||Math.abs(previous.end-lastStart)>.001||finalBar([previous],start,previous.end)!==previous.start)throw Error('固定交接内缺少连续、完整的前一小节')
 return {duckStart:previous.start-start,swapStart:previous.beats[3]-start,swapEnd:lastStart-start}
}
export function bassCurves(pre:number,duration:number,timing:Timing,mode:Mode){
 const {duckStart,swapStart,swapEnd}=timing
 if(![pre,duration,duckStart,swapStart,swapEnd].every(Number.isFinite)||pre<0||duration<=0||duckStart<0||duckStart>=swapStart||swapStart>=swapEnd||swapEnd>duration)throw Error('贝斯交接时刻无效')
 const a:Points=[[0,1],[pre,1],[pre+duration,0]],b:Points=[[0,0],[pre,0],[pre+duration,1]]
 return {a:{rest:a,bass:mode==='swap'?[[0,1],[pre+duckStart,1],[pre+swapStart,.5],[pre+swapEnd,0]] as Points:a},b:{rest:b,bass:mode==='swap'?[[0,0],[pre+swapStart,0],[pre+swapEnd,1]] as Points:b}}
}
