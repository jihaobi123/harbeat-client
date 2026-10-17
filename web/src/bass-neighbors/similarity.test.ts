import {describe,it,expect} from 'vitest'
import {evaluateNeighbor,type NeighborVector} from './similarity'
const anchor:NeighborVector={bpm:[125,125],sourceTags:['EDM'],destinationTags:['house'],styles:['House','House'],vocals:[0,1],bars:4,harmonicBonus:.064}
describe('frozen-plan neighbor selection',()=>{
 it('prefers a matching neighbor without changing the supplied evidence',()=>{
  const close:NeighborVector={...anchor,bpm:[124,125]},far:NeighborVector={...anchor,bpm:[120,121],destinationTags:['KPOP'],styles:['Tropical House','K-pop']}
  const before=JSON.stringify([anchor,close,far])
  expect(evaluateNeighbor(anchor,close,['EDM','house']).distance!).toBeLessThan(evaluateNeighbor(anchor,far,['EDM','house']).distance!)
  expect(JSON.stringify([anchor,close,far])).toBe(before)
 })
 it('rejects distant tempo and unrelated source tags before ranking',()=>{
  expect(evaluateNeighbor(anchor,{...anchor,bpm:[140,140]},['EDM']).reasons).toContain('tempo-distance')
  expect(evaluateNeighbor(anchor,{...anchor,sourceTags:['funk']},['EDM','house']).reasons).toContain('source-family')
 })
 it('matches the observed vocal handoff direction rather than moving cue points',()=>{
  expect(evaluateNeighbor(anchor,{...anchor,vocals:[1,0]},['EDM']).reasons).toContain('vocal-direction')
  expect(evaluateNeighbor(anchor,{...anchor,vocals:[0,.8]},['EDM']).eligible).toBe(true)
  expect(evaluateNeighbor(anchor,{...anchor,vocals:[0,.4]},['EDM']).eligible).toBe(false)
 })
 it('rejects missing/nonfinite measurement evidence',()=>{
  expect(evaluateNeighbor(anchor,{...anchor,bpm:[NaN,125]},['EDM']).eligible).toBe(false)
  expect(evaluateNeighbor(anchor,{...anchor,bars:0},['EDM']).eligible).toBe(false)
 })
})

import {isRejectedWindow} from './similarity'
describe('audibility rejections stay on frozen source windows',()=>{
 const plan={id:'pair-1',from:'a',to:'b',start:100,end:108,rate:1,window:{start:20,end:28}}
 it('rejects the same measured outgoing window across target songs, but not another part of the song',()=>{
  const rejected=[{side:'a',trackId:'a',sourceStart:100,sourceEnd:108}]
  expect(isRejectedWindow(plan,rejected)).toBe(true)
  expect(isRejectedWindow({...plan,start:120,end:128},rejected)).toBe(false)
 })
 it('rejects only the same incoming source window, and also supports an exact plan rejection',()=>{
  expect(isRejectedWindow(plan,[{side:'b',trackId:'b',sourceStart:20,sourceEnd:28,rate:1}])).toBe(true)
  expect(isRejectedWindow(plan,[{side:'b',trackId:'b',sourceStart:40,sourceEnd:48}])).toBe(false)
  expect(isRejectedWindow({...plan,id:'pair-2',rate:1.02},[{side:'b',trackId:'b',sourceStart:20,sourceEnd:28,rate:1}])).toBe(false)
  expect(isRejectedWindow(plan,[{planId:'pair-1'}])).toBe(true)
 })
})
