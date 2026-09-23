import {it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import {planNext} from './planner'
import {guardPlan,type GuardCatalog} from '../guarded/planner'
import {buildDecisionTrace} from './trace'
const root=process.env.DECISION_EVIDENCE_DIR
it.skipIf(!root)('preserves all real candidate rankings while linking raw section/vocal/RMS rows',()=>{
 const summary=[]
 for(const file of ['v3-catalog.json','auto-catalog.json']){
  const c=JSON.parse(readFileSync(`${root}/${file}`,'utf8')) as GuardCatalog
  const before=JSON.stringify(c),plain=JSON.parse(before) as GuardCatalog;plain.tracks.forEach(t=>delete t.preprocessing)
  let checked=0,accepted=0
  for(const a of c.tracks)for(const b of c.tracks)if(a.id!==b.id)for(const position of [0,15,30,60,90,110]){
   const intent={kind:'next' as const,targetId:b.id},budget=file==='auto-catalog.json'?a.duration-position:18
   const run=(cat:GuardCatalog)=>{const x=cat.tracks.find(t=>t.id===a.id)!;return file==='auto-catalog.json'?guardPlan(cat,{},x,cat.tracks,position,intent,new Set(),budget,false):planNext(x,cat.tracks,position,intent,new Set(),budget,false)}
   const r=run(c);expect(r).toEqual(run(plain));checked++
   if(!r.best)continue;accepted++;const trace=buildDecisionTrace(a,b,r.best)
   for(const [t,side] of [[a,trace.a],[b,trace.b]] as const){
    expect(side.binding).toBe('verified_snapshot');expect(side.sections.length).toBeGreaterThan(0);expect(side.sections.every(s=>s.sourceRows.length>0)).toBe(true)
    expect(side.vocals.rows.every(x=>x.sourceRow!==null)).toBe(true)
    expect(side.vocals.fraction).toBeCloseTo(t===a?r.best.aVocal:r.best.bVocal)
    if(side.acoustic){expect(side.acoustic.rows.length).toBeGreaterThan(0);const max=Math.max(...side.acoustic.rows.map(r=>r.rms_dbfs??-120));expect(max).toBeCloseTo(side.acoustic.evidence.maxRmsDbfs,5)}
   }
  }
  expect(JSON.stringify(c)).toBe(before);summary.push({file,checked,accepted})
 }
 console.log(JSON.stringify(summary))
})
