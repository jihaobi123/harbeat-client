import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {planAutomaticQuality} from '../web/src/continuous/qualityPlan'
import {buildV30Eq} from '../web/src/v30/eq'
import {bassTiming} from '../web/src/bass-swap/policy'
import {rankFrozen,type Candidate,type KeySource} from '../web/src/harmonic-key/ranking'
import type {Track,Plan} from '../web/src/realtime/planner'
const root=path.resolve('../../work/bass-generalization-20261017'),oldRoot=path.resolve('../../work/harmonic-key-20261017')
const read=(p:string)=>JSON.parse(fs.readFileSync(p,'utf8')),index=read(path.join(oldRoot,'public-index.json')).tracks
const tracks:Track[]=fs.readdirSync(path.join(root,'details')).filter(x=>x.endsWith('.json')).map(x=>read(path.join(root,'details',x)).track)
const inventory=read(path.join(root,'bass-inventory.json')),keyAudit=read(path.join(oldRoot,'key-audit.json')).tracks
const bound=(t:Track)=>inventory.find((x:any)=>x.id===t.id&&x.sourceBound&&x.runId===t.provenance!.runId&&x.masterSha256===t.provenance!.masterSha256&&x.bass?.exists&&x.bass.channels===2&&x.bass.sampleRate===44100)
const keys:Record<string,KeySource>={}
for(const t of tracks){const row=keyAudit.find((x:any)=>x.id===t.id&&x.source_bound);if(!bound(t)||!row)continue;keys[t.id]={masterSha256:String(t.provenance!.masterSha256),runId:String(t.provenance!.runId),key:{camelot:row.key.camelot,needsReview:row.key.needs_review,verified:false,masterSha256:String(t.provenance!.masterSha256),runId:String(t.provenance!.runId)}}}
const audioRejections=fs.existsSync(path.join(root,'audio-rejections.json'))?read(path.join(root,'audio-rejections.json')):[]
const old=read(path.resolve('../../work/bass-swap-20261017/selection.json')),anchor={...old.cases[0],id:'coverage-anchor',anchor:true,slot:{id:'anchor',label:'旧样例复听'}}
const cases:any[]=[anchor],used=new Set([anchor.plan.from,anchor.plan.to]),audit:any[]=[]
const slots=[{id:'edm',label:'EDM',titles:['The Spectre','Nevada','Move Up (Lost Gravity)']},{id:'kpop',label:'KPOP',titles:['After LIKE','꽃 (FLOWER)','Movie Star']},{id:'amapiano',label:'amapiano',titles:['Yensa','Big Flexa','Hamba Nobani']},{id:'funk',label:'funk',titles:['24K Magic (1)',"Let's Groove",'Treasure (1)']},{id:'jazz',label:'jazz hiphop',titles:['Love Note (Original Instrumental)','Ampersand','Playback (feat. Ine)']}]
const futureSources=new Set(slots.flatMap(s=>s.titles.map(title=>tracks.find(t=>t.title===title)?.id).filter(Boolean)))
for(const slot of slots){
 let found=false
 for(const title of slot.titles){
  const a=tracks.find(t=>t.title===title),row:any={slot:slot.id,source:title}
  if(!a||!keys[a.id]||used.has(a.id)){audit.push({...row,reason:'source unavailable/already used'});continue}
  const pool=tracks.filter(b=>b.id!==a.id&&keys[b.id]&&!used.has(b.id)&&!futureSources.has(b.id)&&!audioRejections.some((x:any)=>x.sourceId===a.id&&x.destinationId===b.id)&&Math.abs(a.bpm/b.bpm-1)<=.06)
  console.log('scan',slot.id,title,'destinations',pool.length)
  const r=planAutomaticQuality(a,pool,0,{kind:'next'},new Set(),false);row.safePlans=r.candidates.length;row.exclusions=r.exclusions.map(e=>({code:e.code,count:e.count}));row.bassTimingRejected=0;row.eqRejected=0
  const frozen:Candidate<Plan>[]=[],destinations=new Set<string>()
  for(const p of r.candidates){if(destinations.has(p.to)||p.rate<.94||p.rate>1.06)continue
   try{bassTiming(a.alignment!.bars,p.start,p.end)}catch{row.bassTimingRejected++;continue}
   const b=tracks.find(t=>t.id===p.to)!
   try{const plan={...p,v30Eq:p.v30Eq||buildV30Eq(a,b,p)};frozen.push({...keys[b.id],id:p.id,score:p.score,plan});destinations.add(b.id)}catch{row.eqRejected++}
  }
  if(!frozen.length){audit.push({...row,reason:'no eligible frozen destination'});continue}
  const before=JSON.stringify(frozen),strict=rankFrozen(keys[a.id],frozen,false),ranked=rankFrozen(keys[a.id],frozen,true)
  if(strict.some((x,i)=>x.id!==frozen[i].id||x.bonus!==0)||JSON.stringify(frozen)!==before)throw Error('Evidence or immutability invariant failed')
  const p=ranked[0].plan,b=tracks.find(t=>t.id===p.to)!,timing=bassTiming(a.alignment!.bars,p.start,p.end)
  cases.push({id:'coverage-'+slot.id,anchor:false,slot:{id:slot.id,label:slot.label},aTitle:a.title,bTitle:b.title,bpm:[a.bpm,b.bpm],pre:4,post:8,plan:p,planSha256:crypto.createHash('sha256').update(JSON.stringify(p)).digest('hex'),timing,collections:[a,b].map(t=>index.find((x:any)=>x.id===t.id)?.collection),styleLabels:[a,b].map(t=>index.find((x:any)=>x.id===t.id)?.styleLabels),ranking:ranked.map(({id,score,bonus,rankScore})=>({id,score,bonus,rankScore})),vocalConflict:{aVocal:p.aVocal,bVocal:p.bVocal,midDuck:p.midDuck,decision:p.decision}})
  used.add(a.id);used.add(b.id);audit.push({...row,eligibleDestinations:frozen.length,selected:b.title,selectedPlan:p.id});found=true;console.log('selected',a.title,'→',b.title,'BPM',a.bpm,b.bpm,'overlap',p.duration);break
 }
 if(!found)audit.push({slot:slot.id,reason:'predeclared source slot exhausted'})
}
const ids=new Set(cases.flatMap(c=>[c.plan.from,c.plan.to])),selectedTracks=tracks.filter(t=>ids.has(t.id)).map(t=>({id:t.id,title:t.title,provenance:t.provenance,bassSha256:bound(t).bass.sha256}))
const selection={schema:'harbeat.bass-generalization-selection.v1',harmonicRelease:old.harmonicRelease,tracks:selectedTracks,cases,audit:{catalog:tracks.length,sourceBoundBass:inventory.filter((x:any)=>x.sourceBound&&x.bass?.exists).length,slots,audioRejections,selection:audit,strictFallback:true,limitations:['Six-case pilot; old anchor is not an independent new sample.','Provisional key labels; no validated accuracy claim.','Eligibility constrained to existing safe plans, complete measured bars and readable bass stems.']}}
fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify(selection,null,2));console.log('Cases',cases.length,'unique tracks',selectedTracks.length)
