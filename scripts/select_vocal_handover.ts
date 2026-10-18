import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {planAutomaticQuality} from '../web/src/continuous/qualityPlan'
import {buildV30Eq} from '../web/src/v30/eq'
import {bassTiming} from '../web/src/bass-swap/policy'
import {validateRelay} from '../web/src/vocal-bed/policy'
import {requireBoundVocals} from '../web/src/vocal-overlap/planner'
import {localBeatGate} from '../web/src/continuous/beatAlignment'
const root=path.resolve(process.argv[2]),w=path.dirname(root),read=(p:string)=>JSON.parse(fs.readFileSync(p,'utf8'))
const tracks=fs.readdirSync(path.join(w,'bass-generalization-20261017/details')).filter(f=>f.endsWith('.json')).map(f=>read(path.join(w,'bass-generalization-20261017/details',f)).track)
const shortlist=read(path.join(w,'vocal-endpoints-20261018/expanded-shortlist.json')),titles=[...new Set(shortlist.map((x:any)=>x[1]))].slice(0,12),audit:any[]=[],cases:any[]=[]
for(const title of titles){
 if(title==="Doin' It")continue
 const a=tracks.find(t=>t.title===title),pool=tracks.filter(b=>b.id!==a.id&&Math.abs(a.bpm/b.bpm-1)<=.06)
 const r=planAutomaticQuality(a,pool,0,{kind:'next'},new Set(),false),eligible:any[]=[]
 for(const p of r.candidates){
  const b=tracks.find(t=>t.id===p.to),av=a.vocals.filter(([s,e]:number[])=>s<p.end&&e>p.start)
  const relay={aVoiceEnd:Math.max(...av.map((x:number[])=>x[1])),bEntry:p.window.start,bEnd:p.window.end,aIntervals:a.vocals,bIntervals:b.vocals}
  try{
   requireBoundVocals(a);requireBoundVocals(b);const issue=localBeatGate(a,b,p);if(issue)throw Error(issue)
   validateRelay(p.start,p.end,p.duration,relay)
   const quiet=shortlist.find((x:any)=>x[2]===a.id&&Math.abs(x[3]-relay.aVoiceEnd)<.01&&Math.abs(x[4]-p.end)<.15)
   if(!quiet)continue
   const plan={...p,v30Eq:p.v30Eq||buildV30Eq(a,b,p)}
   eligible.push({id:'handover-candidate-'+String(cases.length+1).padStart(2,'0'),anchor:false,slot:{id:'vocal',label:'独立人声交接'},aTitle:a.title,bTitle:b.title,bpm:[a.bpm,b.bpm],pre:4,post:8,plan,planSha256:crypto.createHash('sha256').update(JSON.stringify(plan)).digest('hex'),timing:bassTiming(a.alignment.bars,p.start,p.end),baselineBass:'reference',relay,quietProxy:quiet,score:p.score})
  }catch{}
 }
 eligible.sort((a,b)=>b.score-a.score||a.plan.id.localeCompare(b.plan.id))
 if(eligible.length)cases.push(eligible[0])
 audit.push({source:title,plans:r.candidates.length,eligibleCount:eligible.length,selectedPlan:eligible[0]?.plan.id??null})
}
const ids=new Set(cases.flatMap(c=>[c.plan.from,c.plan.to]))
const chosen=tracks.filter(t=>ids.has(t.id))
const selection={schema:'harbeat.vocal-handover-selection.v1',frozenAt:new Date().toISOString(),cases,tracks:chosen.map(t=>({id:t.id,title:t.title,reportId:t.reportId,provenance:t.provenance})),audit:{candidateSources:titles,scan:audit,rule:'One highest-scoring existing-policy eligible plan per source; frozen before endpoint inference. No second cue after rejection. Preserve source order; first two new passing sources plus existing Doin It anchor.'}}
fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify(selection,null,2)+'\n');fs.writeFileSync(path.join(root,'tracks.json'),JSON.stringify(chosen))
const requests=Object.fromEntries(chosen.map(t=>{
 const outgoing=cases.find(c=>c.plan.from===t.id),incoming=cases.filter(c=>c.plan.to===t.id)
 const starts=[...(outgoing?[outgoing.plan.start-4]:[]),...incoming.map(c=>c.plan.window.start-1)],ends=[...(outgoing?[outgoing.plan.end+5]:[]),...incoming.map(c=>c.plan.window.end+2)]
 const cs=outgoing?.plan.start??incoming[0].plan.window.start,ce=outgoing?.plan.end??incoming[0].plan.window.end
 return [t.title,[Math.min(...starts),Math.max(...ends),cs,ce]]
}))
fs.writeFileSync(path.join(root,'context-request.json'),JSON.stringify(requests,null,2))
console.log(cases.map(c=>({id:c.id,pair:c.aTitle+' → '+c.bTitle,start:c.plan.start,end:c.plan.end,window:[c.plan.window.start,c.plan.window.end]})))
