import {correction,type Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export function cutCurves(pre:number,duration:number,edge:number,mode:Mode){
 if(![pre,duration,edge].every(Number.isFinite)||pre<0||duration<=0||edge<=0||edge>=duration)throw Error('短切换边缘不在固定交接内')
 const end=pre+duration,a:Points=[[0,1],[pre,1],[end,0]],b:Points=[[0,0],[pre,0],[end,1]]
 const bedA:Points=mode==='relay'?[[0,1],[end-edge,1],[end,0]]:a
 const bedB:Points=mode==='relay'?[[0,0],[end-edge,0],[end,1]]:b
 return {a:{master:bedA,voice:a,correction:correction(a,bedA)},b:{master:bedB,voice:b,correction:correction(b,bedB)}}
}
