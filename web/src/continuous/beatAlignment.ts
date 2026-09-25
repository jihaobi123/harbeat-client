import type {Track,TimingGate} from '../realtime/planner'
import {sourceBound} from '../v30/planner'
import {planVocalOverlap} from '../vocal-overlap/planner'

// Reuse the existing 65 ms downbeat tolerance for every observed beat in the
// overlap. A whole-song BPM warning alone neither rejects nor approves a cue.
const TOLERANCE=.065
function localBeats(track:Track,start:number,end:number,count:number){
 if(!sourceBound(track)||track.alignment?.source.reportId!==track.reportId)return null
 const bars=track.alignment!.bars
 const first=bars.findIndex(b=>Math.abs(b.start-start)<=TOLERANCE)
 if(first<0)return null
 const rows=bars.slice(first,first+count)
 if(rows.length!==count||Math.abs(rows.at(-1)!.end-end)>TOLERANCE)return null
 if(rows.some((b,i)=>!b.valid||b.beats.length!==4||!Number.isFinite(b.end)||
   Math.abs(b.beats[0]-b.start)>.001||b.beats.some((v,j)=>!Number.isFinite(v)||v>=b.end||j>0&&v<=b.beats[j-1])||
   i>0&&Math.abs(rows[i-1].end-b.start)>.001))return null
 return [...rows.flatMap(b=>b.beats),rows.at(-1)!.end]
}
export const localBeatGate:TimingGate=(a,b,cue)=>{
 const from=localBeats(a,cue.start,cue.end,cue.window.bars)
 const to=localBeats(b,cue.window.start,cue.window.end,cue.window.bars)
 if(!from||!to||from.length!==to.length)return '重叠段缺少同一拍速下连续、完整的实测拍点，跳过此接点'
 const error=Math.max(...from.map((beat,i)=>Math.abs(beat-(cue.start+(to[i]-cue.window.start)/cue.rate))))
 return !Number.isFinite(error)||error>TOLERANCE?'重叠段局部拍点偏差超过 65 ms，跳过此接点':null
}
export const planContinuous:typeof planVocalOverlap=(a,tracks,position,intent,ready,budget=18,requireReady=true)=>
 planVocalOverlap(a,tracks,position,intent,ready,budget,requireReady,localBeatGate)
