import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {planAutomaticQuality} from '../src/continuous/qualityPlan'
import {buildV30Eq} from '../src/v30/eq'
import {rankFrozen,type KeySource,type Candidate} from '../src/harmonic-key/ranking'
import type {Track,Plan} from '../src/realtime/planner'

const root=path.resolve('../../../work/harmonic-key-20261017')
const read=(p:string)=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'))
const audit=read('key-audit.json'),bindings=read('catalog-bindings.json')
const rows=read('cohort.json') as {id:string;collection:string}[]
const tracks:Track[]=rows.map(row=>read('details/'+row.id+'.json').track)
const sha=(v:unknown)=>crypto.createHash('sha256').update(JSON.stringify(v)).digest('hex')
const keys:Record<string,KeySource>={}
for(const t of tracks){
 const old=bindings.tracks.find((x:any)=>x.id===t.id),a=audit.tracks.find((x:any)=>x.id===t.id)
 if(!old||!a?.source_bound||old.provenance.masterSha256!==t.provenance?.masterSha256||old.provenance.runId!==t.provenance?.runId)throw Error('Cohort source binding changed: '+t.id)
 keys[t.id]={masterSha256:String(t.provenance!.masterSha256),runId:String(t.provenance!.runId),key:{camelot:a.key.camelot,needsReview:a.key.needs_review,verified:false,masterSha256:old.provenance.masterSha256,runId:old.provenance.runId}}
}
type Trial={id:string;source:string;collection:string;position:number;baseline:Plan;variant:Plan;exploratory:boolean;frozen:Candidate<Plan>[];ranking:{id:string;score:number;bonus:number;rankScore:number}[]}
const trials:Trial[]=[],skipped:{title:string;reason:string}[]=[]
for(const a of tracks){
 const r=planAutomaticQuality(a,tracks,0,{kind:'next'},new Set(),false)
 if(!r.best){skipped.push({title:a.title,reason:'No original safe plan: '+r.exclusions.slice(0,3).map(e=>e.reason).join('; ')});continue}
 const frozen:Candidate<Plan>[]=[],destinations=new Set<string>()
 for(const p of r.candidates){
  if(destinations.has(p.to))continue
  const b=tracks.find(t=>t.id===p.to)!
  try{
   const plan={...p,v30Eq:p.v30Eq||buildV30Eq(a,b,p)}
   frozen.push({...keys[b.id],id:plan.id,score:plan.score,plan});destinations.add(p.to)
  }catch{}
 }
 if(!frozen.length||frozen[0].id!==r.best.id)throw Error('Frozen pool does not reproduce original winner: '+a.title)
 const before=sha(frozen)
 const strict=rankFrozen(keys[a.id],frozen,false)
 if(strict.some((x,i)=>x.id!==frozen[i].id||x.bonus!==0))throw Error('Provisional evidence affected strict ranking')
 const ranked=rankFrozen(keys[a.id],frozen,true)
 if(sha(frozen)!==before)throw Error('Ranking changed a frozen plan')
 const baseline=frozen[0].plan,variant=ranked[0].plan
 const trial={id:'key-'+a.id,source:a.id,collection:rows.find(x=>x.id===a.id)!.collection,position:0,baseline,variant,exploratory:true,frozen,ranking:ranked.map(({id,score,bonus,rankScore})=>({id,score,bonus,rankScore}))}
 trials.push(trial)
 console.log(a.title,'→',tracks.find(t=>t.id===baseline.to)!.title,'/',tracks.find(t=>t.id===variant.to)!.title,baseline.id===variant.id?'unchanged':'changed')
}
const changed=trials.filter(t=>t.baseline.id!==t.variant.id),chosen:Trial[]=[]
for(const t of changed)if(!chosen.some(c=>c.collection===t.collection)&&chosen.length<2)chosen.push(t)
for(const t of changed)if(chosen.length<2&&!chosen.includes(t))chosen.push(t)
const unchanged=trials.find(t=>t.baseline.id===t.variant.id&&!chosen.includes(t))
if(unchanged)chosen.push(unchanged)
else if(chosen.length===2){const c=trials.find(t=>!chosen.includes(t));if(c)chosen.push({...c,id:c.id+'-strict',variant:c.baseline,exploratory:false,ranking:rankFrozen(keys[c.source],c.frozen,false).map(({id,score,bonus,rankScore})=>({id,score,bonus,rankScore}))})}
if(chosen.length!==3){fs.writeFileSync(path.join(root,'selection-diagnostics.json'),JSON.stringify({trials:trials.length,changed:changed.length,skipped},null,2));throw Error('Could not produce three safe cases; retain diagnostics instead of forcing a contrast')}
const ids=new Set(chosen.flatMap(c=>[c.source,c.baseline.to,c.variant.to]))
const pack={schema:'harbeat.harmonic-audition.v1',createdAt:new Date().toISOString(),release:path.basename(bindings.release),
 modelValidation:'provisional; deployed validation configuration missing',maxBonus:.08,
 tracks:tracks.filter(t=>ids.has(t.id)),keys:Object.fromEntries(Object.entries(keys).filter(([id])=>ids.has(id))),cases:chosen,
 audit:{cohort:tracks.length,safeSources:trials.length,changed:changed.length,skipped,strictFallback:true,frozenPlanHashes:Object.fromEntries(chosen.flatMap(c=>c.frozen.map(p=>[p.id,sha(p.plan)])))}}
fs.writeFileSync('harmonic-key-data.json',JSON.stringify(pack))
fs.writeFileSync(path.join(root,'pack-audit.json'),JSON.stringify({...pack,tracks:undefined,cases:chosen.map(c=>({id:c.id,source:c.source,baseline:c.baseline.id,variant:c.variant.id,exploratory:c.exploratory,ranking:c.ranking}))},null,2))
console.log(JSON.stringify({cases:chosen.length,tracks:ids.size,changedCases:chosen.filter(c=>c.baseline.id!==c.variant.id).length,bytes:fs.statSync('harmonic-key-data.json').size}))
