import {it,expect} from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {planNext,type Track} from '../realtime/planner'
import {makeV30Planner} from './planner'
const root=process.env.V30_CORPUS
it.skipIf(!root)('audits original twenty cases plus source-position sweeps without shortening any overlap',()=>{
 const tracks:Track[]=JSON.parse(fs.readFileSync(path.join(root!,'catalog.json'),'utf8')).tracks
 const pack=JSON.parse(fs.readFileSync(path.join(root!,'cases.json'),'utf8')),original=pack.cases.filter((c:any)=>c.group==='original20'),rows:any[]=[],extra:any[]=[]
 for(const c of original){const a=tracks.find(t=>t.id===c.a)!;const positions=[c.position,...[0,10,20,40,60,80,100].filter(p=>p<a.duration-20&&p!==c.position)]
 for(const pos of positions){const input=[a,tracks,pos,{kind:'next' as const,targetId:c.b},new Set<string>(),18,false] as const,old=planNext(...input).best,f=makeV30Planner(true,'fixed')(...input).best,d=makeV30Planner(true,'dynamic')(...input).best
 if(!old){expect(f).toBeNull();rows.push({a:c.a,b:c.b,position:pos,available:false,originalCase:pos===c.position});continue}
 expect(f).toBeTruthy();expect(d).toBeTruthy();expect(d!.id).toBe(f!.id);expect(f!.duration).toBe(old.duration);expect(f!.asset).toEqual(old.asset);expect(f!.window).toEqual(old.window);expect(f!.rate).toBe(old.rate);expect(f!.end).toBeLessThanOrEqual(pos+18);expect(f!.automation).toBeUndefined();expect(f!.phrase).toBeUndefined()
 const row={a:c.a,b:c.b,position:pos,available:true,originalCase:pos===c.position,shiftSec:f!.v30Tune!.shiftSec,duration:f!.duration,oldEnd:old.end,newEnd:f!.end,reason:f!.v30Tune!.reason,eqChanged:d!.v30Eq!.b.some(p=>Math.abs(p.low+7)>.01||Math.abs(p.mid-(d!.midDuck?-5:0))>.01),maxEqOffset:Math.max(...d!.v30Eq!.b.map(p=>Math.abs(p.low+7)))}
 rows.push(row);if(row.shiftSec>0&&extra.length<6&&!extra.some(e=>e.a===c.a))extra.push({id:`shift:${c.a}:${c.b}:${pos}`,a:c.a,b:c.b,position:pos,group:'boundary_examples'})
 }}
 // Search other pairings within the same twenty tracks for explicitly labelled correction examples.
 let pairChecks=0
 for(const a of tracks)for(const b of tracks){if(a===b)continue;for(const pos of [15,30,45,60,80]){
  pairChecks++;const input=[a,tracks,pos,{kind:'next' as const,targetId:b.id},new Set<string>(),18,false] as const
  const old=planNext(...input).best,f=makeV30Planner(true,'fixed')(...input).best
  if(!old){expect(f).toBeNull();continue}expect(f!.duration).toBe(old.duration);expect(f!.asset).toEqual(old.asset)
  if(f!.v30Tune!.shiftSec>0&&extra.length<6&&!extra.some(e=>e.a===a.id)){
   const d=makeV30Planner(true,'dynamic')(...input).best;expect(d?.id).toBe(f!.id)
   extra.push({id:`shift:${a.id}:${b.id}:${pos}`,a:a.id,b:b.id,position:pos,group:'boundary_examples'})
  }
 }}
 const audit={checks:rows.length,pairChecks,originalCases:rows.filter(r=>r.originalCase),eligible:rows.filter(r=>r.available).length,shifted:rows.filter(r=>r.shiftSec>0).length,examples:extra,rows}
 fs.writeFileSync(path.join(root!,'audit.json'),JSON.stringify(audit,null,2));fs.writeFileSync(path.join(root!,'cases.json'),JSON.stringify({cases:[...original,...extra],coverage:{tracks:tracks.length,checks:rows.length,eligible:audit.eligible,shifted:audit.shifted}},null,2))
 console.log(JSON.stringify({checks:audit.checks,eligible:audit.eligible,shifted:audit.shifted,originalEligible:audit.originalCases.filter(r=>r.available).length,extra:extra.length}))
})
