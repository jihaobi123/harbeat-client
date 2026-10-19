import {correction,valueAt,type Points} from '../melody-overlap/policy'
export type Mode='natural'|'relay'
export function gapCurves(pre:number,duration:number,pauseSeconds:number,edge:number,mode:Mode){
 if(![pre,duration,pauseSeconds,edge].every(Number.isFinite)||pre<0||duration<=0||pauseSeconds<=0||edge<=0||pauseSeconds+edge>=duration)throw Error('伴奏留白必须位于固定交接内')
 const end=pre+duration,gapStart=end-pauseSeconds,downStart=gapStart-edge
 const a:Points=[[0,1],[pre,1],[end,0]],b:Points=[[0,0],[pre,0],[end,1]]
 const bedA:Points=mode==='relay'?[[0,1],[pre,1],[downStart,valueAt(a,downStart)],[gapStart,0],[end,0]]:a
 const bedB:Points=mode==='relay'?[[0,0],[pre,0],[downStart,valueAt(b,downStart)],[gapStart,0],[end,0],[end+edge,1]]:b
 return {a:{master:bedA,voice:a,correction:correction(a,bedA)},b:{master:bedB,voice:b,correction:correction(b,bedB)}}
}
