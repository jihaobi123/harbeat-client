import type {
  AnnotationRecord,
  AnnotationTaskId,
  BarRange,
  SectionAnnotationBlock,
} from '../types/annotation'


const ELEMENT_TASKS: AnnotationTaskId[] = [
  'elements.drums.state',
  'elements.vocal.state',
  'elements.bass.state',
  'elements.melody.state',
]


function taskCoversBlock(
  block: SectionAnnotationBlock,
  annotations: AnnotationRecord[],
  taskId: AnnotationTaskId,
): boolean {
  const records = annotations
    .filter(record => (
      record.task_id === taskId
      && record.annotation_status !== 'candidate'
      && record.annotation_status !== 'rejected'
      && record.end_bar_index > block.start_bar_index
      && record.start_bar_index < block.end_bar_index
    ))
    .sort((left, right) => left.start_bar_index - right.start_bar_index)
  let coveredUntil = block.start_bar_index
  for (const record of records) {
    if (record.start_bar_index > coveredUntil) return false
    coveredUntil = Math.max(coveredUntil, record.end_bar_index)
    if (coveredUntil >= block.end_bar_index) return true
  }
  return false
}


export function blockIsComplete(
  block: SectionAnnotationBlock,
  annotations: AnnotationRecord[],
): boolean {
  return ELEMENT_TASKS.every(taskId => taskCoversBlock(block, annotations, taskId))
}


export function defaultBlockIndex(
  blocks: SectionAnnotationBlock[],
  annotations: AnnotationRecord[],
): number {
  if (blocks.length === 0) return -1
  const unfinished = blocks.findIndex(block => !blockIsComplete(block, annotations))
  return unfinished >= 0 ? unfinished : 0
}


export function defaultBlockSelection(
  blocks: SectionAnnotationBlock[],
  annotations: AnnotationRecord[],
): BarRange {
  const index = defaultBlockIndex(blocks, annotations)
  if (index < 0) return { start: 0, end: 0 }
  return {
    start: blocks[index].start_bar_index,
    end: blocks[index].end_bar_index,
  }
}


export function nextBlockIndex(
  blocks: SectionAnnotationBlock[],
  currentIndex: number,
  direction = 1,
): number {
  if (blocks.length === 0) return -1
  const normalized = currentIndex >= 0 ? currentIndex : 0
  return (normalized + direction + blocks.length) % blocks.length
}


export function blockContainingRange(
  blocks: SectionAnnotationBlock[],
  range: BarRange,
): SectionAnnotationBlock | undefined {
  return blocks.find(block => (
    range.start >= block.start_bar_index
    && range.end <= block.end_bar_index
    && range.start < range.end
  ))
}
