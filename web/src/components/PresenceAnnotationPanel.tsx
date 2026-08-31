import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import * as api from '../api/client'
import {
  addRange,
  deleteRange,
  mergeRanges,
  resizeRange,
  splitRange,
} from '../lib/presenceEditor'
import type {
  LibrarySong,
  PresenceAnnotationBundle,
  PresenceElement,
  PresenceElementReview,
  PresenceReviewState,
} from '../types'
import PresenceTimeline from './PresenceTimeline'


const ELEMENTS: PresenceElement[] = ['vocal', 'drums', 'bass', 'melody']
const SOURCE_LABELS = {
  original: '原曲',
  vocals: '人声',
  drums: '鼓点',
  bass: '贝斯',
  other: '其他 / Melody',
} as const

type AudioSource = keyof typeof SOURCE_LABELS
type DraftElements = Record<PresenceElement, PresenceElementReview>
type ActiveRange = { element: PresenceElement; index: number } | null


function cloneDraft(draft: DraftElements): DraftElements {
  return Object.fromEntries(ELEMENTS.map(element => [
    element,
    {
      review_state: draft[element].review_state,
      ranges: draft[element].ranges.map(range => ({
        start_bar_index: range.start_bar_index,
        end_bar_index: range.end_bar_index,
      })),
    },
  ])) as DraftElements
}


function draftFromBundle(bundle: PresenceAnnotationBundle): DraftElements {
  const latest = bundle.revisions.at(-1)
  if (latest) return cloneDraft(latest.elements)

  return Object.fromEntries(ELEMENTS.map(element => {
    const candidate = bundle.candidates.elements[element]
    const available = candidate.availability === 'available'
    return [element, {
      review_state: available ? 'reviewed' : 'unknown',
      ranges: available
        ? candidate.candidate_ranges.map(range => ({
            start_bar_index: range.start_bar_index,
            end_bar_index: range.end_bar_index,
          }))
        : [],
    }]
  })) as DraftElements
}


function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return '操作失败，请稍后重试'
}


