import {it,expect} from 'vitest'
import {automaticAction} from './automatic'
const song={position:0,duration:200,playing:true,busy:false,pending:false,status:'failed' as const,hasSelection:true}
it('retries a transient no-plan while the current song continues, with a delay between attempts',()=>{
 expect(automaticAction(song,12)).toBeNull()
 expect(automaticAction({...song,position:12},12)).toBe('prepare')
 expect(automaticAction({...song,position:13},24)).toBeNull()
})
it('tries another selection when the selected song has no usable tail and permits a later mix attempt',()=>{
 expect(automaticAction({...song,position:172},0)).toBe('alternative')
 expect(automaticAction({...song,position:179,status:'ready'},178)).toBe('mix')
 expect(automaticAction({...song,position:180,status:'ready'},182)).toBeNull()
 expect(automaticAction({...song,position:183,status:'ready'},182)).toBe('mix')
})
it('never starts automatic work during pause, an active handoff, loading, or another request',()=>{
 for(const change of [{playing:false},{busy:true},{pending:true},{status:'loading' as const},{status:'queued' as const}])expect(automaticAction({...song,position:180,...change},0)).toBeNull()
 expect(automaticAction({...song,position:180,status:'idle',hasSelection:false},0)).toBe('alternative')
})

it('uses the prepared cue deadline instead of waiting for the last 22 seconds',()=>{
 const s={...song,duration:388,position:345,status:'ready' as const,plannedStart:352}
 expect(automaticAction(s,0)).toBe('mix')
 expect(automaticAction({...s,position:330},0)).toBeNull()
})

it('a prepared cue due now is not suppressed by the old selection or retry throttle',()=>{
 expect(automaticAction({...song,position:105,duration:150,status:'ready',plannedStart:106,futurePreparation:true},117)).toBe('mix')
})

it('uses current selection state after the track-change effect starts preparation, not an idle render snapshot',async()=>{
 const {selectionSnapshot}=await import('./automatic')
 const rendered={id:null,status:'idle' as const,error:''},live={id:'best',status:'loading' as const,error:''}
 const selected=selectionSnapshot(rendered,{state:live})
 expect(automaticAction({position:0,duration:100,playing:true,busy:false,pending:false,status:selected.status,hasSelection:!!selected.id,futurePreparation:true},0)).toBeNull()
})
