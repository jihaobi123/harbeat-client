export type PlaybackMode = 'full' | 'range_preview' | 'range_loop'
export type PlaybackAction = 'continue' | 'pause' | 'loop'

export interface PlaybackInput {
  mode: PlaybackMode
  currentTime: number
  rangeStart: number
  rangeEnd: number
}


export function playbackAction(input: PlaybackInput): PlaybackAction {
  if (
    input.mode === 'full'
    || !Number.isFinite(input.rangeStart)
    || !Number.isFinite(input.rangeEnd)
    || input.rangeEnd <= input.rangeStart
    || input.currentTime < input.rangeEnd
  ) {
    return 'continue'
  }
  return input.mode === 'range_loop' ? 'loop' : 'pause'
}
