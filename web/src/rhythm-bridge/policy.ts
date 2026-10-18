import {correction,type Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export function bridgeCurves(pre:number,duration:number,bridgeStart:number,mode:Mode){
 if(![pre,duration,bridgeStart].every(Number.isFinite)||pre<0||duration<=0||bridgeStart<=0||bridgeStart>=duration)throw Error('鼓组交接边界不在固定重叠内')
 const a:Points=[[0,1],[pre,1],[pre+duration,0]],b:Points=[[0,0],[pre,0],[pre+duration,1]]
 const drumsA:Points=mode==='relay'?[[0,1],[pre+bridgeStart,1],[pre+duration,0]]:a
 const drumsB:Points=mode==='relay'?[[0,0],[pre+bridgeStart,0],[pre+duration,1]]:b
 return {a:{master:a,correction:correction(drumsA,a)},b:{master:b,correction:correction(drumsB,b)}}
}
