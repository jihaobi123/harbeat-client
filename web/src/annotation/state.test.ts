import { describe, expect, it } from 'vitest'
import type {
  AnnotationDraft,
  AnnotationRecord,
  AnnotationTaskId,
  CandidateBar,
} from '../types/annotation'
import { applyRangeLabel, candidateSourceForBar, normalizeRange, recordsFor } from './state'


function bars(count = 8): CandidateBar[] {
  return Array.from({ length: count }, (_, index) => ({
    bar_index: index,
    start_sec: index * 2,
    end_sec: (index + 1) * 2,
    beat_times_sec: [index * 2],
    is_partial: false,
    section: { value: 'unknown', confidence: null, source: null, source_label: null },
    elements: {
      drums: { value: 'unknown', activity: null, confidence: null, source: null },
      vocal: { value: 'unknown', activity: null, confidence: null, source: null },
      bass: { value: 'unknown', activity: null, confidence: null, source: null },
      melody: { value: 'unknown', activity: null, confidence: null, source: null },
    },
  }))
}


function draft(annotations: AnnotationRecord[] = []): AnnotationDraft {
  return {
    datasetVersion: 'bar-understanding-1.0.0',
    trackId: 'track-1',
    annotatorId: 'producer-7',
    bars: bars(),
    annotations,
  }
}


function record(
  taskId: AnnotationTaskId,
  start: number,
  end: number,
  value: AnnotationRecord['value'],
): AnnotationRecord {
  return {
    schema_name: 'harbeat.annotation_record',
    schema_version: '1.0.0',
    annotation_id: `ann-${taskId}-${start}-${end}`.replace(/_/g, '-'),
    dataset_version: 'bar-understanding-1.0.0',
    track_id: 'track-1',
    task_id: taskId,
    granularity: taskId === 'structure.section_label' ? 'section' : 'bar',
    start_sec: start * 2,
    end_sec: end * 2,
    start_bar_index: start,
    end_bar_index: end,
    value,
    annotator_id: 'producer-7',
    annotation_status: 'annotated',
    annotator_confidence: null,
    candidate_source: null,
    created_at: '2026-08-30T09:00:00.000Z',
  }
}


describe('annotation editor state', () => {
  it('normalizes reversed inclusive selections to a half-open Bar range', () => {
    expect(normalizeRange(6, 2, 8)).toEqual({ start: 2, end: 7 })
    expect(normalizeRange(-3, 99, 8)).toEqual({ start: 0, end: 8 })
  })

  it('applies one Section label to a half-open Bar range', () => {
    const updated = applyRangeLabel(
      draft(),
      { start: 2, end: 6 },
      'structure.section_label',
      'build',
      '2026-08-30T09:00:00.000Z',
    )

    expect(updated.annotations).toHaveLength(1)
    expect(updated.annotations[0].start_bar_index).toBe(2)
    expect(updated.annotations[0].end_bar_index).toBe(6)
    expect(updated.annotations[0].start_sec).toBe(4)
    expect(updated.annotations[0].end_sec).toBe(12)
  })

  it('replaces only the selected overlap and leaves other tasks untouched', () => {
    const drums = record('elements.drums.state', 0, 8, 'foreground')
    const vocal = record('elements.vocal.state', 0, 8, 'background')

    const updated = applyRangeLabel(
      draft([drums, vocal]),
      { start: 2, end: 5 },
      'elements.vocal.state',
      'foreground',
      '2026-08-30T09:00:00.000Z',
    )

    expect(recordsFor(updated, 'elements.drums.state')).toEqual([drums])
    expect(recordsFor(updated, 'elements.vocal.state').map(item => [
      item.start_bar_index,
      item.end_bar_index,
      item.value,
    ])).toEqual([
      [0, 2, 'background'],
      [2, 5, 'foreground'],
      [5, 8, 'background'],
    ])
  })

  it('preserves original fine labels and confidence in candidate provenance', () => {
    const bar = bars(1)[0]
    bar.section = {
      value: 'main',
      confidence: 0.78,
      source: 'analysis:phrase_map:v1',
      source_label: 'Drop 2',
    }

    const candidate = candidateSourceForBar(bar, 'structure.section_label')

    expect(candidate.value).toBe('main')
    expect(candidate.source).toContain('label=Drop%202')
    expect(candidate.source).toContain('confidence=0.78')
  })
})
