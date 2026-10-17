import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {planAutomaticQuality} from '../web/src/continuous/qualityPlan'
import {buildV30Eq} from '../web/src/v30/eq'
import {bassTiming} from '../web/src/bass-swap/policy'
import {harmonicBonus,rankFrozen,type Candidate,type KeySource} from '../web/src/harmonic-key/ranking'
import {evaluateNeighbor,isRejectedWindow,type NeighborVector} from '../web/src/bass-neighbors/similarity'
import type {Track,Plan} from '../web/src/realtime/planner'
const read=(p:string)=>JSON.parse(fs.readFileSync(p,'utf8')),work=path.resolve('../../work/bass-neighbors-20261017'),prior=path.resolve('../../work/bass-generalization-20261017'),old=read(path.join(prior,'selection.json'))
const tracks:Track[]=fs.readdirSync(path.join(prior,'details')).filter(x=>x.endsWith('.json')).map(x=>read(path.join(prior,'details',x)).track)
const inventory=read(path.join(prior,'bass-inventory.json')),keyAudit=read(path.resolve('../../work/harmonic-key-20261017/key-audit.json')).tracks
const excludeOld=new Set(old.cases.flatMap((c:any)=>[c.plan.from,c.plan.to])),rejections=fs.existsSync(path.join(work,'audio-rejections.json'))?read(path.join(work,'audio-rejections.json')):[]
const bound=(t:Track)=>inventory.find((x:any)=>x.id===t.id&&x.sourceBound&&x.runId===t.provenance!.runId&&x.masterSha256===t.provenance!.masterSha256&&x.bass?.exists&&x.bass.channels===2&&x.bass.sampleRate===44100)
const keys:Record<string,KeySource>={}
for(const t of tracks){const row=keyAudit.find((x:any)=>x.id===t.id&&x.source_bound);if(!bound(t)||!row)continue;keys[t.id]={masterSha256:String(t.provenance!.masterSha256),runId:String(t.provenance!.runId),key:{camelot:row.key.camelot,needsReview:row.key.needs_review,verified:false,masterSha256:String(t.provenance!.masterSha256),runId:String(t.provenance!.runId)}}}
const families=[{id:'funk',reference:'coverage-funk',labels:['funk'],preference:'reference'},{id:'jazz',reference:'coverage-jazz',labels:['jazz hiphop','boombap'],preference:'stem'},{id:'edm',reference:'coverage-edm',labels:['EDM','house'],preference:'stem'}]
const vector=(a:Track,b:Track,p:Plan):NeighborVector=>({bpm:[a.bpm,b.bpm],sourceTags:a.styleLabels??[],destinationTags:b.styleLabels??[],styles:[a.style,b.style],vocals:[p.aVocal??0,p.bVocal??0],bars:p.duration*a.bpm/240,harmonicBonus:harmonicBonus(keys[a.id],keys[b.id],true)})
const candidateAudit:any[]=[],scanAudit:any[]=[],chosen:any[]=[],used=new Set<string>(),fallbacks=['Strict all-new funk sources provided only one eligible pair. Retain only the 24K Magic reference source with a new destination as an explicit same-source control; retain every cue/vocal gate.']
for(const family of families){
 const reference=old.cases.find((c:any)=>c.id===family.reference),ra=tracks.find(t=>t.id===reference.plan.from)!,rb=tracks.find(t=>t.id===reference.plan.to)!,rv=vector(ra,rb,reference.plan)
 if(!rv.destinationTags.length&&family.id==='jazz')rv.destinationTags=[...family.labels]
 const sources=tracks.filter(a=>keys[a.id]&&!excludeOld.has(a.id)&&(a.styleLabels??[]).some(x=>family.labels.some(y=>x.toLowerCase()===y.toLowerCase()))&&Math.abs(a.bpm/ra.bpm-1)<=.1000001).sort((a,b)=>a.id.localeCompare(b.id))
 if(family.id==='funk')sources.push(ra)
 const candidates:any[]=[]
 for(const a of sources){
  const pool=tracks.filter(b=>keys[b.id]&&!excludeOld.has(b.id)&&b.id!==a.id&&Math.abs(a.bpm/b.bpm-1)<=.06&&Math.abs(b.bpm/rb.bpm-1)<=.1000001)
  const r=planAutomaticQuality(a,pool,0,{kind:'next'},new Set(),false),destinations=new Set<string>(),frozen:Candidate<Plan>[]=[],counts:Record<string,number>={}
  for(const e of r.exclusions)counts[e.code]=(counts[e.code]??0)+(e.count??1)
  let timingRejected=0,eqRejected=0
  for(const p of r.candidates){if(destinations.has(p.to)||p.rate<.94||p.rate>1.06)continue
   try{bassTiming(a.alignment!.bars,p.start,p.end)}catch{timingRejected++;continue}
   const b=tracks.find(t=>t.id===p.to)!
   try{const plan={...p,v30Eq:p.v30Eq||buildV30Eq(a,b,p)};frozen.push({...keys[b.id],id:p.id,score:p.score,plan});destinations.add(b.id)}catch{eqRejected++}
  }
  const before=JSON.stringify(frozen),ranked=rankFrozen(keys[a.id],frozen,true),strict=rankFrozen(keys[a.id],frozen,false)
  if(before!==JSON.stringify(frozen)||strict.some((x,i)=>x.id!==frozen[i].id||x.bonus!==0))throw Error('frozen/ranking invariant')
  const rejected:Record<string,number>={}
  for(const row of ranked){const p=row.plan,b=tracks.find(t=>t.id===p.to)!,v=vector(a,b,p),match=evaluateNeighbor(rv,v,family.labels)
   candidateAudit.push({family:family.id,source:a.title,destination:b.title,planId:p.id,planSha256:crypto.createHash('sha256').update(JSON.stringify(p)).digest('hex'),cue:{start:p.start,end:p.end,duration:p.duration,rate:p.rate,window:{start:p.window.start,end:p.window.end}},vector:v,neighbor:match,rankScore:row.rankScore,harmonicBonus:row.bonus,audioRejected:isRejectedWindow(p,rejections)})
   for(const reason of match.reasons)rejected[reason]=(rejected[reason]??0)+1
   if(!match.eligible||isRejectedWindow(p,rejections))continue
   candidates.push({a,b,plan:p,vector:v,match,rankScore:row.rankScore,harmonicBonus:row.bonus,reference,referenceVector:rv,family})
  }
  scanAudit.push({family:family.id,source:a.title,sourceId:a.id,rawSafePlans:r.candidates.length,frozenDestinations:frozen.length,exclusionCounts:counts,timingRejected,eqRejected,neighborRejections:rejected})
  console.log('scanned',family.id,a.title,'eligible',candidates.filter(x=>x.a.id===a.id).length)
 }
 const available=candidates.filter(x=>!used.has(x.a.id)&&!used.has(x.b.id)).sort((x,y)=>x.match.distance-y.match.distance||y.rankScore-x.rankScore||x.plan.id.localeCompare(y.plan.id))
 let best:[any,any]|undefined,bestDistance=Infinity
 for(let i=0;i<available.length;i++)for(let j=i+1;j<available.length;j++){
  const x=available[i],y=available[j],distance=x.match.distance+y.match.distance
  if(distance>bestDistance)break
  if(new Set([x.a.id,x.b.id,y.a.id,y.b.id]).size!==4)continue
  if(distance<bestDistance){best=[x,y];bestDistance=distance}
 }
 if(!best)throw Error('family lacks two independent eligible pairs: '+family.id)
 best.forEach((x,i)=>{
  used.add(x.a.id);used.add(x.b.id)
  chosen.push({id:'neighbor-'+family.id+'-'+(i+1),anchor:false,slot:{id:family.id,label:'新曲对'},aTitle:x.a.title,bTitle:x.b.title,bpm:x.vector.bpm,pre:4,post:8,plan:x.plan,planSha256:crypto.createHash('sha256').update(JSON.stringify(x.plan)).digest('hex'),timing:bassTiming(x.a.alignment!.bars,x.plan.start,x.plan.end),similarity:{referenceId:x.reference.id,referenceTitles:[x.reference.aTitle,x.reference.bTitle],referencePreference:family.preference,referenceVector:x.referenceVector,candidateVector:x.vector,distance:x.match.distance,components:x.match.components,scope:'metadata neighbor, not verified perceptual groove similarity',candidateCount:available.length,familyOrder:'scarce funk, then jazz, then EDM; choose minimum total-distance disjoint pair within family'},vocalConflict:{aVocal:x.plan.aVocal,bVocal:x.plan.bVocal,midDuck:x.plan.midDuck}})
  console.log('SELECTED',x.a.title,'→',x.b.title,'distance',x.match.distance)
 })
}
const cases=[...chosen].sort((a,b)=>Number(a.id.at(-1))-Number(b.id.at(-1))||a.id.localeCompare(b.id)),ids=new Set(cases.flatMap(c=>[c.plan.from,c.plan.to]))
const selection={schema:'harbeat.bass-generalization-selection.v1',harmonicRelease:old.harmonicRelease,tracks:tracks.filter(t=>ids.has(t.id)).map(t=>({id:t.id,title:t.title,provenance:t.provenance,bassSha256:bound(t).bass.sha256})),cases,audit:{catalog:tracks.length,fallbacks,excludedPreviousTrackIds:[...excludeOld],families,missingDestinationTagPolicy:'Feather has no human tag; its Jazzy Hip-Hop model style is matched using declared jazz hiphop/boombap destination family tags, never inferred from BPM alone',scanAudit,audioRejections:rejections,strictFallback:true,selectionRule:'original best eligible frozen plan per destination; metadata distance only selects pairs, never edits plan; minimum sum distance of two disjoint pairs per family; no listening-based choice',limitations:['six new pairs; one listener; no guaranteed outcome','style/model labels are proxies, not verified groove similarity','only selected safe vocal handoff and measured complete bars','all prior tracks excluded except the declared 24K Magic source control; no track repeats within this round']}}
fs.writeFileSync(path.join(work,'candidate-ledger.json'),JSON.stringify(candidateAudit,null,2));fs.writeFileSync(path.join(work,'selection.json'),JSON.stringify(selection,null,2));console.log('saved',cases.length,'cases',ids.size,'tracks')
