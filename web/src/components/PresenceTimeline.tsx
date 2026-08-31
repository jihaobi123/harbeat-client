import { useEffect, useMemo, useState } from 'react'

import type {
  PresenceBar,
  PresenceElement,
  PresenceElementCandidate,
  PresenceElementReview,
  PresenceReviewState,
} from '../types'
import { shouldCreateRangeFromPointer } from '../lib/presenceEditor'


const ELEMENT_INFO: Record<PresenceElement, { label: string; color: string }> = {
  vocal: { label: 'Vocal', color: '#ef5da8' },
  drums: { label: 'Drums', color: '#ff7a00' },
  bass: { label: 'Bass', color: '#00a67e' },
  melody: { label: 'Melody', color: '#5b6cff' },
}

interface ElementLaneState {
  candidate: PresenceElementCandidate
  review: PresenceElementReview
}

interface PresenceTimelineProps {
  bars: PresenceBar[]
  elements: Record<PresenceElement, ElementLaneState>
  currentTime: number
  selectedElement: PresenceElement
  onSelectElement: (element: PresenceElement) => void
  onSeek: (seconds: number) => void
  onAddRange: (element: PresenceElement, startBar: number, endBar: number) => void
  onResizeRange: (element: PresenceElement, index: number, startBar: number, endBar: number) => void
  onDeleteRange: (element: PresenceElement, index: number) => void
  onSplitRange: (element: PresenceElement, index: number, splitBar: number) => void
  onMergeRanges: (element: PresenceElement, indexes: number[]) => void
  onLoopRange: (startBar: number, endBar: number) => void
  onReviewStateChange: (element: PresenceElement, state: PresenceReviewState) => void
  onActiveRangeChange?: (element: PresenceElement, index: number) => void
}

type ResizeState = {
  element: PresenceElement
  rangeIndex: number
  edge: 'start' | 'end'
} | null

type DrawState = {
  element: PresenceElement
  startBar: number
  startClientX: number
} | null


function timePercent(seconds: number, start: number, duration: number): number {
  if (duration <= 0) return 0
  return Math.max(0, Math.min(100, ((seconds - start) / duration) * 100))
}


