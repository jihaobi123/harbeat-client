import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { EdmStructureCandidatePanel, InstrumentCandidatePanel } from './AnnotationWorkbench'
import type { EdmStructureAnalysisDocument, InstrumentAnalysisDocument } from '../types/annotation'


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


const edmCandidates: EdmStructureAnalysisDocument = {
  schema_name: 'harbeat.edm_structure_analysis',
  schema_version: '0.1.0',
  track_id: 'track-1',
  status: 'ready',
  duration_sec: 4,
  audio_sha256: 'a'.repeat(64),
  timeline_fingerprint: 'b'.repeat(64),
  songformer_sidecar_sha256: 'c'.repeat(64),
  muq_sha256: 'd'.repeat(64),
  musicfm_sha256: 'e'.repeat(64),
  musicfm_stats_sha256: 'f'.repeat(64),
  edmformer_sha256: '1'.repeat(64),
  deployment_status: 'shadow',
  aggregation_version: 'edmformer_songformer_block_aggregation_v1',
  runtime_fingerprint: { runner_version: 'test' },
  segments: [{
    canonical_section_id: 'section-1',
    start_bar_index: 0,
    end_bar_index: 1,
    start_sec: 0,
    end_sec: 4,
    canonical_boundary_source: 'songformer_bar_snap_v1',
    edmformer_label_candidate: 'drop',
    edmformer_label_probabilities: {
      intro: 0.05, buildup: 0.1, drop: 0.7, breakdown: 0.05, outro: 0.05, silence: 0.05,
    },
    edmformer_label_max_probabilities: {
      intro: 0.1, buildup: 0.2, drop: 0.9, breakdown: 0.1, outro: 0.1, silence: 0.1,
    },
    edmformer_boundary_candidates: [2.1],
    validation_status: 'unreviewed',
  }],
  expanded_structure_head: {
    enabled: false,
    model_status: 'not_installed',
    model_version: null,
    input_contract_version: 'expanded_structure_input_v1',
    output_contract_version: 'expanded_structure_output_v1',
  },
  warnings: [],
  error: null,
}


describe('EdmStructureCandidatePanel', () => {
  it('shows all six shadow probabilities without replacing SongFormer boundaries', () => {
    const html = renderToStaticMarkup(
      <EdmStructureCandidatePanel
        candidates={edmCandidates}
        selectedRange={{ start: 0, end: 1 }}
        onSeek={() => undefined}
      />,
    )
    expect(html).toContain('EDMFormer Shadow 候选')
    expect(html).toContain('Drop')
    expect(html).toContain('70%')
    expect(html).toContain('ExpandedStructureHead：未安装')
    expect(html).toContain('2.10 秒')
  })
})
