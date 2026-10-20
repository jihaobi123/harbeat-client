export const canArm=(plan:{from:string;start:number},currentId:string|null,position:number)=>plan.from===currentId&&Number.isFinite(position)&&plan.start>=position+.5
export const contextForSource=(at:number,offset:number,source:number)=>at+source-offset
export const adoptedPosition=(plan:{bEnd:number},handoffContext:number,now:number)=>plan.bEnd+Math.max(0,now-handoffContext)
