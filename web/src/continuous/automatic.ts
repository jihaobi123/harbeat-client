import type {SelectionState} from './selection'
type Snapshot={position:number;duration:number;playing:boolean;busy:boolean;pending:boolean;status:SelectionState['status'];hasSelection:boolean;plannedStart?:number|null;futurePreparation?:boolean}
/** Retry transient cue misses as source time advances; never spin while the clock is paused. */
export function automaticAction(s:Snapshot,nextAttemptAt:number):'prepare'|'alternative'|'mix'|null{
 const due=s.status==='ready'&&s.plannedStart!=null&&s.position>=s.plannedStart-8&&s.position<=s.plannedStart-.25
 if(!s.playing||s.busy||s.pending||s.position<nextAttemptAt&&!due||s.status==='loading'||s.status==='queued')return null
 const left=s.duration-s.position
 if(left<1)return null
 if(!s.hasSelection)return 'alternative'
 if(s.futurePreparation&&s.status==='failed')return 'alternative'
 if(s.futurePreparation&&s.status==='ready'&&s.plannedStart==null)return 'prepare'
 if(s.status==='failed')return left<=30?'alternative':'prepare'
 if(s.status==='ready'&&(s.plannedStart!=null?s.position>=s.plannedStart-8:left<=22))return 'mix'
 return null
}

/** Call after cancelling only automatic work; preserve any remaining manual request. */
export function canPrepareAfterAutoOff(player:{current:unknown;pending:unknown;busy:boolean;gate:{locked:boolean}},id:string|null){
 return !!player.current&&!!id&&!player.pending&&!player.busy&&!player.gate.locked
}
export function selectionSnapshot(rendered:SelectionState,controller:{state:SelectionState}|null){return controller?.state||rendered}
