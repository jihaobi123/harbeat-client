import { describe, expect, it } from 'vitest'
import { playbackAction } from './playback'


describe('annotation playback modes', () => {
  it('does not stop full playback at the selected range end', () => {
    expect(playbackAction({
      mode: 'full',
      currentTime: 8,
      rangeStart: 0,
      rangeEnd: 4,
    })).toBe('continue')
  })

  it('stops a one-shot range preview at its end', () => {
    expect(playbackAction({
      mode: 'range_preview',
      currentTime: 4,
      rangeStart: 0,
      rangeEnd: 4,
    })).toBe('pause')
  })

  it('continues a range preview before its end', () => {
    expect(playbackAction({
      mode: 'range_preview',
      currentTime: 3.99,
      rangeStart: 0,
      rangeEnd: 4,
    })).toBe('continue')
  })

  it('seeks and continues only in range-loop mode', () => {
    expect(playbackAction({
      mode: 'range_loop',
      currentTime: 4,
      rangeStart: 0,
      rangeEnd: 4,
    })).toBe('loop')
  })

  it('fails open for an invalid range', () => {
    expect(playbackAction({
      mode: 'range_preview',
      currentTime: 10,
      rangeStart: 4,
      rangeEnd: 4,
    })).toBe('continue')
  })
})
