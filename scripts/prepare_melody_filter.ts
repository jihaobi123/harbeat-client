import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {filterPlan} from '../web/src/melody-filter/policy'
import {requireBoundVocals} from '../web/src/vocal-overlap/planner'
const root=path.resolve(process.argv[2]),parent=path.resolve(process.argv[3]),details=path.resolve(process.argv[4]),read=(p:string)=>JSON.parse(fs.readFileSync(p,'utf8')),sha=(v:Buffer|string)=>crypto.createHash('sha256').update(v).digest('hex')
const frozen=read(path.join(root,'frozen-input.json')),raw=fs.readFileSync(path.join(parent,'pack.json')),old=JSON.parse(raw.toString()),tracks=fs.readdirSync(details).filter(p=>p.endsWith('.json')).map(p=>read(path.join(details,p)).track)
if(sha(raw)!==frozen.sourcePackSha256||JSON.stringify(old.cases.map((c:any)=>c.id))!==JSON.stringify(frozen.sourceCaseIds))throw Error('Frozen parent changed')
const cases=old.cases.map((c:any,i:number)=>{
 const a=tracks.find(t=>t.id===c.plan.from),b=tracks.find(t=>t.id===c.plan.to)
 for(const [t,side] of [[a,'a'],[b,'b']] as const){requireBoundVocals(t);for(const k of ['reportSha256','masterSha256','vocalSha256','runId'])if(t.provenance[k]!==c.sourceVerification[side][k])throw Error('Source/VAD bindings changed')}
 const sourceBar=a.alignment.bars.find((x:any)=>Math.abs(x.start-c.lastBarSourceStart)<=.001)
 const next={...c,id:'melody-filter-'+String(i+1).padStart(2,'0'),sourceCaseId:c.id,originalPlanSha256:c.planSha256,planSha256:sha(JSON.stringify(c.plan)),filter:{...frozen.filter,sourceStart:c.lastBarSourceStart,sourceBar,gridSource:a.alignment.source,endOffsetFromObservedBar:c.plan.end-sourceBar.end},filterScope:'only original Aother final-bar highpass; original gains/cues/EQ and vocal conflict preserved'}
 for(const k of ['yieldEnd','firstBar','shortStart','lastBarSourceStart'])delete next[k]
 filterPlan(next,'relay');return next
})
fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify({schema:'harbeat.melody-filter-selection.v1',sourcePackSha256:frozen.sourcePackSha256,cases},null,2)+'\n')
console.log(cases.map((c:any)=>({pair:[c.aTitle,c.bTitle],filter:c.filter,fullPlanSha256:c.planSha256})))
