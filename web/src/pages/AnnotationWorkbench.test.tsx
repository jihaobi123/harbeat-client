import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { InstrumentCandidatePanel } from './AnnotationWorkbench'
import type { InstrumentAnalysisDocument } from '../types/annotation'


const candidates: InstrumentAnalysisDocument = {
  schema_name: 'harbeat.instrument_analysis',
  schema_version: '0.1.0',
  track_id: 'track-1',
  status: 'ready',
  duration_sec: 4,
  audio_sha256: 'f'.repeat(64),
  timeline_fingerprint: 'a'.repeat(64),
  taxonomy_version: 'instrument_taxonomy@0.1.0',
  aggregation_version: 'instrument_bar_aggregation_v1',
  runtime_fingerprint: { runner_version: 'test' },
  models: {
    adtof: { availability: 'available', deployment_status: 'shadow', error: null },
    panns: { availability: 'available', deployment_status: 'shadow', error: null },
  },
  bars: [{
    bar_index: 0,
    start_sec: 0,
    end_sec: 4,
    drum_events: [{
      time_sec: 1,
      drum_class: 'kick',
      confidence: 0.9,
      bar_index: 0,
      beat_index_in_bar: 1,
      beat_position: 2,
    }],
    drum_summary: {
      event_counts: { kick: 1, snare: 0, hihat: 0, tom: 0, cymbal: 0 },
      density_per_sec: 0.25,
    },
    instrument_probabilities: [{
      instrument_class: 'bass',
      mean_probability: 0.8,
      max_probability: 0.9,
      active_coverage: 1,
    }],
    validation_status: 'unreviewed',
  }],
  warnings: [],
}


describe('InstrumentCandidatePanel', () => {
  it('shows drum events and model candidates as unreviewed evidence', () => {
    const html = renderToStaticMarkup(
      <InstrumentCandidatePanel
        candidates={candidates}
        selectedRange={{ start: 0, end: 1 }}
        onSeek={() => undefined}
      />,
    )
    expect(html).toContain('五类鼓事件')
    expect(html).toContain('模型候选，不是人工真值')
    expect(html).toContain('贝斯')
    expect(html).toContain('1.00 秒')
  })
})
