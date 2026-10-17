import {bassCurves,type Timing} from '../bass-swap/policy'
import type {Points} from '../melody-overlap/policy'
export type Mode='reference'|'stem'|'eq'
export const SETTINGS=Object.freeze({frequency:140,maxCutDb:18})
export function treatment(pre:number,duration:number,timing:Timing,mode:Mode){
 const curves=bassCurves(pre,duration,timing,mode==='stem'?'swap':'reference')
 const low:{a:Points;b:Points}=mode==='eq'?{a:[[0,0],[pre+timing.duckStart,0],[pre+timing.swapStart,-6],[pre+timing.swapEnd,-SETTINGS.maxCutDb]],b:[[0,-SETTINGS.maxCutDb],[pre+timing.swapStart,-SETTINGS.maxCutDb],[pre+timing.swapEnd,0]]}:{a:[[0,0]],b:[[0,0]]}
 return {curves,low,settings:SETTINGS}
}
