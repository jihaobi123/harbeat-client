import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {finalBar} from '../web/src/melody-overlap/policy'
import {localBeatGate} from '../web/src/continuous/beatAlignment'
import type {Track,Plan} from '../web/src/realtime/planner'
const pack=JSON.parse(fs.readFileSync('web/harmonic-key-data.json','utf8'))
const tracks=pack.tracks as Track[],cases:any[]=[],skipped:any[]=[]
for(const item of pack.cases){
 const plan=item.variant as Plan,a=tracks.find(t=>t.id===plan.from)!,b=tracks.find(t=>t.id===plan.to)!
 try{
  const reason=localBeatGate(a,b,plan);if(reason)throw Error(reason)
  if(!plan.v30Eq||plan.automation)throw Error('不支持的固定处理计划')
  const last=finalBar(a.alignment!.bars,plan.start,plan.end)
  cases.push({id:item.id.replace('key-','melody-'),aTitle:a.title,bTitle:b.title,sourceHarmonicCase:item.id,pre:4,post:8,shortStart:last-plan.start,lastBarSourceStart:last,plan,planSha256:crypto.createHash('sha256').update(JSON.stringify(plan)).digest('hex'),bpm:[a.bpm,b.bpm],vocalConflict:{aVocal:plan.aVocal,bVocal:plan.bVocal,midDuck:plan.midDuck,decision:plan.decision},sources:{a:{id:a.id,...a.provenance},b:{id:b.id,...b.provenance}}})
 }catch(e){skipped.push({id:item.id,reason:(e as Error).message})}
}
const result={schema:'harbeat.melody-overlap-selection.v1',createdAt:new Date().toISOString(),harmonicRelease:pack.release,tracks:tracks.filter(t=>cases.some(c=>[c.plan.from,c.plan.to].includes(t.id))).map(t=>({id:t.id,title:t.title,provenance:t.provenance})),cases,skipped}
const root=path.resolve('../../work/melody-overlap-20261017');fs.mkdirSync(root,{recursive:true});fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify(result,null,2))
console.log(JSON.stringify({cases:cases.map(c=>({id:c.id,a:c.aTitle,b:c.bTitle,originalOverlap:c.plan.duration,shortOverlap:c.plan.duration-c.shortStart})),skipped},null,2))
