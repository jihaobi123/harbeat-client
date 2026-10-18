import {bassCurves,type Timing} from '../bass-swap/policy'
import type {Points} from '../melody-overlap/policy'
export type Mode='natural'|'loop'
export type BaselineBass='reference'|'stem'
export function treatment(pre:number,duration:number,timing:Timing,baseline:BaselineBass,mode:Mode){
 const curves=bassCurves(pre,duration,timing,baseline==='stem'?'swap':'reference')
 // Offline loop PCM equals natural PCM outside the replacement window, so these
 // complementary paths cancel there without adding another transition envelope.
 const drum:{natural:Points;loop:Points}=mode==='loop'
  ?{natural:curves.a.rest.map(([t,g])=>[t,g===0?0:-g]),loop:curves.a.rest.map(([t,g])=>[t,g])}
  :{natural:[[0,0]],loop:[[0,0]]}
 return {curves,drum}
}
