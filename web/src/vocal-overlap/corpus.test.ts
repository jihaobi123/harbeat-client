import {it,expect} from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {performance} from 'node:perf_hooks'
import type {Track,Plan} from '../realtime/planner'
import {planV31} from '../v31-release/release'
import {planVocalOverlap,type OverlapPlan} from './planner'
import {alignedVocalOverlap} from './score'

const root=process.env.VOCAL_OVERLAP_CORPUS,base=process.env.VOCAL_OVERLAP_BASE,auditRoot=process.env.VOCAL_OVERLAP_AUDIT
it.skipIf(!root||!base||!auditRoot)('compares a fixed old/new matrix with identical entry material and preserves the frozen corpus',()=>{
  const tracks:Track[]=JSON.parse(fs.readFileSync(path.join(root!,'catalog.json'),'utf8')).tracks
  const old:Track[]=JSON.parse(fs.readFileSync(path.join(base!,'catalog.json'),'utf8')).tracks
  const oldIds=new Set(old.map(t=>t.id)),added=tracks.filter(t=>!oldIds.has(t.id))
  expect(old).toHaveLength(20)
  expect(new Set(tracks.map(t=>t.id)).size).toBe(tracks.length)
  expect(new Set(tracks.map(t=>t.provenance?.masterSha256)).size).toBe(tracks.length)
  for(const t of old){
    const actual=tracks.find(x=>x.id===t.id)!
    const projected={...actual,windows:actual.windows.map(w=>({...w,variants:Object.fromEntries(Object.entries(w.variants).filter(([id])=>oldIds.has(id)))}))}
    expect(projected).toEqual(t)
  }
  type Case={id:string;a:string;b:string;position:number;group:string}
  const originals:Case[]=JSON.parse(fs.readFileSync(path.join(base!,'cases.json'),'utf8')).cases.filter((c:Case)=>c.group==='original20')
  expect(originals).toHaveLength(20)
  const newCases:Case[]=[]
  // Pair selection depends on prepared tempo variants, never the score change.
  for(const t of added){
    const compatible=(a:Track,b:Track)=>b.windows.some(w=>!!w.variants[a.id])
    const ordered=[...old].sort((a,b)=>Math.abs(a.bpm-t.bpm)-Math.abs(b.bpm-t.bpm)||a.id.localeCompare(b.id))
    const incoming=ordered.find(a=>compatible(a,t)),outgoing=ordered.find(b=>compatible(t,b))
    expect(incoming).toBeTruthy();expect(outgoing).toBeTruthy()
    newCases.push({id:`new-in:${t.id}`,a:incoming!.id,b:t.id,position:30,group:'new_music'},
      {id:`new-out:${t.id}`,a:t.id,b:outgoing!.id,position:30,group:'new_music'})
  }
  const rows:any[]=[],examples:Case[]=[],timings:number[]=[]
  const measure=(a:Track,b:Track,p:Plan)=>alignedVocalOverlap(a.vocals,b.vocals,
    {aStart:p.start,bStart:p.window.start,bEnd:p.window.end,duration:p.duration,rate:p.rate})
  function compare(a:Track,b:Track,position:number,group:string){
    const args=[a,tracks,position,{kind:'next' as const,targetId:b.id},new Set<string>(),18,false] as const
    const original=planV31(...args),before=performance.now(),experiment=planVocalOverlap(...args),elapsed=performance.now()-before
    timings.push(elapsed)
    const p=original.best,q=experiment.best as OverlapPlan|null
    const row:any={a:a.id,b:b.id,aTitle:a.title,bTitle:b.title,position,group,oldPair:oldIds.has(a.id)&&oldIds.has(b.id),
      baselineAvailable:!!p,experimentAvailable:!!q,baselineCandidateCount:original.candidates.length,
      timingCandidateCount:experiment.candidates.length,exclusions:experiment.exclusions.map(e=>e.code)}
    if(!p){expect(q).toBeNull();rows.push(row);return row}
    expect(q).toBeTruthy()
    expect(q!.window).toEqual(p.window);expect(q!.asset).toEqual(p.asset)
    expect(q!.duration).toBe(p.duration);expect(q!.rate).toBe(p.rate);expect(q!.to).toBe(p.to)
    expect(q!.start).toBeGreaterThanOrEqual(position+.25);expect(q!.end).toBeLessThanOrEqual(position+18)
    expect(q!.automation).toBeUndefined();expect(q!.phrase).toBeUndefined()
    expect(q!.vocalOverlap.weightedOverlap).toBeGreaterThanOrEqual(0);expect(q!.vocalOverlap.weightedOverlap).toBeLessThanOrEqual(1)
    const oldCandidate=original.candidates.find(c=>c.id===q!.id)!
    expect(oldCandidate).toBeTruthy()
    expect(q!.decision!.score.components.filter(c=>c.key!=='vocal')).toEqual(oldCandidate.decision!.score.components.filter(c=>c.key!=='vocal'))
    expect(q!.midDuck).toBe(oldCandidate.midDuck)
    if(q!.id===p.id)expect(q!.v30Eq).toEqual(p.v30Eq)
    const baselineOverlap=measure(a,b,p)
    Object.assign(row,{changed:q!.id!==p.id,shiftSec:q!.start-p.start,duration:p.duration,
      oldStart:p.start,oldEnd:p.end,newStart:q!.start,newEnd:q!.end,bStart:p.window.start,bEnd:p.window.end,
      windowId:p.window.id,assetSha256:p.asset.sha256,rate:p.rate,
      oldVocalProduct:p.aVocal*p.bVocal,baselineWeightedOverlap:baselineOverlap.weightedOverlap,
      experimentWeightedOverlap:q!.vocalOverlap.weightedOverlap,baselineSimultaneousSec:baselineOverlap.simultaneousSec,
      experimentSimultaneousSec:q!.vocalOverlap.simultaneousSec})
    rows.push(row);return row
  }
  for(const c of [...originals,...newCases])compare(tracks.find(t=>t.id===c.a)!,tracks.find(t=>t.id===c.b)!,c.position,c.group)
  for(const a of tracks)for(const b of tracks){if(a===b)continue;for(const position of [15,30,45,60,80]){
    const row=compare(a,b,position,'fixed_matrix')
    if(row.changed && examples.length<10 && !examples.some(c=>c.a===a.id))
      examples.push({id:`changed:${a.id}:${b.id}:${position}`,a:a.id,b:b.id,position,group:'changed_examples'})
  }}
  const matrix=rows.filter(r=>r.group==='fixed_matrix'),available=matrix.filter(r=>r.baselineAvailable)
  const changed=available.filter(r=>r.changed),oldRows=rows.filter(r=>r.group==='original20'),newRows=rows.filter(r=>r.group==='new_music')
  timings.sort((a,b)=>a-b)
  const coverage={tracks:tracks.length,oldTracks:20,newTracks:added.length,matrixChecks:matrix.length,available:available.length,
    unavailable:matrix.length-available.length,changed:changed.length,oldCases:20,oldAvailable:oldRows.filter(r=>r.baselineAvailable).length,
    oldChanged:oldRows.filter(r=>r.changed).length,newCases:newCases.length,newAvailable:newRows.filter(r=>r.baselineAvailable).length,
    newChanged:newRows.filter(r=>r.changed).length,plannerP95Ms:timings[Math.floor(timings.length*.95)],plannerMaxMs:timings.at(-1),
    interpretation:'确定性规则与结构验证；人声指标降低不等于听感更好。变化示例经过挑选，不计作独立胜率。'}
  fs.mkdirSync(auditRoot!,{recursive:true})
  fs.writeFileSync(path.join(auditRoot!,'coverage-matrix.json'),JSON.stringify({coverage,rows},null,2))
  fs.writeFileSync(path.join(auditRoot!,'cases.json'),JSON.stringify({cases:[...originals,...newCases,...examples],coverage},null,2))
  fs.writeFileSync(path.join(auditRoot!,'music-list.json'),JSON.stringify(tracks.map(t=>({id:t.id,title:t.title,group:oldIds.has(t.id)?'original':'new',bpm:t.bpm,modelStyle:t.style,reportId:t.reportId,source:t.provenance})),null,2))
  console.log(JSON.stringify(coverage))
},240000)