export default function PresenceAnnotationPanel({ song }: { song: LibrarySong }) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const loopRef = useRef<{ start: number; end: number } | null>(null)
  const [bundle, setBundle] = useState<PresenceAnnotationBundle | null>(null)
  const [draft, setDraft] = useState<DraftElements | null>(null)
  const [undoStack, setUndoStack] = useState<DraftElements[]>([])
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [source, setSource] = useState<AudioSource>('original')
  const [currentTime, setCurrentTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [selectedElement, setSelectedElement] = useState<PresenceElement>('vocal')
  const [activeRange, setActiveRange] = useState<ActiveRange>(null)

  const installBundle = useCallback((next: PresenceAnnotationBundle) => {
    setBundle(next)
    setDraft(draftFromBundle(next))
    setUndoStack([])
    setDirty(false)
    setError('')
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      installBundle(await api.getPresenceAnnotations(song.id))
    } catch (loadError) {
      setBundle(null)
      setDraft(null)
      setError(errorMessage(loadError))
    } finally {
      setLoading(false)
    }
  }, [installBundle, song.id])

  useEffect(() => { void load() }, [load])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const position = audio.currentTime || currentTime
    const shouldResume = !audio.paused
    const url = source === 'original'
      ? api.getStreamUrl(song.id)
      : api.getStemStreamUrl(song.id, source)
    const restore = () => {
      audio.currentTime = Math.min(position, Number.isFinite(audio.duration) ? audio.duration : position)
      if (shouldResume) void audio.play()
    }
    audio.addEventListener('loadedmetadata', restore, { once: true })
    audio.src = url
    audio.load()
    return () => audio.removeEventListener('loadedmetadata', restore)
  // currentTime is deliberately read only when the source or song changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [song.id, source])

  const changeDraft = useCallback((change: (current: DraftElements) => DraftElements) => {
    setDraft(current => {
      if (!current) return current
      setUndoStack(stack => [...stack, cloneDraft(current)])
      setDirty(true)
      return change(cloneDraft(current))
    })
  }, [])

  const changeRanges = useCallback((
    element: PresenceElement,
    change: (ranges: PresenceElementReview['ranges']) => PresenceElementReview['ranges'],
  ) => {
    changeDraft(current => ({
      ...current,
      [element]: {
        review_state: 'reviewed',
        ranges: change(current[element].ranges),
      },
    }))
  }, [changeDraft])

  const undo = useCallback(() => {
    setUndoStack(stack => {
      const previous = stack.at(-1)
      if (!previous) return stack
      setDraft(cloneDraft(previous))
      setDirty(stack.length > 1)
      setActiveRange(null)
      return stack.slice(0, -1)
    })
  }, [])

  const save = useCallback(async () => {
    if (!bundle || !draft || saving) return
    setSaving(true)
    setError('')
    try {
      installBundle(await api.savePresenceReview(song.id, {
        expected_revision: bundle.revision,
        elements: draft,
      }))
    } catch (saveError) {
      const message = errorMessage(saveError)
      setError(message.includes('409') || message.toLowerCase().includes('revision')
        ? '标注版本已变化，请刷新后重新检查；当前修改没有覆盖服务器数据。'
        : message)
    } finally {
      setSaving(false)
    }
  }, [bundle, draft, installBundle, saving, song.id])

  const seek = useCallback((seconds: number) => {
    const audio = audioRef.current
    if (audio) audio.currentTime = seconds
    setCurrentTime(seconds)
  }, [])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) void audio.play()
    else audio.pause()
  }, [])

  const seekBar = useCallback((offset: -1 | 1) => {
    const bars = bundle?.timeline.bars ?? []
    if (!bars.length) return
    const currentIndex = Math.max(0, bars.findIndex(bar => currentTime >= bar.start_sec && currentTime < bar.end_sec))
    const nextIndex = Math.max(0, Math.min(bars.length - 1, currentIndex + offset))
    loopRef.current = null
    seek(bars[nextIndex].start_sec)
  }, [bundle, currentTime, seek])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (target?.matches('input, textarea, select')) return
      if (event.key === ' ') {
        event.preventDefault()
        togglePlay()
      } else if (event.key === '[') {
        event.preventDefault()
        seekBar(-1)
      } else if (event.key === ']') {
        event.preventDefault()
        seekBar(1)
      } else if ((event.key === 'Delete' || event.key === 'Backspace') && activeRange) {
        event.preventDefault()
        changeRanges(activeRange.element, ranges => deleteRange(ranges, activeRange.index))
        setActiveRange(null)
      } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        undo()
      } else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        void save()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeRange, changeRanges, save, seekBar, togglePlay, undo])

  const timelineElements = useMemo(() => {
    if (!bundle || !draft) return null
    return Object.fromEntries(ELEMENTS.map(element => [element, {
      candidate: bundle.candidates.elements[element],
      review: draft[element],
    }])) as Record<PresenceElement, {
      candidate: PresenceAnnotationBundle['candidates']['elements'][PresenceElement]
      review: PresenceElementReview
    }>
  }, [bundle, draft])

  const generate = async () => {
    setGenerating(true)
    setError('')
    try {
      installBundle(await api.generatePresenceAnnotations(song.id))
    } catch (generateError) {
      setError(errorMessage(generateError))
    } finally {
      setGenerating(false)
    }
  }

  const exportReviewed = async () => {
    setError('')
    try {
      const blob = await api.downloadPresenceExport(song.id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${song.id}-presence.jsonl`
      link.click()
      URL.revokeObjectURL(url)
    } catch (exportError) {
      setError(errorMessage(exportError))
    }
  }

  const loopRange = (startBar: number, endBar: number) => {
    if (!bundle) return
    const start = bundle.timeline.bars[startBar]?.start_sec
    const end = bundle.timeline.bars[endBar - 1]?.end_sec
    if (start === undefined || end === undefined) return
    const previous = loopRef.current
    if (previous?.start === start && previous.end === end) {
      loopRef.current = null
      return
    }
    loopRef.current = { start, end }
    seek(start)
    if (audioRef.current?.paused) void audioRef.current.play()
  }

  const setReviewState = (element: PresenceElement, state: PresenceReviewState) => {
    changeDraft(current => ({
      ...current,
      [element]: {
        review_state: state,
        ranges: state === 'reviewed' ? current[element].ranges : [],
      },
    }))
  }

  return (
    <section className="presence-panel" aria-label="元素出现区间审核">
      <div className="presence-panel-titlebar">
        <div>
          <h4>元素出现区间审核</h4>
          <p>机器先标，小节级人工纠错 · 左闭右开区间</p>
        </div>
        {bundle && <span className="presence-revision">Revision {bundle.revision}</span>}
      </div>

      <audio
        ref={audioRef}
        aria-label="标注试听播放器"
        onTimeUpdate={event => {
          const audio = event.currentTarget
          const loop = loopRef.current
          if (loop && audio.currentTime >= loop.end) audio.currentTime = loop.start
          setCurrentTime(audio.currentTime)
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />

      <div className="presence-transport">
        <button type="button" onClick={togglePlay}>{playing ? '暂停' : '播放'}</button>
        <button type="button" onClick={() => seekBar(-1)} title="快捷键 [">上一 Bar</button>
        <button type="button" onClick={() => seekBar(1)} title="快捷键 ]">下一 Bar</button>
        <span>{currentTime.toFixed(2)}s</span>
      </div>

      <div className="presence-sources" aria-label="试听音源">
        {(Object.keys(SOURCE_LABELS) as AudioSource[]).map(value => (
          <button
            key={value}
            type="button"
            className={source === value ? 'is-active' : ''}
            onClick={() => setSource(value)}
          >
            {SOURCE_LABELS[value]}
          </button>
        ))}
      </div>

      {loading && <p className="presence-status">正在读取标注…</p>}
      {!loading && !bundle && (
        <div className="presence-empty">
          <p>这首歌还没有机器候选。Stems 和节拍时间轴准备好后即可生成。</p>
          <button type="button" onClick={() => void generate()} disabled={generating}>
            {generating ? '正在生成…' : '生成机器候选'}
          </button>
        </div>
      )}

      {bundle && draft && timelineElements && (
        <>
          <PresenceTimeline
            bars={bundle.timeline.bars}
            elements={timelineElements}
            currentTime={currentTime}
            selectedElement={selectedElement}
            onSelectElement={setSelectedElement}
            onSeek={seconds => { loopRef.current = null; seek(seconds) }}
            onAddRange={(element, start, end) => changeRanges(element, ranges => addRange(ranges, start, end))}
            onResizeRange={(element, index, start, end) => changeRanges(element, ranges => resizeRange(ranges, index, start, end))}
            onDeleteRange={(element, index) => changeRanges(element, ranges => deleteRange(ranges, index))}
            onSplitRange={(element, index, split) => changeRanges(element, ranges => splitRange(ranges, index, split))}
            onMergeRanges={(element, indexes) => changeRanges(element, ranges => mergeRanges(ranges, indexes))}
            onLoopRange={loopRange}
            onReviewStateChange={setReviewState}
            onActiveRangeChange={(element, index) => setActiveRange({ element, index })}
          />

          <div className="presence-actions">
            <button type="button" onClick={undo} disabled={!undoStack.length}>撤销</button>
            <button type="button" onClick={() => void exportReviewed()} disabled={!bundle.revisions.length}>导出 JSONL</button>
            <button type="button" className="is-primary" onClick={() => void save()} disabled={!dirty || saving}>
              {saving ? '保存中…' : dirty ? '保存人工修订' : '已保存'}
            </button>
          </div>
          <p className="presence-shortcuts">Space 播放 · [ ] 切 Bar · Delete 删除 · Cmd/Ctrl+Z 撤销 · Cmd/Ctrl+S 保存</p>
        </>
      )}

      {error && <p className="presence-error" role="alert">{error}</p>}
    </section>
  )
}
