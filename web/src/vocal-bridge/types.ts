import type {Asset} from '../realtime/planner'
import type {V30Eq} from '../v30/types'
import type {BridgeCue} from './policy'
export type Mode='reference'|'bridge'
export type BridgeCase=BridgeCue&{id:string;aTitle:string;bTitle:string;label:string;style:string;pre:number;post:number;restore:number;eq:V30Eq;assets:Record<'aMaster'|'aVocal'|'bMaster'|'bVocal',Asset>}
export type PlayerState={status:'idle'|'loading'|'playing'|'paused'|'complete'|'error';message:string;position:number;mode:Mode;caseId:string;peak?:number;minimumLimiterGain?:number}
