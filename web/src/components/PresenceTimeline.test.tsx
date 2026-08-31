import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import PresenceTimeline from './PresenceTimeline'
import type {
  PresenceBar,
  PresenceElement,
  PresenceElementCandidate,
  PresenceElementReview,
} from '../types'


const bars: PresenceBar[] = [
  { index: 0, start_sec: 0, end_sec: 2, beat_start_index: 0, beat_count: 4, is_partial: false },
  { index: 1, start_sec: 2, end_sec: 4, beat_start_index: 4, beat_count: 4, is_partial: false },
]

const candidate = (probabilities: number[]): PresenceElementCandidate => ({
  availability: 'available',
  requires_review: false,
  confidence_cap: 1,
  bar_probabilities: probabilities,
  bar_features: [],
  candidate_ranges: [{ start_bar_index: 0, end_bar_index: 1, confidence: 0.9 }],
  warnings: [],
})

const review = (state: PresenceElementReview['review_state']): PresenceElementReview => ({
  review_state: state,
  ranges: state === 'reviewed' ? [{ start_bar_index: 0, end_bar_index: 1 }] : [],
})


it('renders four Bar-aligned element lanes and reviewed regions', () => {
  const elements = Object.fromEntries(
    (['vocal', 'drums', 'bass', 'melody'] as PresenceElement[]).map(element => [
      element,
      {
        candidate: {
          ...candidate(element === 'vocal' ? [0.9, 0.1] : [0.2, 0.8]),
          requires_review: element === 'melody',
          confidence_cap: element === 'melody' ? 0.65 : 1,
        },
        review: review(element === 'melody' ? 'unknown' : 'reviewed'),
      },
    ]),
  ) as Record<PresenceElement, { candidate: PresenceElementCandidate; review: PresenceElementReview }>

  const html = renderToStaticMarkup(
    <PresenceTimeline
      bars={bars}
      elements={elements}
      currentTime={1}
      selectedElement="vocal"
      onSelectElement={vi.fn()}
      onSeek={vi.fn()}
      onAddRange={vi.fn()}
      onResizeRange={vi.fn()}
      onDeleteRange={vi.fn()}
      onSplitRange={vi.fn()}
      onMergeRanges={vi.fn()}
      onLoopRange={vi.fn()}
      onReviewStateChange={vi.fn()}
    />,
  )

  expect(html).toContain('aria-label="Vocal presence lane"')
  expect(html).toContain('aria-label="Drums presence lane"')
  expect(html).toContain('aria-label="Bass presence lane"')
  expect(html).toContain('aria-label="Melody presence lane"')
  expect(html).toContain('data-bar-index="0"')
  expect(html).toContain('aria-label="Vocal Bar 1, confidence 90%"')
  expect(html).toContain('data-presence-range="0-1"')
  expect(html).toContain('Melody 为低置信候选')
})
