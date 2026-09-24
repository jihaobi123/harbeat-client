import type {SelectionState} from './selection'
type Snapshot={position:number;duration:number;playing:boolean;busy:boolean;pending:boolean;status:SelectionState['status'];hasSelection:boolean}
/** Retry transient cue misses as source time advances; never spin while the clock is paused. */
export function automaticAction(s:Snapshot,nextAttemptAt:number):'prepare'|'alternative'|'mix'|null{
 if(!s.playing||s.busy||s.pending||s.position<nextAttemptAt||s.status==='loading'||s.status==='queued')return null
 const left=s.duration-s.position
 if(left<1)return null
 if(!s.hasSelection)return 'alternative'
 if(s.status==='failed')return left<=30?'alternative':'prepare'
 if(s.status==='ready'&&left<=22)return 'mix'
 return null
}
