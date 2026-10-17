export type KeyEvidence={camelot:string;needsReview:boolean;verified:boolean;masterSha256:string;runId:string}
export type KeySource={masterSha256:string;runId:string;key?:KeyEvidence}
export type Candidate<T>=KeySource&{id:string;score:number;plan:T}
function usable(source:KeySource,allowProvisional:boolean){
 const k=source.key
 if(!k||!source.masterSha256||!source.runId||k.masterSha256!==source.masterSha256||k.runId!==source.runId)return null
 if(!allowProvisional&&(!k.verified||k.needsReview))return null
 const match=/^([1-9]|1[0-2])([AB])$/.exec(k.camelot)
 return match?{number:Number(match[1]),mode:match[2]}:null
}
export function harmonicBonus(from:KeySource,to:KeySource,allowProvisional=false){
 const a=usable(from,allowProvisional),b=usable(to,allowProvisional)
 if(!a||!b)return 0
 if(a.number===b.number)return a.mode===b.mode?.08:.064
 const difference=Math.abs(a.number-b.number)
 return a.mode===b.mode&&Math.min(difference,12-difference)===1?.064:0
}
export function rankFrozen<T>(from:KeySource,candidates:readonly Candidate<T>[],allowProvisional=false){
 return candidates.map((c,order)=>{
  if(!Number.isFinite(c.score))throw Error('Base score must be finite')
  const bonus=harmonicBonus(from,c,allowProvisional)
  return {...c,bonus,rankScore:c.score+bonus,order}
 }).sort((a,b)=>b.rankScore-a.rankScore||a.order-b.order)
}
