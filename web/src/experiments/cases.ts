import type {Track,Plan} from '../realtime/planner'
import {planTrial,type FixedCase} from './trials'
export function comparisonKey(...parts:string[]){return JSON.stringify(parts)}
export function buildRankingCases(tracks:Track[]){
 return [...tracks].sort((a,b)=>a.title.localeCompare(b.title)).flatMap(a=>[5,60].filter(position=>position+30<a.duration).map(position=>({id:`rank:${a.id}:${position}`,aId:a.id,position,label:`${a.title} · ${position} 秒`})))
}
function alternate(a:Track,b:Track,p:Plan){
 return b.windows.filter(w=>w.id!==p.window.id&&w.bars===4&&w.end+12<b.duration).find(w=>{const asset=w.variants[a.id];return asset&&Math.abs(asset.duration-p.duration)<1/44100&&Math.abs(asset.rate-p.rate)<1e-8})
}
/** Balanced by outgoing track and directed pair; never select cases by observed improvement. */
export function buildFixedCases(tracks:Track[],limit=12):FixedCase[]{
 const pools=tracks.map((a,index)=>{
  const list:FixedCase[]=[]
  for(let step=1;step<tracks.length;step++){
   const b=tracks[(index+step)%tracks.length]
   for(const position of [15,45,60]){
    const p=planTrial(a,tracks,position,'baseline',b.id).candidates
      .filter(p=>p.window.bars===4&&p.midDuck&&Math.min(...a.bars.map(t=>Math.abs(t-(p.end-p.duration/2))))<=.065&&alternate(a,b,p))
      .sort((x,y)=>x.end-y.end||x.window.start-y.window.start)[0]
    if(p){list.push({id:`fixed:${a.id}:${b.id}`,aId:a.id,bId:b.id,position,windowId:p.window.id,end:p.end,alternateWindowId:alternate(a,b,p)!.id});break}
   }
  }
  return list
 })
 const result:FixedCase[]=[]
 for(let round=0;round<tracks.length;round++)for(const list of pools)if(list[round]&&result.length<limit)result.push(list[round])
 return result
}
