import {describe, expect, it} from 'vitest'
import {alignedVocalOverlap} from './score'

const mapping = {aStart: 0, bStart: 0, bEnd: 10, duration: 10, rate: 1}
describe('aligned vocal overlap', () => {
  it('distinguishes staggered voices from simultaneous voices with equal marginal coverage', () => {
    const staggered = alignedVocalOverlap([[1,4]], [[6,9]], mapping)
    const simultaneous = alignedVocalOverlap([[1,4]], [[1,4]], mapping)
    expect(staggered.weightedOverlap).toBe(0)
    expect(staggered.simultaneousSec).toBe(0)
    expect(simultaneous.simultaneousSec).toBeCloseTo(3.6)
    expect(simultaneous.weightedOverlap).toBeGreaterThan(0)
  })
  it('normalizes continuous simultaneous vocals to one and silence to zero', () => {
    expect(alignedVocalOverlap([[0,10]], [[0,10]], mapping).weightedOverlap).toBeCloseTo(1)
    expect(alignedVocalOverlap([], [[0,10]], mapping).weightedOverlap).toBe(0)
  })
  it('weights the same collision duration more strongly in the middle than at either edge', () => {
    const early = alignedVocalOverlap([[.3,1.7]], [[.3,1.7]], mapping)
    const middle = alignedVocalOverlap([[4.3,5.7]], [[4.3,5.7]], mapping)
    const late = alignedVocalOverlap([[8.3,9.7]], [[8.3,9.7]], mapping)
    expect(early.simultaneousSec).toBeCloseTo(middle.simultaneousSec)
    expect(early.weightedOverlap).toBeCloseTo(late.weightedOverlap)
    expect(middle.weightedOverlap).toBeGreaterThan(early.weightedOverlap)
    expect(middle.weightedOverlap).toBeCloseTo(.296)
  })
  it.each([.8, 1.2])('maps B source intervals using rate %s, with padding before mapping', rate => {
    const evidence = alignedVocalOverlap([[22,26]], [[100 + 3*rate,100 + 5*rate]],
      {aStart:20,bStart:100,bEnd:100+10*rate,duration:10,rate})
    expect(evidence.aIntervals[0]).toEqual([1.6999999999999993,6.300000000000001])
    expect(evidence.bIntervals[0][0]).toBeCloseTo(3-.3/rate)
    expect(evidence.bIntervals[0][1]).toBeCloseTo(5+.3/rate)
    expect(evidence.simultaneousSec).toBeCloseTo(2+.6/rate)
  })
  it('merges duplicates and intersections without double counting and keeps source rows', () => {
    const single = alignedVocalOverlap([[1,8]], [[2,7]], mapping)
    const duplicate = alignedVocalOverlap([[1,5],[4,8],[1,5]], [[2,7],[2,7]], mapping)
    expect(duplicate.weightedOverlap).toBeCloseTo(single.weightedOverlap)
    expect(duplicate.simultaneousSec).toBeCloseTo(single.simultaneousSec)
    expect(duplicate.aRows).toEqual([1,2,3])
    expect(duplicate.bRows).toEqual([1,2])
  })
  it('clips source activity to the entry and exit boundaries', () => {
    const evidence = alignedVocalOverlap([[0,80]], [[0,200]],
      {aStart:20,bStart:100,bEnd:108,duration:10,rate:.8})
    expect(evidence.aIntervals).toEqual([[0,10]])
    expect(evidence.bIntervals).toEqual([[0,10]])
    expect(evidence.weightedOverlap).toBeCloseTo(1)
  })
  it('rejects unknown or malformed evidence instead of treating it as silence', () => {
    expect(() => alignedVocalOverlap(null, [], mapping)).toThrow()
    expect(() => alignedVocalOverlap([[2,1]], [], mapping)).toThrow()
    expect(() => alignedVocalOverlap([[0,NaN]], [], mapping)).toThrow()
    expect(() => alignedVocalOverlap([], [], {...mapping,rate:0})).toThrow()
    expect(() => alignedVocalOverlap([], [], {...mapping,duration:0})).toThrow()
    expect(() => alignedVocalOverlap([], [], {...mapping,bEnd:8})).toThrow()
  })
})
