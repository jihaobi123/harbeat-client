import {bassCurves,type Timing} from '../bass-swap/policy'
import {filterPlan} from '../melody-filter/policy'
export type Mode='original'|'single'|'combined'
export const modes:Mode[]=['original','single','combined']
export function combinationPlan(c:any,mode:Mode){
 if(!modes.includes(mode))throw Error('Unknown combination arm')
 const filter=filterPlan(c,mode==='combined'?'relay':'natural')
 const bass=bassCurves(c.pre,c.plan.duration,c.timing as Timing,mode==='original'?'reference':'swap')
 return {start:filter.start,end:filter.end,bass,filter}
}
