import {planNext,type Track,type Intent} from '../realtime/planner'

/** Prepare a complete handoff near the last measured bars while there is still
 * time to load it. Widen backwards only when the later region has no valid cue.
 * Candidate scoring and full overlap length belong to the supplied planner.
 */
export function planAutomatic(planner:typeof planNext,a:Track,tracks:Track[],position:number,intent:Intent,ready:Set<string>,requireReady=false){
 const last=a.bars.filter(t=>t<a.duration-.1).at(-1)??a.duration-.1
 const starts:number[]=[]
 for(let end=last;;end-=15){const start=Math.max(position,end-30);starts.push(start);if(start===position)break}
 let result:ReturnType<typeof planNext>|undefined
 for(const start of new Set(starts)){
  result=planner(a,tracks,start,intent,ready,Math.max(0,Math.min(last,start+30)-start+.0001),requireReady)
  if(result.best)return {...result,planningPosition:start}
 }
 return {...result!,planningPosition:position}
}
