import { describe, expect, it } from 'vitest'

import {
  addRange,
  deleteRange,
  mergeRanges,
  resizeRange,
  splitRange,
} from './presenceEditor'


describe('presence interval editing', () => {
  it('normalizes overlapping ranges to half-open merged ranges', () => {
    expect(addRange([{ start_bar_index: 1, end_bar_index: 3 }], 2, 5))
      .toEqual([{ start_bar_index: 1, end_bar_index: 5 }])
  })

  it('deletes one range without mutating the original list', () => {
    const original = [
      { start_bar_index: 1, end_bar_index: 3 },
      { start_bar_index: 5, end_bar_index: 7 },
    ]
    expect(deleteRange(original, 0)).toEqual([
      { start_bar_index: 5, end_bar_index: 7 },
    ])
    expect(original).toHaveLength(2)
  })

  it('splits one range at an interior bar', () => {
    expect(splitRange([{ start_bar_index: 1, end_bar_index: 6 }], 0, 4))
      .toEqual([
        { start_bar_index: 1, end_bar_index: 4 },
        { start_bar_index: 4, end_bar_index: 6 },
      ])
  })

  it('resizes and re-normalizes a range', () => {
    expect(resizeRange([
      { start_bar_index: 1, end_bar_index: 3 },
      { start_bar_index: 5, end_bar_index: 7 },
    ], 0, 2, 6)).toEqual([
      { start_bar_index: 2, end_bar_index: 7 },
    ])
  })

  it('rejects a resize that creates an empty interval', () => {
    expect(() => resizeRange(
      [{ start_bar_index: 2, end_bar_index: 4 }],
      0,
      4,
      4,
    )).toThrow('range must contain at least one bar')
  })

  it('merges selected ranges and keeps unselected ranges', () => {
    expect(mergeRanges([
      { start_bar_index: 0, end_bar_index: 1 },
      { start_bar_index: 2, end_bar_index: 3 },
      { start_bar_index: 5, end_bar_index: 6 },
    ], [0, 1])).toEqual([
      { start_bar_index: 0, end_bar_index: 3 },
      { start_bar_index: 5, end_bar_index: 6 },
    ])
  })
})
