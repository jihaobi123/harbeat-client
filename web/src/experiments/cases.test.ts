import {it,expect} from 'vitest'
import {readFileSync,writeFileSync} from 'node:fs'
import {buildFixedCases,buildRankingCases,comparisonKey} from './cases'
import {fixedTrial,type LengthAsset} from './trials'
const path=process.env.LIVE_CATALOG
it('keeps feedback separate by experiment, case and exact plan',()=>{
 expect(comparisonKey('catalog','eq','case1','plan1')).not.toBe(comparisonKey('catalog','eq','case2','plan1'))
 expect(comparisonKey('catalog','eq','case1','plan1')).not.toBe(comparisonKey('catalog','eq','case1','plan2'))
})
it.skipIf(!path)('offers diverse reproducible cases and preserves each fixed comparison',()=>{
 const tracks=JSON.parse(readFileSync(path!,'utf8')).tracks
 const cases=buildFixedCases(tracks);expect(cases).toHaveLength(12);expect(new Set(cases.map(c=>c.aId+':'+c.bId)).size).toBe(12)
 expect(new Set(cases.flatMap(c=>[c.aId,c.bId])).size).toBe(6);expect(new Set(cases.map(c=>c.aId)).size).toBeGreaterThanOrEqual(5)
 expect(buildFixedCases(tracks)).toEqual(cases)
 for(const c of cases){
  const eq=fixedTrial(tracks,'eq',undefined,c),m=fixedTrial(tracks,'material',undefined,c)
  expect(eq.variant.from).toBe(c.aId);expect(eq.variant.to).toBe(c.bId);expect(eq.variant.asset.sha256).toBe(eq.baseline.asset.sha256);expect(eq.variant.decision!.strategy.midDuck.bMidDb).toBe(-8)
  expect(m.variant.asset.sha256).not.toBe(m.baseline.asset.sha256);expect(m.variant.start).toBe(m.baseline.start);expect(m.variant.end).toBe(m.baseline.end);expect(m.variant.duration).toBe(m.baseline.duration);expect(m.variant.rate).toBeCloseTo(m.baseline.rate,8)
  const p=eq.baseline,b=tracks.find((t:any)=>t.id===c.bId),duration=p.duration/2
  let tail:LengthAsset={sourceTrackId:b.id,sourceMasterSha256:b.provenance.masterSha256,start:(p.window.start+p.window.end)/2,end:p.window.end,rate:p.rate,asset:{...p.asset,duration}}
  if(process.env.CASE_LENGTH_ASSETS){const assets=JSON.parse(readFileSync(process.env.CASE_LENGTH_ASSETS,'utf8'));expect(Object.keys(assets)).toHaveLength(12);tail=assets[c.id];expect(tail).toBeDefined()}
  const l=fixedTrial(tracks,'length',tail,c);expect(l.variant.end).toBe(l.baseline.end);expect(l.variant.window.end).toBe(l.baseline.window.end);expect(l.variant.duration*2).toBeCloseTo(l.baseline.duration,4);expect(l.variant.gridError).toBeLessThanOrEqual(.065)
 }
 const ranks=buildRankingCases(tracks);expect(ranks).toHaveLength(12);expect(new Set(ranks.map(c=>c.aId)).size).toBe(6);expect(ranks.some(c=>tracks.find((t:any)=>t.id===c.aId).title==='FREE BRO'&&c.position===5)).toBe(true)
 if(process.env.CASE_OUTPUT)writeFileSync(process.env.CASE_OUTPUT,JSON.stringify({cases,rankingCases:ranks,inputs:cases.map(c=>{const f=fixedTrial(tracks,'eq',undefined,c);return {caseId:c.id,sourceTrackId:f.b.id,sourceMasterSha256:f.b.provenance!.masterSha256,runId:f.b.provenance!.runId,start:(f.baseline.window.start+f.baseline.window.end)/2,end:f.baseline.window.end,rate:f.baseline.rate,targetDuration:f.baseline.duration/2}})},null,2))
})
