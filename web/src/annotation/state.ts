import type {
  AnnotationDraft,
  AnnotationRecord,
  AnnotationTaskId,
  AnnotationValue,
  BarRange,
  CandidateBar,
  ElementState,
  SectionLabel,
} from '../types/annotation'


const SECTION_VALUES = new Set<SectionLabel>([
  'intro', 'main', 'build', 'breakdown', 'outro', 'unknown',
])
const ELEMENT_VALUES = new Set<ElementState>([
  'absent', 'background', 'foreground', 'entering', 'ending', 'unknown',
])


export function normalizeRange(
  start: number,
  endInclusive: number,
  barCount: number,
): BarRange {
  if (barCount <= 0) return { start: 0, end: 0 }
  const first = Math.max(0, Math.min(barCount - 1, Math.min(start, endInclusive)))
  const last = Math.max(0, Math.min(barCount - 1, Math.max(start, endInclusive)))
  return { start: first, end: last + 1 }
}


function recordId(
  trackId: string,
  taskId: AnnotationTaskId,
  start: number,
  end: number,
): string {
  return `ann:${trackId}:${taskId}:${start}-${end}`.replace(/[^A-Za-z0-9._:-]/g, '-')
}


function resizedRecord(
  draft: AnnotationDraft,
  record: AnnotationRecord,
  start: number,
  end: number,
): AnnotationRecord {
  return {
    ...record,
    annotation_id: recordId(draft.trackId, record.task_id, start, end),
    start_bar_index: start,
    end_bar_index: end,
    start_sec: draft.bars[start].start_sec,
    end_sec: draft.bars[end - 1].end_sec,
  }
}


function validateTaskValue(taskId: AnnotationTaskId, value: AnnotationValue): void {
  if (taskId === 'structure.section_label') {
    if (!SECTION_VALUES.has(value as SectionLabel)) {
      throw new Error(`invalid Section value: ${value}`)
    }
    return
  }
  if (!ELEMENT_VALUES.has(value as ElementState)) {
    throw new Error(`invalid element value: ${value}`)
  }
}


export function recordsFor(
  draft: AnnotationDraft,
  taskId: AnnotationTaskId,
): AnnotationRecord[] {
  return draft.annotations
    .filter(record => record.task_id === taskId)
    .sort((left, right) => left.start_bar_index - right.start_bar_index)
}


function evidenceValue(value: number | null): string {
  return value === null ? 'unknown' : String(value)
}


export function candidateSourceForBar(
  bar: CandidateBar,
  taskId: AnnotationTaskId,
): { value: AnnotationValue; source: string | null } {
  if (taskId === 'structure.section_label') {
    const candidate = bar.section
    if (!candidate.source) return { value: candidate.value, source: null }
    const label = encodeURIComponent(candidate.source_label ?? '<unknown>')
    return {
      value: candidate.value,
      source: `${candidate.source}|label=${label}|confidence=${evidenceValue(candidate.confidence)}`,
    }
  }

  const element = taskId.split('.')[1] as keyof CandidateBar['elements']
  const candidate = bar.elements[element]
  if (!candidate.source) return { value: candidate.value, source: null }
  return {
    value: candidate.value,
    source: [
      candidate.source,
      `activity=${evidenceValue(candidate.activity)}`,
      `confidence=${evidenceValue(candidate.confidence)}`,
    ].join('|'),
  }
}


export function applyRangeLabel(
  draft: AnnotationDraft,
  requestedRange: BarRange,
  taskId: AnnotationTaskId,
  value: AnnotationValue,
  createdAt = new Date().toISOString(),
  candidateSource: string | null = null,
): AnnotationDraft {
  validateTaskValue(taskId, value)
  const start = Math.max(0, Math.min(draft.bars.length, requestedRange.start))
  const end = Math.max(0, Math.min(draft.bars.length, requestedRange.end))
  if (start >= end || !draft.bars[start] || !draft.bars[end - 1]) {
    throw new Error('the selected Bar range is empty or outside the timeline')
  }

  const untouched: AnnotationRecord[] = []
  const remainders: AnnotationRecord[] = []
  for (const record of draft.annotations) {
    const overlaps = record.start_bar_index < end && record.end_bar_index > start
    if (record.task_id !== taskId || !overlaps) {
      untouched.push(record)
      continue
    }
    if (record.start_bar_index < start) {
      remainders.push(resizedRecord(draft, record, record.start_bar_index, start))
    }
    if (record.end_bar_index > end) {
      remainders.push(resizedRecord(draft, record, end, record.end_bar_index))
    }
  }

  const annotation: AnnotationRecord = {
    schema_name: 'harbeat.annotation_record',
    schema_version: '1.0.0',
    annotation_id: recordId(draft.trackId, taskId, start, end),
    dataset_version: draft.datasetVersion,
    track_id: draft.trackId,
    task_id: taskId,
    granularity: taskId === 'structure.section_label' ? 'section' : 'bar',
    start_sec: draft.bars[start].start_sec,
    end_sec: draft.bars[end - 1].end_sec,
    start_bar_index: start,
    end_bar_index: end,
    value,
    annotator_id: draft.annotatorId,
    annotation_status: 'annotated',
    annotator_confidence: null,
    candidate_source: candidateSource,
    created_at: createdAt,
  }

  return {
    ...draft,
    annotations: [...untouched, ...remainders, annotation].sort((left, right) => {
      const taskOrder = left.task_id.localeCompare(right.task_id)
      return taskOrder || left.start_bar_index - right.start_bar_index
    }),
  }
}
