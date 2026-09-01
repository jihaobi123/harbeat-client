import { describe, expect, it } from 'vitest'
import type { AnnotationRecord, SectionAnnotationBlock } from '../types/annotation'
import {
  blockContainingRange,
  defaultBlockIndex,
  defaultBlockSelection,
  nextBlockIndex,
} from './sectionBlocks'


function block(id: string, start: number, end: number): SectionAnnotationBlock {
  return {
    block_id: id,
    start_bar_index: start,
    end_bar_index: end,
    start_time: start * 2,
    end_time: end * 2,
    raw_start_time: start * 2,
    raw_end_time: end * 2,
    start_snap_error_sec: 0,
    end_snap_error_sec: 0,
    source: 'songformer_bar_snap_v1',
    source_segment_indexes: [start],
    needs_review: false,
    suppressed_boundary_count: 0,
    model_runtime_fingerprint: 'a'.repeat(64),
  }
}


function annotation(taskId: AnnotationRecord['task_id'], start: number, end: number): AnnotationRecord {
  return {
    schema_name: 'harbeat.annotation_record',
    schema_version: '1.0.0',
    annotation_id: `ann-${taskId}-${start}-${end}`.replace(/[^A-Za-z0-9._:-]/g, '-'),
    dataset_version: 'bar-understanding-1.0.0',
    track_id: 'track-1',
    task_id: taskId,
    granularity: 'bar',
    start_sec: start * 2,
    end_sec: end * 2,
    start_bar_index: start,
    end_bar_index: end,
    value: 'foreground',
    annotator_id: 'user:1',
    annotation_status: 'annotated',
    annotator_confidence: null,
    candidate_source: null,
    created_at: '2026-09-01T00:00:00Z',
  }
}


describe('SongFormer annotation block navigation', () => {
  const blocks = [block('block-1', 0, 4), block('block-2', 4, 8), block('block-3', 8, 12)]

  it('selects the first unfinished block', () => {
    const tasks: AnnotationRecord['task_id'][] = [
      'elements.drums.state',
      'elements.vocal.state',
      'elements.bass.state',
      'elements.melody.state',
    ]
    const completedFirst = tasks.map(task => annotation(task, 0, 4))

    expect(defaultBlockIndex(blocks, completedFirst)).toBe(1)
    expect(defaultBlockSelection(blocks, completedFirst)).toEqual({ start: 4, end: 8 })
  })

  it('returns the first block after every block is complete', () => {
    const tasks: AnnotationRecord['task_id'][] = [
      'elements.drums.state',
      'elements.vocal.state',
      'elements.bass.state',
      'elements.melody.state',
    ]
    const completed = blocks.flatMap(item => tasks.map(task => (
      annotation(task, item.start_bar_index, item.end_bar_index)
    )))

    expect(defaultBlockIndex(blocks, completed)).toBe(0)
  })

  it('moves to the next block and wraps', () => {
    expect(nextBlockIndex(blocks, 1)).toBe(2)
    expect(nextBlockIndex(blocks, 2)).toBe(0)
  })

  it('treats a manual subrange as part of its containing model block', () => {
    expect(blockContainingRange(blocks, { start: 5, end: 7 })?.block_id).toBe('block-2')
    expect(blockContainingRange(blocks, { start: 3, end: 5 })).toBeUndefined()
  })

  it('returns an empty selection when no model blocks exist', () => {
    expect(defaultBlockSelection([], [])).toEqual({ start: 0, end: 0 })
  })
})