export default function PresenceTimeline({
  bars,
  elements,
  currentTime,
  selectedElement,
  onSelectElement,
  onSeek,
  onAddRange,
  onResizeRange,
  onDeleteRange,
  onSplitRange,
  onMergeRanges,
  onLoopRange,
  onReviewStateChange,
  onActiveRangeChange,
}: PresenceTimelineProps) {
  const [drawState, setDrawState] = useState<DrawState>(null)
  const [resizeState, setResizeState] = useState<ResizeState>(null)
  const [selectedRanges, setSelectedRanges] = useState<Record<PresenceElement, number[]>>({
    vocal: [], drums: [], bass: [], melody: [],
  })
  const startSec = bars[0]?.start_sec ?? 0
  const endSec = bars.at(-1)?.end_sec ?? 0
  const duration = Math.max(0, endSec - startSec)
  const columns = useMemo(
    () => bars.map(bar => `${Math.max(0.001, bar.end_sec - bar.start_sec)}fr`).join(' '),
    [bars],
  )
  useEffect(() => {
    setSelectedRanges({ vocal: [], drums: [], bass: [], melody: [] })
  }, [elements])
  const clearSelectedRanges = (element: PresenceElement) => {
    setSelectedRanges(previous => ({ ...previous, [element]: [] }))
  }

  const barAtPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const ratio = rect.width ? (event.clientX - rect.left) / rect.width : 0
    const seconds = startSec + Math.max(0, Math.min(1, ratio)) * duration
    return bars.findIndex(bar => seconds >= bar.start_sec && seconds < bar.end_sec)
  }

  const finishPointerEdit = (event: React.PointerEvent<HTMLDivElement>) => {
    const barIndex = barAtPointer(event)
    if (
      drawState
      && drawState.element === selectedElement
      && barIndex >= 0
      && shouldCreateRangeFromPointer(drawState.startClientX, event.clientX)
    ) {
      onAddRange(
        drawState.element,
        Math.min(drawState.startBar, barIndex),
        Math.max(drawState.startBar, barIndex) + 1,
      )
    }
    setDrawState(null)
    setResizeState(null)
  }

  const movePointerEdit = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!resizeState) return
    const barIndex = barAtPointer(event)
    if (barIndex < 0) return
    const range = elements[resizeState.element].review.ranges[resizeState.rangeIndex]
    if (!range) return
    if (resizeState.edge === 'start' && barIndex < range.end_bar_index) {
      onResizeRange(
        resizeState.element,
        resizeState.rangeIndex,
        barIndex,
        range.end_bar_index,
      )
    }
    if (resizeState.edge === 'end' && barIndex + 1 > range.start_bar_index) {
      onResizeRange(
        resizeState.element,
        resizeState.rangeIndex,
        range.start_bar_index,
        barIndex + 1,
      )
    }
  }

  return (
    <div className="presence-timeline" aria-label="Bar presence annotation timeline">
      <div className="presence-ruler" style={{ gridTemplateColumns: columns }}>
        {bars.map(bar => (
          <button
            type="button"
            key={bar.index}
            className="presence-ruler-cell"
            onClick={() => onSeek(bar.start_sec)}
            title={`${bar.index + 1} · ${bar.start_sec.toFixed(2)}s`}
          >
            {bar.index % 4 === 0 ? bar.index + 1 : ''}
          </button>
        ))}
      </div>

      {(Object.keys(ELEMENT_INFO) as PresenceElement[]).map(element => {
        const info = ELEMENT_INFO[element]
        const lane = elements[element]
        const selected = selectedRanges[element]
        const selectedIntervals = selected
          .map(index => lane.review.ranges[index])
          .filter(Boolean)
          .sort((left, right) => left.start_bar_index - right.start_bar_index)
        const canMergeSelected = selectedIntervals.length >= 2 && selectedIntervals.every(
          (range, index) => index === 0 || range.start_bar_index <= selectedIntervals[index - 1].end_bar_index,
        )
        return (
          <section
            key={element}
            className={`presence-lane ${selectedElement === element ? 'is-selected' : ''}`}
            aria-label={`${info.label} presence lane`}
          >
            <div className="presence-lane-header">
              <button
                type="button"
                onClick={() => onSelectElement(element)}
                className="presence-element-button"
                style={{ borderLeftColor: info.color }}
              >
                {info.label}
              </button>
              <select
                aria-label={`${info.label} review state`}
                value={lane.review.review_state}
                onChange={event => onReviewStateChange(element, event.target.value as PresenceReviewState)}
              >
                <option value="reviewed">已复核</option>
                <option value="unknown">无法判断</option>
                <option value="rejected">候选无效</option>
              </select>
              {canMergeSelected && (
                <button type="button" onClick={() => {
                  onMergeRanges(element, selected)
                  clearSelectedRanges(element)
                }}>
                  合并 {selected.length} 段
                </button>
              )}
            </div>

            {element === 'melody' && (
              <p className="presence-melody-warning">Melody 为低置信候选，必须人工确认</p>
            )}

            <div
              className="presence-lane-body"
              onPointerMove={movePointerEdit}
              onPointerUp={finishPointerEdit}
              onPointerLeave={() => { setDrawState(null); setResizeState(null) }}
            >
              <div className="presence-probability-grid" style={{ gridTemplateColumns: columns }}>
                {bars.map((bar, barIndex) => {
                  const probability = lane.candidate.bar_probabilities[barIndex] ?? 0
                  return (
                    <button
                      type="button"
                      key={bar.index}
                      data-bar-index={bar.index}
                      className="presence-probability-cell"
                      style={{ backgroundColor: `${info.color}${Math.round(probability * 170 + 20).toString(16).padStart(2, '0')}` }}
                      onPointerDown={event => {
                        onSelectElement(element)
                        event.currentTarget.setPointerCapture(event.pointerId)
                        setDrawState({
                          element,
                          startBar: barIndex,
                          startClientX: event.clientX,
                        })
                      }}
                      onClick={() => onSeek(bar.start_sec)}
                      title={`${info.label} · Bar ${bar.index + 1} · ${(probability * 100).toFixed(0)}%`}
                    />
                  )
                })}
              </div>

              {lane.review.review_state === 'reviewed' && lane.review.ranges.map((range, rangeIndex) => {
                const rangeStart = bars[range.start_bar_index]?.start_sec ?? startSec
                const rangeEnd = bars[range.end_bar_index - 1]?.end_sec ?? rangeStart
                const isRangeSelected = selected.includes(rangeIndex)
                return (
                  <div
                    key={`${range.start_bar_index}-${range.end_bar_index}-${rangeIndex}`}
                    data-presence-range={`${range.start_bar_index}-${range.end_bar_index}`}
                    className={`presence-range ${isRangeSelected ? 'is-range-selected' : ''}`}
                    style={{
                      left: `${timePercent(rangeStart, startSec, duration)}%`,
                      width: `${timePercent(rangeEnd, startSec, duration) - timePercent(rangeStart, startSec, duration)}%`,
                      borderColor: info.color,
                    }}
                    onDoubleClick={() => {
                      onDeleteRange(element, rangeIndex)
                      clearSelectedRanges(element)
                    }}
                    onClick={event => {
                      event.stopPropagation()
                      onActiveRangeChange?.(element, rangeIndex)
                      if (event.metaKey || event.ctrlKey) {
                        setSelectedRanges(previous => ({
                          ...previous,
                          [element]: previous[element].includes(rangeIndex)
                            ? previous[element].filter(index => index !== rangeIndex)
                            : [...previous[element], rangeIndex],
                        }))
                        return
                      }
                      if (event.shiftKey) {
                        const rect = event.currentTarget.getBoundingClientRect()
                        const ratio = rect.width ? (event.clientX - rect.left) / rect.width : 0
                        const splitBar = range.start_bar_index + Math.floor(
                          ratio * (range.end_bar_index - range.start_bar_index),
                        )
                        if (splitBar > range.start_bar_index && splitBar < range.end_bar_index) {
                          onSplitRange(element, rangeIndex, splitBar)
                          clearSelectedRanges(element)
                        }
                        return
                      }
                      onLoopRange(range.start_bar_index, range.end_bar_index)
                    }}
                    title="点击循环播放；双击删除；Shift 点击拆分；Cmd/Ctrl 点击多选"
                  >
                    <button
                      type="button"
                      className="presence-resize-handle is-start"
                      aria-label={`Resize ${info.label} range start`}
                      onPointerDown={event => {
                        event.stopPropagation()
                        setResizeState({ element, rangeIndex, edge: 'start' })
                      }}
                    />
                    <span>{range.end_bar_index - range.start_bar_index} Bars</span>
                    <button
                      type="button"
                      className="presence-resize-handle is-end"
                      aria-label={`Resize ${info.label} range end`}
                      onPointerDown={event => {
                        event.stopPropagation()
                        setResizeState({ element, rangeIndex, edge: 'end' })
                      }}
                    />
                  </div>
                )
              })}

              {duration > 0 && currentTime >= startSec && currentTime <= endSec && (
                <div
                  className="presence-playhead"
                  style={{ left: `${timePercent(currentTime, startSec, duration)}%` }}
                />
              )}
            </div>
          </section>
        )
      })}
    </div>
  )
}
