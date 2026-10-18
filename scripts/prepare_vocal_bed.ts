import fs from 'node:fs'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {validateRelay} from '../web/src/vocal-bed/policy'
import {requireBoundVocals} from '../web/src/vocal-overlap/planner'
import {localBeatGate} from '../web/src/continuous/beatAlignment'
const work=process.argv[2],parent=path.dirname(work)
const tracks=new Map(fs.readdirSync(path.join(parent,'bass-generalization-20261017/details')).filter(f=>f.endsWith('.json')).map(f=>{const t=JSON.parse(fs.readFileSync(path.join(parent,'bass-generalization-20261017/details',f),'utf8')).track;return [t.id,t]}))
const selected:any[]=[],audit:any[]=[]
for(const file of ['bass-generalization-20261017/user-feedback.json','bass-neighbors-20261017/user-feedback-20261018.json']){
 const raw=fs.readFileSync(path.join(parent,file)),feedback=JSON.parse(raw.toString()),round=feedback.current
 if(round.practice)throw Error('formal choices required')
 for(const c of feedback.pack.cases){
  const p=c.plan,a:any=tracks.get(p.from),b:any=tracks.get(p.to)
  try{
   requireBoundVocals(a);requireBoundVocals(b)
   const issue=localBeatGate(a,b,p);if(issue)throw Error(issue)
   const av=a.vocals.filter(([s,e]:number[])=>s<p.end&&e>p.start)
   const relay={aVoiceEnd:Math.max(...av.map((x:number[])=>x[1])),bEntry:p.window.start,bEnd:p.window.end,aIntervals:a.vocals,bIntervals:b.vocals}
   validateRelay(p.start,p.end,p.duration,relay)
   const f=round.cases[c.id],mode=f.mapping[f.choice],baselineBass=mode==='stem'?'stem':'reference'
   selected.push({...c,id:'vocal-bed-'+String(selected.length+1).padStart(2,'0'),originalCaseId:c.id,baselineBass,relay,previousChoice:{roundId:round.id,choice:f.choice,method:mode??'tie',feedbackSha256:createHash('sha256').update(raw).digest('hex')}})
   audit.push({caseId:c.id,eligible:true})
  }catch(e){audit.push({caseId:c.id,eligible:false,reason:(e as Error).message})}
 }
}
if(!selected.length)throw Error('No frozen pair meets vocal/bed eligibility')
const cases=selected.slice(0,3),ids=new Set(cases.flatMap(c=>[c.plan.from,c.plan.to]))
fs.writeFileSync(path.join(work,'selection.json'),JSON.stringify({schema:'harbeat.vocal-bed-selection.v1',cases,tracks:[...tracks.values()].filter((t:any)=>ids.has(t.id)).map((t:any)=>({id:t.id,title:t.title,reportId:t.reportId,provenance:t.provenance})),audit:{candidateCount:audit.length,eligibleCount:selected.length,actualCount:cases.length,requestedMaximum:3,candidates:audit,semanticPhraseValidation:'unavailable; activity endpoints only; listening review required'}},null,2)+'\n')
console.log(cases.map(c=>[c.aTitle,c.bTitle,c.baselineBass,c.relay.aVoiceEnd]))
