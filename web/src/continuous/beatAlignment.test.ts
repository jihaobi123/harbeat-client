import {it,expect} from 'vitest'
import {localBeatGate} from './beatAlignment'
import type {Track,Window} from '../realtime/planner'

function track(id:string,barLength=2){
 return {id,reportId:id,provenance:{masterSha256:id,reportSha256:id,vocalSha256:id},
  alignment:{source:{reportId:id,masterSha256:id,reportSha256:id,vocalSha256:id},
   bars:Array.from({length:8},(_,i)=>({start:i*barLength,end:(i+1)*barLength,valid:true,beats:[0,1,2,3].map(j=>i*barLength+j*barLength/4)}))}} as unknown as Track
}
const window={start:0,end:4,bars:2} as Window
const cue={start:4,end:8,window,rate:1,duration:4}
it('keeps a fully aligned overlap even if the whole-song BPM needs review',()=>{
 const a=track('a'),b=track('b');a.warnings=['BPM 待确认']
 expect(localBeatGate(a,b,cue)).toBeNull()
})
it('rejects a half-speed local grid whose entry happens to land on a downbeat',()=>{
 expect(localBeatGate(track('a',4),track('b'),cue)).toMatch(/完整/)
})
it('checks interior beats, not just aligned start and end points',()=>{
 const a=track('a'),b=track('b');b.alignment!.bars[0].beats[2]+=.12
 expect(localBeatGate(a,b,cue)).toMatch(/65 ms/)
})
it('checks the time-stretched B grid and preserves full overlap length',()=>{
 const a=track('a'),b=track('b',2.2)
 expect(localBeatGate(a,b,{...cue,window:{...window,end:4.4},rate:1.1})).toBeNull()
})
it('rejects broken or unbound local evidence instead of silently accepting',()=>{
 const a=track('a'),b=track('b');a.alignment!.bars[2].valid=false
 expect(localBeatGate(a,b,cue)).not.toBeNull()
 a.alignment!.bars[2].valid=true;b.alignment!.source.masterSha256='another'
 expect(localBeatGate(a,b,cue)).not.toBeNull()
})
