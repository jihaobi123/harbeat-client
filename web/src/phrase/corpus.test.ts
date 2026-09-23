import {it,expect} from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {makePhrasePlanner} from './planner'
import {gainAt} from './automation'
import {guardPlan} from '../guarded/planner'
import type {Track} from '../realtime/planner'
const root=process.env.PHRASE_CORPUS
it.skipIf(!root)('checks the real corpus, preserves paired EQ choices, and exports executable coverage',()=>{
 const catalog=JSON.parse(fs.readFileSync(path.join(root!,'catalog.json'),'utf8')),old=JSON.parse(fs.readFileSync(path.join(root!,'../v31-20260923/auto-catalog.json'),'utf8')),tracks:Track[]=catalog.tracks,cases:any[]=[],checked:any[]=[],summary:any[]=[]
 for(const mode of ['phrase','section'] as const){const fixed=makePhrasePlanner(tracks,mode,'fixed'),dynamic=makePhrasePlanner(tracks,mode,'adaptive');for(const a of tracks)for(const b of tracks){if(a===b)continue
 const first=fixed(a,tracks,0,{kind:'next',targetId:b.id},new Set(),a.duration,false).best
 if(!first){summary.push({a:a.id,b:b.id,mode,available:false});continue}
 const positions=[0,Math.max(0,first.start-8)]
 for(const position of positions){const args=[a,tracks,position,{kind:'next' as const,targetId:b.id},new Set<string>(),a.duration-position,false] as const,p=fixed(...args).best,q=dynamic(...args).best;expect(p).not.toBeNull();expect(q?.id).toBe(p!.id);expect(q?.automation?.aGain).toEqual(p?.automation?.aGain);expect(q?.automation?.bGain).toEqual(p?.automation?.bGain)
 const ev=p!.phrase!;expect(ev.incomingVocalRender).toBeGreaterThanOrEqual(ev.exit.tailEnd-.00001);expect(ev.vocalGap).toBeLessThanOrEqual(Math.max(1.2,120/a.bpm));expect(gainAt(p!.automation!.aGain,Math.max(0,ev.exit.tailEnd-p!.start))).toBe(1);expect(p!.start).toBeGreaterThan(position);expect(p!.end).toBeLessThan(a.duration)
 if(mode==='section')expect(ev.exit.sectionAligned).toBe(true)
 expect(q!.automation!.evidence.length).toBeGreaterThan(0)
 for(const e of q!.automation!.bEq){expect([e.low,e.mid,e.high].every(Number.isFinite)).toBe(true);expect(e.low).toBeGreaterThanOrEqual(-9);expect(e.mid).toBeGreaterThanOrEqual(-4);expect(e.high).toBeGreaterThanOrEqual(-3)}
 const paired=!!guardPlan(old,{},old.tracks.find((t:Track)=>t.id===a.id),old.tracks,position,args[3],new Set(),a.duration-position,false).best
 checked.push({a:a.id,b:b.id,position,mode,paired,plan:p!.id,vocalGap:ev.vocalGap,fadeSec:p!.end-ev.fadeStart,entry:p!.window.id,sourceRows:q!.automation!.evidence.length,minEqDb:Math.min(...q!.automation!.bEq.flatMap(e=>[e.low,e.mid,e.high]))})
 if(position===positions[1]&&!cases.some(c=>c.a===a.id&&c.b===b.id&&c.mode===mode))cases.push({a:a.id,b:b.id,position,mode,paired})
 }
 summary.push({a:a.id,b:b.id,mode,available:true})
 }}
 expect(checked.length).toBeGreaterThan(0)
 const doc={cases:cases.sort((a,b)=>Number(b.paired)-Number(a.paired)||a.mode.localeCompare(b.mode)),coverage:{tracks:tracks.length,checks:checked.length,orderedPairsChecked:summary.length,eligible:summary.filter((x:any)=>x.available).length},checked,summary};fs.writeFileSync(path.join(root!,'cases.json'),JSON.stringify(doc,null,2));console.log(JSON.stringify({coverage:doc.coverage,cases:cases.length,outgoing:[...new Set(cases.map(c=>tracks.find(t=>t.id===c.a)?.title))],incoming:[...new Set(cases.map(c=>tracks.find(t=>t.id===c.b)?.title))],sectionCases:cases.filter(c=>c.mode==='section').length,paired:cases.filter(c=>c.paired).length}))
})
