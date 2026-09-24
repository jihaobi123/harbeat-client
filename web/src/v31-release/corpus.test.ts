import {it,expect} from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import {planV31} from './release'
import {makeV30Planner} from '../v30/planner'
import type {Track} from '../realtime/planner'

const root=process.env.V31_RELEASE_CORPUS,reference=process.env.V31_ACCEPTED_REFERENCE
it.skipIf(!root)('preserves all original twenty cases, including unavailable transitions',()=>{
 const tracks:Track[]=JSON.parse(fs.readFileSync(path.join(root!,'catalog.json'),'utf8')).tracks
 const cases=JSON.parse(fs.readFileSync(path.join(root!,'cases.json'),'utf8')).cases
 expect(tracks).toHaveLength(20);expect(cases).toHaveLength(20)
 for(const c of cases){
  const input=[tracks.find(t=>t.id===c.a)!,tracks,c.position,{kind:'next' as const,targetId:c.b},new Set<string>(),18,false] as const
  expect(planV31(...input)).toEqual(makeV30Planner(false,'dynamic')(...input))
 }
})
it.skipIf(!root||!reference)('reproduces the eighteen accepted feedback plans and exact EQ curves saved before promotion',()=>{
 const tracks:Track[]=JSON.parse(fs.readFileSync(path.join(root!,'catalog.json'),'utf8')).tracks
 const rows=JSON.parse(fs.readFileSync(reference!,'utf8')).rows
 expect(rows).toHaveLength(18)
 for(const r of rows){
  const p=planV31(tracks.find(t=>t.id===r.aId)!,tracks,r.position,{kind:'next',targetId:r.bId},new Set(),18,false).best!
  expect(p).toBeTruthy();expect(p.id).toBe(r.planId)
  for(const field of ['start','end','duration','rate','midDuck'] as const)expect(p[field]).toBe(r[field])
  expect(p.window.start).toBe(r.bStart);expect(p.window.end).toBe(r.bEnd)
  expect(p.v30Eq!.a).toEqual(r.curves.a);expect(p.v30Eq!.b).toEqual(r.curves.b)
  expect(p.v30Eq!.evidence).toEqual(r.evidence);expect(p.v30Eq!.sources).toEqual(r.sources)
  expect(p.v30Tune!.shiftSec).toBe(0);expect(p.phrase).toBeUndefined();expect(p.automation).toBeUndefined()
 }
})
