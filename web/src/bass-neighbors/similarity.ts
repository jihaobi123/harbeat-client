export type NeighborVector={bpm:[number,number];sourceTags:string[];destinationTags:string[];styles:[string,string];vocals:[number,number];bars:number;harmonicBonus:number}
const overlap=(a:string[],b:string[])=>a.some(x=>b.some(y=>x.toLowerCase()===y.toLowerCase()))
export function evaluateNeighbor(anchor:NeighborVector,candidate:NeighborVector,sourceFamily:string[]){
 const reasons:string[]=[]
 const numbers=[...anchor.bpm,...candidate.bpm,...anchor.vocals,...candidate.vocals,anchor.bars,candidate.bars,anchor.harmonicBonus,candidate.harmonicBonus]
 if(!numbers.every(Number.isFinite)||[...anchor.bpm,...candidate.bpm,anchor.bars,candidate.bars].some(x=>x<=0))return {eligible:false,reasons:['invalid-evidence'],distance:null,components:{}}
 if(candidate.bpm.some((x,i)=>Math.abs(x/anchor.bpm[i]-1)>.1000001))reasons.push('tempo-distance')
 if(!overlap(candidate.sourceTags,sourceFamily))reasons.push('source-family')
 if(candidate.vocals.some((x,i)=>anchor.vocals[i]>=.75?x<.75:anchor.vocals[i]<=.25?x>.25:Math.abs(x-anchor.vocals[i])>.25))reasons.push('vocal-direction')
 const components={tempo:4*candidate.bpm.reduce((s,x,i)=>s+Math.abs(x/anchor.bpm[i]-1),0),sourceTags:overlap(anchor.sourceTags,candidate.sourceTags)?0:.25,destinationTags:anchor.destinationTags.length?(overlap(anchor.destinationTags,candidate.destinationTags)?0:.35):0,modelStyles:candidate.styles.reduce((s,x,i)=>s+(x===anchor.styles[i]?0:.1),0),vocals:.4*candidate.vocals.reduce((s,x,i)=>s+Math.abs(x-anchor.vocals[i]),0),bars:.2*Math.abs(Math.log(candidate.bars/anchor.bars)),harmonicCategory:(candidate.harmonicBonus>0)===(anchor.harmonicBonus>0)?0:.1}
 return {eligible:reasons.length===0,reasons,distance:reasons.length?null:Object.values(components).reduce((s,x)=>s+x,0),components}
}
type FrozenWindow={id:string;from:string;to:string;start:number;end:number;rate:number;window:{start:number;end:number}}
type RejectedWindow={planId?:string;side?:string;trackId?:string;sourceStart?:number;sourceEnd?:number;rate?:number}
export function isRejectedWindow(p:FrozenWindow,rejections:RejectedWindow[]){
 return rejections.some(x=>x.planId===p.id||x.side==='a'&&x.trackId===p.from&&Math.abs(x.sourceStart!-p.start)<.001&&Math.abs(x.sourceEnd!-p.end)<.001||x.side==='b'&&x.trackId===p.to&&x.rate!==undefined&&Math.abs(x.rate-p.rate)<1e-12&&Math.abs(x.sourceStart!-p.window.start)<.001&&Math.abs(x.sourceEnd!-p.window.end)<.001)
}
