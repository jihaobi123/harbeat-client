import {describe,expect,it} from 'vitest'
import {harmonicBonus,rankFrozen,type KeySource,type Candidate} from './ranking'

function source(camelot='8A',needsReview=false):KeySource {
 return {masterSha256:'master',runId:'run',key:{camelot,needsReview,verified:!needsReview,masterSha256:'master',runId:'run'}}
}
const candidate=(id:string,score:number,camelot:string,needsReview=false):Candidate<{cue:number}>=>(
 {...source(camelot,needsReview),id,score,plan:Object.freeze({cue:12})})

describe('bounded harmonic preference',()=>{
 it.each([['8A','8A',.08],['12A','1A',.064],['1A','12A',.064],['8A','7A',.064],['8A','8B',.064],['8B','8A',.064],['8A','9B',0],['8A','2A',0]])('%s to %s', (a,b,bonus)=>{
  expect(harmonicBonus(source(a),source(b))).toBeCloseTo(bonus)
 })
 it.each(['','0A','13A','8C','8a',' 8A','NaN'])('does not score malformed Camelot %s',key=>{
  expect(harmonicBonus(source(),source(key))).toBe(0)
 })
 it('requires both records and exact source/run binding',()=>{
  const missing=source();delete missing.key
  expect(harmonicBonus(source(),missing)).toBe(0)
  const stale=source();stale.key!.masterSha256='another'
  expect(harmonicBonus(source(),stale,true)).toBe(0)
  stale.key!.masterSha256='master';stale.key!.runId='another'
  expect(harmonicBonus(stale,source(),true)).toBe(0)
 })
 it('keeps provisional labels neutral unless the isolated audition opts in',()=>{
  expect(harmonicBonus(source('8A',true),source())).toBe(0)
  expect(harmonicBonus(source(),source('8A',true))).toBe(0)
  expect(harmonicBonus(source('8A',true),source('8A',true),true)).toBe(.08)
  const unverified=source();unverified.key!.verified=false
  expect(harmonicBonus(source(),unverified)).toBe(0)
 })
 it('reranks only the supplied safe plans without rewriting scores or plans',()=>{
  const a=source(),rows=Object.freeze([Object.freeze(candidate('first',1,'2A')),Object.freeze(candidate('compatible',.96,'8A'))])
  const before=JSON.stringify(rows),ranked=rankFrozen(a,rows)
  expect(ranked.map(x=>x.id)).toEqual(['compatible','first'])
  expect(ranked[0].score).toBe(.96);expect(ranked[0].bonus).toBe(.08)
  expect(ranked[0].plan).toBe(rows[1].plan);expect(JSON.stringify(rows)).toBe(before)
 })
 it('falls back exactly for the audited all-provisional library',()=>{
  const rows=[candidate('first',1,'2A',true),candidate('second',.96,'8A',true)]
  const result=rankFrozen(source('8A',true),rows)
  expect(result.map(x=>x.id)).toEqual(rows.map(x=>x.id));expect(result.every(x=>x.bonus===0)).toBe(true)
 })
 it('preserves original order for ties and cannot overcome a gap greater than its cap',()=>{
  const rows=[candidate('z',1,'2A'),candidate('a',1,'2A'),candidate('third',.90,'8A')]
  expect(rankFrozen(source(),rows).map(x=>x.id)).toEqual(['z','a','third'])
 })
 it('rejects nonfinite base scores rather than returning an arbitrary winner',()=>{
  expect(()=>rankFrozen(source(),[candidate('bad',NaN,'8A')])).toThrow('finite')
 })
})
