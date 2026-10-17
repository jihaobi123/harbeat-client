import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {bassTiming} from '../web/src/bass-swap/policy'
import {localBeatGate} from '../web/src/continuous/beatAlignment'
const root=path.resolve('../../work/bass-swap-20261017'),pack=JSON.parse(fs.readFileSync('web/harmonic-key-data.json','utf8')),probe=JSON.parse(fs.readFileSync(path.join(root,'source-probe.json'),'utf8'))
const old=pack.cases[1],plan=old.variant,a=pack.tracks.find((t:any)=>t.id===plan.from),b=pack.tracks.find((t:any)=>t.id===plan.to)
const rejected=localBeatGate(a,b,plan);if(rejected||!plan.v30Eq||plan.automation)throw Error(rejected||'Unsupported frozen plan')
const timing=bassTiming(a.alignment.bars,plan.start,plan.end)
const tracks=[a,b].map(t=>{const p=probe.find((p:any)=>p.id===t.id);if(!p?.sourceBound||p.masterSha256!==t.provenance.masterSha256)throw Error('Bass audit source mismatch');return {id:t.id,title:t.title,provenance:t.provenance,bassSha256:p.layers.bass.manifestSha256}})
const c={id:old.id.replace('key-','bass-'),aTitle:a.title,bTitle:b.title,bpm:[a.bpm,b.bpm],pre:4,post:8,plan,planSha256:crypto.createHash('sha256').update(JSON.stringify(plan)).digest('hex'),timing,vocalConflict:{aVocal:plan.aVocal,bVocal:plan.bVocal,midDuck:plan.midDuck,decision:plan.decision}}
fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify({schema:'harbeat.bass-swap-selection.v1',harmonicRelease:pack.release,tracks,cases:[c]},null,2));console.log(JSON.stringify({case:c.id,timing,sourceTimes:Object.fromEntries(Object.entries(timing).map(([k,v])=>[k,plan.start+v]))},null,2))
