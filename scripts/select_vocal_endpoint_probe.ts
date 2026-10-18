import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {planAutomaticQuality} from '../web/src/continuous/qualityPlan'
import {buildV30Eq} from '../web/src/v30/eq'
import {bassTiming} from '../web/src/bass-swap/policy'
import {validateRelay} from '../web/src/vocal-bed/policy'
const w=path.resolve('../../work'),root=path.join(w,'vocal-endpoints-20261018'),read=(p:string)=>JSON.parse(fs.readFileSync(p,'utf8'))
const tracks=fs.readdirSync(path.join(w,'bass-generalization-20261017/details')).filter(f=>f.endsWith('.json')).map(f=>read(path.join(w,'bass-generalization-20261017/details',f)).track)
const shortlist=read(path.join(root,'expanded-shortlist.json')),titles=[...new Set(shortlist.map((x:any)=>x[1]))].slice(0,12),audit:any[]=[],eligible:any[]=[]
for(const title of titles){
 const a=tracks.find(t=>t.title===title),pool=tracks.filter(b=>b.id!==a.id&&Math.abs(a.bpm/b.bpm-1)<=.06)
 const r=planAutomaticQuality(a,pool,0,{kind:'next'},new Set(),false)
 for(const p of r.candidates){
  const b=tracks.find(t=>t.id===p.to),av=a.vocals.filter(([s,e]:number[])=>s<p.end&&e>p.start)
  const relay={aVoiceEnd:Math.max(...av.map((x:number[])=>x[1])),bEntry:p.window.start,bEnd:p.window.end,aIntervals:a.vocals,bIntervals:b.vocals}
  try{
   validateRelay(p.start,p.end,p.duration,relay)
   const quiet=shortlist.find((x:any)=>x[2]===a.id&&Math.abs(x[3]-relay.aVoiceEnd)<.01&&Math.abs(x[4]-p.end)<.15)
   if(!quiet)continue
   const timing=bassTiming(a.alignment.bars,p.start,p.end),plan={...p,v30Eq:p.v30Eq||buildV30Eq(a,b,p)}
   eligible.push({id:'endpoint-probe-01',anchor:false,slot:{id:'probe',label:'扩展验证片段'},aTitle:a.title,bTitle:b.title,bpm:[a.bpm,b.bpm],pre:4,post:8,plan,planSha256:crypto.createHash('sha256').update(JSON.stringify(plan)).digest('hex'),timing,baselineBass:'reference',relay,quietProxy:quiet,score:p.score})
  }catch{}
 }
 audit.push({source:title,plans:r.candidates.length,eligible:eligible.filter(c=>c.aTitle===title).length})
}
eligible.sort((a,b)=>b.score-a.score||a.plan.id.localeCompare(b.plan.id))
if(!eligible.some(c=>c.aTitle==="Doin' It"&&c.bTitle==='Talgo'))throw Error('No original-policy plan supports this probe')
const cases=eligible.filter(c=>c.aTitle==="Doin' It"&&c.bTitle==='Talgo').slice(0,1),ids=new Set(cases.flatMap(c=>[c.plan.from,c.plan.to])),selected=tracks.filter(t=>ids.has(t.id))
fs.writeFileSync(path.join(root,'probe-selection.json'),JSON.stringify({schema:'harbeat.endpoint-probe-selection.v1',cases,tracks:selected.map(t=>({id:t.id,title:t.title,reportId:t.reportId,provenance:t.provenance})),audit:{expanded:true,reason:'All three original source contexts failed endpoint gate; new controlled exploratory pair from unchanged automatic planner; not a retest of the prior pair',candidateSources:titles,scan:audit,eligible:eligible.length}},null,2))
fs.writeFileSync(path.join(root,'probe-tracks.json'),JSON.stringify(selected))
console.log(cases.map(c=>({a:c.aTitle,b:c.bTitle,start:c.plan.start,end:c.plan.end,voiceEnd:c.relay.aVoiceEnd})),audit)
