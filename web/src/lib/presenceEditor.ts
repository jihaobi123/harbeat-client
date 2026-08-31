export interface EditableRange {
  start_bar_index: number
  end_bar_index: number
  confidence?: number | null
}


function manualRange(startBar: number, endBar: number): EditableRange {
  if (!Number.isInteger(startBar) || !Number.isInteger(endBar) || startBar < 0) {
    throw new Error('range boundaries must be non-negative Bar indexes')
  }
  if (endBar <= startBar) {
    throw new Error('range must contain at least one bar')
  }
  return { start_bar_index: startBar, end_bar_index: endBar }
}


export function normalizeRanges(ranges: EditableRange[]): EditableRange[] {
  const sorted = ranges
    .map(range => manualRange(range.start_bar_index, range.end_bar_index))
    .sort((a, b) => a.start_bar_index - b.start_bar_index)

  return sorted.reduce<EditableRange[]>((result, range) => {
    const previous = result.at(-1)
    if (previous && range.start_bar_index <= previous.end_bar_index) {
      previous.end_bar_index = Math.max(previous.end_bar_index, range.end_bar_index)
    } else {
      result.push({ ...range })
    }
    return result
  }, [])
}


export function addRange(
  ranges: EditableRange[],
  startBar: number,
  endBar: number,
): EditableRange[] {
  return normalizeRanges([...ranges, manualRange(startBar, endBar)])
}


export function deleteRange(ranges: EditableRange[], index: number): EditableRange[] {
  if (index < 0 || index >= ranges.length) {
    throw new Error('range index is out of bounds')
  }
  return ranges.filter((_, rangeIndex) => rangeIndex !== index).map(range => ({ ...range }))
}


export function resizeRange(
  ranges: EditableRange[],
  index: number,
  startBar: number,
  endBar: number,
): EditableRange[] {
  if (index < 0 || index >= ranges.length) {
    throw new Error('range index is out of bounds')
  }
  const resized = ranges.map((range, rangeIndex) => (
    rangeIndex === index
      ? manualRange(startBar, endBar)
      : { ...range }
  ))
  return normalizeRanges(resized)
}


export function splitRange(
  ranges: EditableRange[],
  index: number,
  splitBar: number,
): EditableRange[] {
  const range = ranges[index]
  if (!range) {
    throw new Error('range index is out of bounds')
  }
  if (splitBar <= range.start_bar_index || splitBar >= range.end_bar_index) {
    throw new Error('split Bar must be inside the range')
  }
  const next = ranges.filter((_, rangeIndex) => rangeIndex !== index)
  next.push(
    manualRange(range.start_bar_index, splitBar),
    manualRange(splitBar, range.end_bar_index),
  )
  return next.sort((a, b) => a.start_bar_index - b.start_bar_index)
}


export function mergeRanges(
  ranges: EditableRange[],
  indexes: number[],
): EditableRange[] {
  const selected = [...new Set(indexes)].sort((a, b) => a - b)
  if (selected.length < 2 || selected.some(index => index < 0 || index >= ranges.length)) {
    throw new Error('select at least two valid ranges to merge')
  }
  const selectedRanges = selected.map(index => ranges[index])
  const merged = manualRange(
    Math.min(...selectedRanges.map(range => range.start_bar_index)),
    Math.max(...selectedRanges.map(range => range.end_bar_index)),
  )
  const selectedSet = new Set(selected)
  const remaining = ranges
    .filter((_, index) => !selectedSet.has(index))
    .map(range => ({ ...range }))
  return normalizeRanges([...remaining, merged])
}
