import {correction,type Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export function yieldCurves(pre:number,duration:number,yieldEnd:number,mode:Mode){
 if(![pre,duration,yieldEnd].every(Number.isFinite)||pre<0||duration<=0||yieldEnd<=0||yieldEnd>=duration)throw Error('旋律让位时刻不在固定交接内')
 const a:Points=[[0,1],[pre,1],[pre+duration,0]],b:Points=[[0,0],[pre,0],[pre+duration,1]]
 const other:Points=mode==='relay'?[[0,1],[pre,1],[pre+yieldEnd,0],[pre+duration,0]]:a
 return {a:{master:a,correction:correction(other,a)},b:{master:b,correction:correction(b,b)}}
}
