import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import {requireBoundVocals} from '../web/src/vocal-overlap/planner'
import {buildV30Eq} from '../web/src/v30/eq'
import {vocalPresence,energyAt} from '../web/src/realtime/planner'
import {evaluateEvidence} from '../web/src/realtime/evidence'
import {validateMetric} from '../web/src/half-double/policy'
const root=path.resolve(process.argv[2]),details=path.resolve(process.argv[3]),read=(p:string)=>JSON.parse(fs.readFileSync(p,'utf8')),digest=(s:string|Buffer)=>crypto.createHash('sha256').update(s).digest('hex')
const tracks=fs.readdirSync(details).filter(f=>f.endsWith('.json')).map(f=>read(path.join(details,f)).track),rows=read(path.join(root,'frozen-cues.json')),selected:any[]=[],cases:any[]=[]
for(const [i,row] of rows.entries()){
 const a=tracks.find(t=>t.id===row.aid),b=tracks.find(t=>t.id===row.bid);requireBoundVocals(a);requireBoundVocals(b)
 const window={...b.windows.find((w:any)=>w.id===row.window.id),variants:{}}
 if(window.start!==row.window.start||window.end!==row.window.end)throw Error('frozen B cues changed')
 const metric={relation:row.relation,input:row.inputBeats,output:row.outputBeats,aBars:row.aBars,bBars:window.bars,maxShiftSeconds:row.maxShift,voicePolicy:'original-linear-fades',scope:'endpoint-preserving local2:1/1:2phase correction; not constant tempo/phrase reselection',aGridSource:a.alignment.source,bGridSource:b.alignment.source}
 const av=a.vocals.map(([s,e]:number[])=>[s-.3,e+.3]),bv=b.vocals.map(([s,e]:number[])=>[s-.3,e+.3])
 const interpolate=(v:number)=>{const x=metric.input,y=metric.output;if(v<=0)return v;if(v>=row.duration)return v;const j=x.findIndex((t:number)=>t>=v);return y[j-1]+(v-x[j-1])*(y[j]-y[j-1])/(x[j]-x[j-1])}
 // Apply unchanged padded-voice protection to the union of native and mapped time.
 for(const [s,e] of bv){const lo=Math.max(0,s-window.start),hi=Math.min(row.duration,e-window.start);if(hi<=lo)continue;const left=row.start+Math.min(lo,interpolate(lo))-.065,right=row.start+Math.max(hi,interpolate(hi))+.065;if(av.some(([u,v]:number[])=>u<right&&v>left))throw Error('native/mapped protected vocals overlap')}
 if(a.alignment.phrases.some((x:any)=>x.start<row.end+.08&&x.tailEnd>row.end-.15)||b.alignment.phrases.some((x:any)=>x.start<window.start+.08&&x.tailEnd>window.start-.08))throw Error('fixed cue intersects protected phrase')
 const aVocal=vocalPresence(a.vocals,row.start,row.end),bVocal=vocalPresence(b.vocals,window.start,window.end),evidence=evaluateEvidence(a,b,window,row.start,{kind:'next'});if(!evidence.accepted)throw Error(evidence.reason)
 const plan:any={id:`half-double:${a.id}:${b.id}:${window.id}:${row.end}`,from:a.id,to:b.id,start:row.start,end:row.end,duration:row.duration,rate:1,window,restore:row.end-Math.min(row.duration,120/a.bpm),aVocal,bVocal,midDuck:aVocal*row.duration>=.5&&aVocal>=.05&&bVocal*row.duration>=.5&&bVocal>=.05,gridError:row.gridError,aEnergy:energyAt(a,row.start,row.end),bEnergy:window.energy,evidence}
 plan.v30Eq=buildV30Eq(a,b,plan)
 const c={id:'half-double-'+String(i+1).padStart(2,'0'),aTitle:a.title,bTitle:b.title,bpm:[a.bpm,b.bpm],pre:4,post:8,baselineBass:'reference',plan,planSha256:digest(JSON.stringify(plan)),metric,features:{originalMaxBeatOffset:row.maxShift,rawSectionBoundary:row.section},sourceVerification:{}}
 validateMetric(c);cases.push(c)
 for(const t of [a,b])if(!selected.some(x=>x.id===t.id))selected.push(t)
}
const audit={candidateWindows:read(path.join(root,'exploration.json')).length,distinctPairs:3,sourceTracks:selected.length,selection:'highest observed native phase RMS among fixed eligible windows per distinct pair, before audio; first2share OldTownRoad',cuePolicy:'existing B windows and late A raw bars; same65ms original tolerance and bound vocal/phrase protections. No per-arm search or source-cue movement.',limitation:'New exploratory ratio pairs; cannot reuse prior near-tempo pairs. Numerical grid relation is provisional, not human-confirmed half-time groove/semantic phrase truth.',snapshotHashes:selected.map(t=>({id:t.id,sha256:digest(JSON.stringify(t))}))}
fs.writeFileSync(path.join(root,'selection.json'),JSON.stringify({schema:'harbeat.half-double-selection.v1',cases,tracks:selected.map(t=>({id:t.id,title:t.title,reportId:t.reportId,provenance:t.provenance})),audit},null,2)+'\n')
fs.writeFileSync(path.join(root,'tracks.json'),JSON.stringify(selected,null,2)+'\n');console.log(cases.map(c=>({a:c.aTitle,b:c.bTitle,relation:c.metric.relation,eq:c.plan.v30Eq})))
