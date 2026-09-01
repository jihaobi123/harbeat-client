import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from '../api/client'
import { applyRangeLabel, candidateSourceForBar, normalizeRange } from '../annotation/state'
import {
  blockContainingRange,
  defaultBlockIndex,
  nextBlockIndex,
} from '../annotation/sectionBlocks'
import { playbackAction, type PlaybackMode } from '../annotation/playback'
import { useAuthStore } from '../store/useAuthStore'
import type {
  AnnotationDraft,
  AnnotationRecord,
  AnnotationTaskId,
  AnnotationValue,
  AnnotationWorkspace,
  BarRange,
  ElementName,
  ElementState,
  EdmStructureAnalysisDocument,
  EdmStructureLabel,
  InstrumentAnalysisDocument,
  InstrumentClass,
  PilotTrackSummary,
  SectionLabel,
} from '../types/annotation'
import { BrandIllustration } from '../components/editorial/BrandIllustration'


const DATASET_VERSION = 'bar-understanding-1.0.0'
const SECTION_OPTIONS: Array<{ value: SectionLabel; label: string }> = [
  { value: 'intro', label: '开场 Intro' },
  { value: 'main', label: '主体 Main' },
  { value: 'build', label: '推进 Build' },
  { value: 'breakdown', label: '间歇 Breakdown' },
  { value: 'outro', label: '收尾 Outro' },
  { value: 'unknown', label: '不确定' },
]
const ELEMENT_OPTIONS: Array<{ value: ElementName; label: string }> = [
  { value: 'drums', label: '鼓' },
  { value: 'vocal', label: '人声' },
  { value: 'bass', label: '贝斯' },
  { value: 'melody', label: '旋律' },
]
const STATE_OPTIONS: Array<{ value: ElementState; label: string }> = [
  { value: 'absent', label: '没有' },
  { value: 'background', label: '背景' },
  { value: 'foreground', label: '前景' },
  { value: 'entering', label: '进入' },
  { value: 'ending', label: '结束' },
  { value: 'unknown', label: '不确定' },
]
const SECTION_LABELS = Object.fromEntries(SECTION_OPTIONS.map(item => [item.value, item.label]))
const STATE_LABELS = Object.fromEntries(STATE_OPTIONS.map(item => [item.value, item.label]))
const DRUM_LABELS = {
  kick: '底鼓', snare: '军鼓', hihat: '踩镲', tom: '通鼓', cymbal: '吊镲',
} as const
const INSTRUMENT_LABELS: Record<InstrumentClass, string> = {
  drums: '鼓组', percussion: '打击乐', bass: '贝斯', acoustic_guitar: '木吉他',
  electric_guitar: '电吉他', piano: '钢琴', electric_piano: '电钢琴',
  synthesizer: '合成器', strings: '弦乐', brass: '铜管', woodwind: '木管',
  organ: '风琴', sampler_fx: '采样／音效', voice: '人声',
}
const EDM_STRUCTURE_LABELS: Record<EdmStructureLabel, string> = {
  intro: 'Intro', buildup: 'Buildup', drop: 'Drop', breakdown: 'Breakdown',
  outro: 'Outro', silence: 'Silence',
}

interface Props {
  onDirtyChange: (dirty: boolean) => void
}


function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`
}


function annotationAt(
  annotations: AnnotationRecord[],
  taskId: AnnotationTaskId,
  barIndex: number,
): AnnotationRecord | undefined {
  return annotations.find(record => (
    record.task_id === taskId
    && record.start_bar_index <= barIndex
    && record.end_bar_index > barIndex
  ))
}


interface InstrumentCandidatePanelProps {
  candidates: InstrumentAnalysisDocument | null
  selectedRange: BarRange
  onSeek: (timeSec: number) => void
}


export function InstrumentCandidatePanel({
  candidates,
  selectedRange,
  onSeek,
}: InstrumentCandidatePanelProps) {
  if (!candidates || candidates.status === 'failed') {
    return (
      <section className="annotation-model-candidates street-sticker bg-surface-lighter p-3 sm:p-4">
        <div className="text-xs street-subtitle">SHADOW · MODEL EVIDENCE</div>
        <h2 className="text-xl mt-1">鼓件与乐器候选</h2>
        <p className="text-sm mt-2">这首歌还没有可用的模型候选，人工标注仍可正常进行。</p>
      </section>
    )
  }
  const bars = candidates.bars.filter(bar => (
    bar.bar_index >= selectedRange.start && bar.bar_index < selectedRange.end
  ))
  const counts = { kick: 0, snare: 0, hihat: 0, tom: 0, cymbal: 0 }
  const events = bars.flatMap(bar => bar.drum_events)
  bars.forEach(bar => {
    Object.entries(bar.drum_summary.event_counts).forEach(([name, count]) => {
      counts[name as keyof typeof counts] += count
    })
  })
  const instrumentValues = new Map<InstrumentClass, { total: number; maximum: number; samples: number }>()
  bars.forEach(bar => bar.instrument_probabilities.forEach(item => {
    const current = instrumentValues.get(item.instrument_class) ?? { total: 0, maximum: 0, samples: 0 }
    current.total += item.mean_probability
    current.maximum = Math.max(current.maximum, item.max_probability)
    current.samples += 1
    instrumentValues.set(item.instrument_class, current)
  }))
  const instruments = [...instrumentValues.entries()]
    .map(([instrumentClass, value]) => ({
      instrumentClass,
      mean: value.total / value.samples,
      maximum: value.maximum,
    }))
    .sort((left, right) => right.mean - left.mean)

  return (
    <section className="annotation-model-candidates street-sticker bg-surface-lighter p-3 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs street-subtitle">SHADOW · MODEL EVIDENCE</div>
          <h2 className="text-xl mt-1">五类鼓事件与乐器候选</h2>
        </div>
        <strong className="bg-primary border-2 border-black px-3 py-1 text-xs">
          模型候选，不是人工真值
        </strong>
      </div>
      <div className="grid lg:grid-cols-2 gap-4 mt-4">
        <div>
          <h3 className="font-bold">五类鼓事件</h3>
          <div className="grid grid-cols-5 gap-1 mt-2 text-center text-xs">
            {Object.entries(counts).map(([name, count]) => (
              <div key={name} className="border-2 border-black bg-white p-2">
                <div className="font-bold text-lg">{count}</div>
                <div>{DRUM_LABELS[name as keyof typeof DRUM_LABELS]}</div>
              </div>
            ))}
          </div>
          {events.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2" aria-label="鼓事件时间">
              {events.slice(0, 40).map((event, index) => (
                <button
                  key={`${event.time_sec}-${event.drum_class}-${index}`}
                  className="px-2 py-1 bg-white text-xs"
                  onClick={() => onSeek(event.time_sec)}
                >
                  {DRUM_LABELS[event.drum_class]} · {event.time_sec.toFixed(2)} 秒
                </button>
              ))}
            </div>
          )}
        </div>
        <div>
          <h3 className="font-bold">乐器候选</h3>
          <div className="grid sm:grid-cols-2 gap-1 mt-2 text-xs">
            {instruments.map(item => (
              <div key={item.instrumentClass} className="border-2 border-black bg-white p-2 flex justify-between gap-2">
                <span className="font-bold">{INSTRUMENT_LABELS[item.instrumentClass]}</span>
                <span>平均 {(item.mean * 100).toFixed(0)}% · 峰值 {(item.maximum * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      {candidates.warnings.length > 0 && (
        <p className="text-xs mt-3">模型提示：{candidates.warnings.join('、')}</p>
      )}
    </section>
  )
}


interface EdmStructureCandidatePanelProps {
  candidates: EdmStructureAnalysisDocument | null
  selectedRange: BarRange
  onSeek: (timeSec: number) => void
}


export function EdmStructureCandidatePanel({
  candidates,
  selectedRange,
  onSeek,
}: EdmStructureCandidatePanelProps) {
  if (!candidates || candidates.status === 'failed') {
    return (
      <section className="annotation-edm-candidates street-sticker bg-surface-lighter p-3 sm:p-4">
        <div className="text-xs street-subtitle">EDMFORMER · SHADOW</div>
        <h2 className="text-xl mt-1">EDM 功能结构候选</h2>
        <p className="text-sm mt-2">这首歌还没有 EDMFormer 候选，不影响 SongFormer 分段和人工标注。</p>
      </section>
    )
  }
  const segments = candidates.segments.filter(segment => (
    segment.end_bar_index > selectedRange.start
    && segment.start_bar_index < selectedRange.end
  ))
  return (
    <section className="annotation-edm-candidates street-sticker bg-surface-lighter p-3 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs street-subtitle">EDMFORMER · SHADOW</div>
          <h2 className="text-xl mt-1">EDMFormer Shadow 候选</h2>
        </div>
        <strong className="bg-primary border-2 border-black px-3 py-1 text-xs">
          SongFormer 边界仍是主时间轴
        </strong>
      </div>
      <div className="grid gap-3 mt-4">
        {segments.map(segment => (
          <article key={segment.canonical_section_id} className="border-2 border-black bg-white p-3">
            <div className="flex flex-wrap justify-between gap-2">
              <strong>
                第 {segment.start_bar_index + 1}–{segment.end_bar_index} 小节 ·
                {' '}{EDM_STRUCTURE_LABELS[segment.edmformer_label_candidate]}
              </strong>
              <span className="text-xs">模型候选，不是人工真值</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-1 mt-3 text-xs">
              {(Object.keys(EDM_STRUCTURE_LABELS) as EdmStructureLabel[]).map(label => (
                <div key={label} className="border-2 border-black p-2 flex justify-between gap-2">
                  <span className="font-bold">{EDM_STRUCTURE_LABELS[label]}</span>
                  <span>{(segment.edmformer_label_probabilities[label] * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
            {segment.edmformer_boundary_candidates.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-3" aria-label="EDMFormer 对比边界">
                <span className="text-xs py-1">模型自有边界，仅供比较：</span>
                {segment.edmformer_boundary_candidates.map(boundary => (
                  <button
                    key={boundary}
                    className="px-2 py-1 bg-white text-xs"
                    onClick={() => onSeek(boundary)}
                  >
                    {boundary.toFixed(2)} 秒
                  </button>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
      <p className="text-xs mt-3">ExpandedStructureHead：未安装。</p>
    </section>
  )
}


export default function AnnotationWorkbench({ onDirtyChange }: Props) {
  const { user } = useAuthStore()
  const audioRef = useRef<HTMLAudioElement>(null)
  const playbackModeRef = useRef<PlaybackMode>('full')
  const [tracks, setTracks] = useState<PilotTrackSummary[]>([])
  const [tracksLoading, setTracksLoading] = useState(true)
  const [trackId, setTrackId] = useState('')
  const [workspace, setWorkspace] = useState<AnnotationWorkspace | null>(null)
  const [instrumentCandidates, setInstrumentCandidates] = useState<InstrumentAnalysisDocument | null>(null)
  const [edmStructureCandidates, setEdmStructureCandidates] = useState<EdmStructureAnalysisDocument | null>(null)
  const [draft, setDraft] = useState<AnnotationDraft | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [selectionStart, setSelectionStart] = useState(0)
  const [selectionEnd, setSelectionEnd] = useState(0)
  const [waitingForEnd, setWaitingForEnd] = useState(false)
  const [activeElement, setActiveElement] = useState<ElementName>('drums')
  const [loopSelection, setLoopSelection] = useState(false)
  const [audioSource, setAudioSource] = useState('original')
  const [currentBlockIndex, setCurrentBlockIndex] = useState(-1)

  const resetPlaybackMode = () => {
    playbackModeRef.current = 'full'
  }

  useEffect(() => {
    let active = true
    api.getPilotAnnotationTracks()
      .then(next => {
        if (active) setTracks(next)
      })
      .catch(caught => {
        if (active) setError(caught instanceof Error ? caught.message : 'Pilot 歌曲加载失败')
      })
      .finally(() => {
        if (active) setTracksLoading(false)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    onDirtyChange(dirty)
  }, [dirty, onDirtyChange])

  useEffect(() => {
    if (!dirty) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [dirty])

  const selectedRange = useMemo<BarRange>(() => {
    const count = workspace?.bars.length ?? 0
    return normalizeRange(selectionStart, selectionEnd, count)
  }, [selectionEnd, selectionStart, workspace?.bars.length])

  const loadWorkspace = async (nextTrackId: string) => {
    setTrackId(nextTrackId)
    setWorkspace(null)
    setInstrumentCandidates(null)
    setEdmStructureCandidates(null)
    setDraft(null)
    setDirty(false)
    setMessage('')
    setError('')
    setConflict(false)
    setWaitingForEnd(false)
    setSelectionStart(0)
    setSelectionEnd(0)
    setLoopSelection(false)
    setAudioSource('original')
    setCurrentBlockIndex(-1)
    resetPlaybackMode()
    if (!nextTrackId) return
    setLoading(true)
    try {
      const [next, nextInstrumentCandidates, nextEdmStructureCandidates] = await Promise.all([
        api.getBarAnnotationWorkspace(nextTrackId, DATASET_VERSION),
        api.getInstrumentCandidates(nextTrackId).catch(() => null),
        api.getEdmStructureCandidates(nextTrackId).catch(() => null),
      ])
      const blockIndex = defaultBlockIndex(next.section_blocks, next.annotations)
      setWorkspace(next)
      setInstrumentCandidates(nextInstrumentCandidates)
      setEdmStructureCandidates(nextEdmStructureCandidates)
      setDraft({
        datasetVersion: next.dataset_version,
        trackId: next.track_id,
        annotatorId: `producer-${user?.id ?? 'unknown'}`,
        bars: next.bars,
        annotations: next.annotations,
      })
      setCurrentBlockIndex(blockIndex)
      if (blockIndex >= 0) {
        const block = next.section_blocks[blockIndex]
        setSelectionStart(block.start_bar_index)
        setSelectionEnd(block.end_bar_index - 1)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '工作区加载失败')
    } finally {
      setLoading(false)
    }
  }

  const selectBar = (barIndex: number) => {
    resetPlaybackMode()
    if (!waitingForEnd) {
      setSelectionStart(barIndex)
      setSelectionEnd(barIndex)
      setWaitingForEnd(true)
    } else {
      setSelectionEnd(barIndex)
      setWaitingForEnd(false)
    }
  }

  const selectBlock = (blockIndex: number) => {
    if (!workspace || blockIndex < 0 || blockIndex >= workspace.section_blocks.length) return
    const block = workspace.section_blocks[blockIndex]
    resetPlaybackMode()
    setCurrentBlockIndex(blockIndex)
    setSelectionStart(block.start_bar_index)
    setSelectionEnd(block.end_bar_index - 1)
    setWaitingForEnd(false)
  }

  const applyLabel = (
    taskId: AnnotationTaskId,
    value: AnnotationValue,
    candidateSource: string | null = null,
  ) => {
    if (!draft || selectedRange.start >= selectedRange.end) return
    try {
      setDraft(applyRangeLabel(
        draft,
        selectedRange,
        taskId,
        value,
        new Date().toISOString(),
        candidateSource,
      ))
      setDirty(true)
      setMessage('已修改，记得保存')
      setError('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '标签设置失败')
    }
  }

  const acceptCandidates = (taskId: AnnotationTaskId) => {
    if (!workspace || !draft || selectedRange.start >= selectedRange.end) return
    let nextDraft = draft
    let runStart = selectedRange.start
    let current = candidateSourceForBar(workspace.bars[runStart], taskId)
    const timestamp = new Date().toISOString()
    for (let index = runStart + 1; index <= selectedRange.end; index += 1) {
      const next = index < selectedRange.end
        ? candidateSourceForBar(workspace.bars[index], taskId)
        : null
      if (next && next.value === current.value && next.source === current.source) continue
      nextDraft = applyRangeLabel(
        nextDraft,
        { start: runStart, end: index },
        taskId,
        current.value,
        timestamp,
        current.source,
      )
      if (next) {
        runStart = index
        current = next
      }
    }
    setDraft(nextDraft)
    setDirty(true)
    setMessage('已采用所选范围的系统建议，保存后才会生效')
    setError('')
  }

  const save = async () => {
    if (!workspace || !draft) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const next = await api.saveBarAnnotationWorkspace(workspace.track_id, {
        dataset_version: workspace.dataset_version,
        revision: workspace.revision,
        annotations: draft.annotations,
      })
      setWorkspace(next)
      setDraft(previous => previous ? { ...previous, annotations: next.annotations } : previous)
      setDirty(false)
      setConflict(false)
      setMessage(`已保存 · 修订 ${next.revision}`)
    } catch (caught) {
      if (caught instanceof api.ApiError && caught.status === 409) {
        setConflict(true)
      }
      setError(caught instanceof Error ? caught.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const playSelection = async () => {
    if (!audioRef.current || !workspace || selectedRange.start >= selectedRange.end) return
    audioRef.current.currentTime = workspace.bars[selectedRange.start].start_sec
    playbackModeRef.current = loopSelection ? 'range_loop' : 'range_preview'
    try {
      await audioRef.current.play()
    } catch {
      setError('浏览器没有允许播放，请先点一下播放器的播放按钮')
    }
  }

  const handleAudioTime = () => {
    if (!audioRef.current || !workspace || selectedRange.start >= selectedRange.end) return
    const start = workspace.bars[selectedRange.start].start_sec
    const end = workspace.bars[selectedRange.end - 1].end_sec
    const action = playbackAction({
      mode: playbackModeRef.current,
      currentTime: audioRef.current.currentTime,
      rangeStart: start,
      rangeEnd: end,
    })
    if (action === 'loop') {
      audioRef.current.currentTime = start
      void audioRef.current.play()
    } else if (action === 'pause') {
      resetPlaybackMode()
      audioRef.current.pause()
    }
  }

  const handleNativePlay = () => {
    if (!audioRef.current || !workspace || selectedRange.start >= selectedRange.end) {
      resetPlaybackMode()
      return
    }
    const rangeStart = workspace.bars[selectedRange.start].start_sec
    if (Math.abs(audioRef.current.currentTime - rangeStart) > 0.08) {
      resetPlaybackMode()
    }
  }

  const seekToCandidate = (timeSec: number) => {
    if (!audioRef.current) return
    resetPlaybackMode()
    audioRef.current.currentTime = timeSec
    void audioRef.current.play().catch(() => {
      setError('浏览器没有允许播放，请先点一下播放器的播放按钮')
    })
  }

  const confirmedCount = draft?.annotations.filter(record => (
    record.annotation_status !== 'candidate' && record.annotation_status !== 'rejected'
  )).length ?? 0
  const selectedLabel = selectedRange.start < selectedRange.end
    ? `第 ${selectedRange.start + 1}–${selectedRange.end} 小节`
    : '尚未选择'
  const selectedModelBlock = workspace
    ? blockContainingRange(workspace.section_blocks, selectedRange)
    : undefined
  const currentBlock = workspace && currentBlockIndex >= 0
    ? workspace.section_blocks[currentBlockIndex]
    : undefined

  return (
    <main className="annotation-workbench">
      <div className="max-w-[1500px] mx-auto space-y-4">
        <section className="annotation-track-picker flex flex-col xl:flex-row xl:items-end gap-3">
          <div className="flex-1">
            <div className="text-xs street-subtitle mb-1">WORKFLOW B · PILOT</div>
            <h1 className="text-3xl leading-none">音乐段落标注工作台</h1>
            <p className="text-sm mt-2 max-w-3xl">
              先听歌，再选择连续小节，最后确认或修改系统建议。这里只做段落、鼓、人声、贝斯和旋律状态。
            </p>
          </div>
          <label className="min-w-[280px] text-sm font-semibold">
            选择要标注的歌曲
            <select
              className="w-full mt-1 px-3 py-2"
              value={trackId}
              onChange={event => void loadWorkspace(event.target.value)}
              disabled={tracksLoading || dirty}
              title={dirty ? '请先保存当前修改，再切换歌曲' : undefined}
            >
              <option value="">{tracksLoading ? '正在读取歌曲…' : '请选择歌曲'}</option>
              {tracks.map(song => (
                <option key={song.id} value={song.id}>
                  {song.title} — {song.artist}
                </option>
              ))}
            </select>
          </label>
        </section>

        {loading && <div className="street-sticker bg-surface-lighter p-4">正在建立统一小节时间轴…</div>}
        {error && (
          <div className="street-sticker bg-red-500/20 p-3 text-sm" role="alert">
            <strong>没有完成：</strong> {error}
            {conflict && trackId && (
              <button
                className="ml-3 px-3 py-1 bg-white"
                onClick={() => void loadWorkspace(trackId)}
              >
                放弃本地草稿并重新加载
              </button>
            )}
          </div>
        )}
        {message && !error && (
          <div className="street-sticker bg-green-500/10 p-3 text-sm" role="status">{message}</div>
        )}

        {workspace && draft && (
          <>
            <section className="annotation-transport street-sticker bg-surface-lighter p-3 sm:p-4 grid lg:grid-cols-[minmax(0,1fr)_auto] gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <h2 className="text-2xl truncate">{workspace.title}</h2>
                  <span className="text-sm">{workspace.artist}</span>
                  <span className="text-xs">{formatTime(workspace.duration_sec)} · {workspace.bars.length} 小节</span>
                </div>
                <audio
                  ref={audioRef}
                  className="w-full mt-3 h-10"
                  controls
                  preload="metadata"
                  src={audioSource === 'original'
                    ? api.getBarAnnotationAudioUrl(workspace.track_id)
                    : api.getBarAnnotationStemUrl(workspace.track_id, audioSource)}
                  onTimeUpdate={handleAudioTime}
                  onPlay={handleNativePlay}
                />
                <div className="flex flex-wrap gap-2 mt-2" aria-label="试听音源">
                  <button
                    className={audioSource === 'original' ? 'px-3 py-1 bg-primary' : 'px-3 py-1 bg-white'}
                    onClick={() => {
                      resetPlaybackMode()
                      setAudioSource('original')
                    }}
                  >
                    原曲
                  </button>
                  {(tracks.find(track => track.id === workspace.track_id)?.stems_available ?? []).map(stem => (
                    <button
                      key={stem}
                      className={audioSource === stem ? 'px-3 py-1 bg-primary' : 'px-3 py-1 bg-white'}
                      onClick={() => {
                        resetPlaybackMode()
                        setAudioSource(stem)
                      }}
                    >
                      {stem === 'vocals' ? '人声' : stem === 'drums' ? '鼓' : stem === 'bass' ? '贝斯' : '其他/旋律'}
                    </button>
                  ))}
                </div>
                {workspace.timeline_warnings.length > 0 && (
                  <div className="text-xs mt-2">
                    时间轴提示：{workspace.timeline_warnings.join('、')}
                  </div>
                )}
              </div>
              <div className="flex flex-wrap lg:flex-col gap-2 lg:min-w-44">
                <button className="px-3 py-2 bg-primary" onClick={() => void playSelection()}>
                  ▶ 试听所选范围
                </button>
                <button
                  className={loopSelection ? 'px-3 py-2 bg-primary' : 'px-3 py-2 bg-white'}
                  onClick={() => setLoopSelection(value => {
                    const next = !value
                    if (playbackModeRef.current !== 'full') {
                      playbackModeRef.current = next ? 'range_loop' : 'range_preview'
                    }
                    return next
                  })}
                >
                  {loopSelection ? '↻ 正在循环' : '↻ 循环所选'}
                </button>
              </div>
            </section>

            <section className="annotation-block-nav street-sticker bg-surface-lighter p-3 sm:p-4">
              <div>
                <div className="text-xs street-subtitle">SONGFORMER · SECTION BLOCKS</div>
                <h2 className="text-xl mt-1">按段落块标注，小节级纠错</h2>
                {workspace.section_block_status === 'not_analyzed' && (
                  <p className="text-sm mt-2">这首歌还没有 SongFormer 结果，可以继续手动选择小节。</p>
                )}
                {workspace.section_block_status === 'failed' && (
                  <p className="text-sm mt-2 text-red-800">SongFormer 分段失败，当前保留手动小节选择。</p>
                )}
                {currentBlock && (
                  <p className="text-sm mt-2">
                    段落块 {currentBlockIndex + 1}/{workspace.section_blocks.length} ·
                    第 {currentBlock.start_bar_index + 1}–{currentBlock.end_bar_index} 小节
                    {currentBlock.needs_review ? ' · 边界需要复核' : ' · 边界已对齐'}
                  </p>
                )}
                {currentBlock?.needs_review && (
                  <p className="text-xs mt-1">
                    吸附误差：起点 {currentBlock.start_snap_error_sec.toFixed(2)} 秒，
                    终点 {currentBlock.end_snap_error_sec.toFixed(2)} 秒
                  </p>
                )}
                <p className="text-xs mt-1">
                  残差分类器：未安装，本次只使用 SongFormer 时间边界。
                </p>
              </div>
              {workspace.section_blocks.length > 0 && (
                <div className="annotation-block-nav__actions">
                  <button
                    className="px-3 py-2 bg-white"
                    onClick={() => selectBlock(nextBlockIndex(workspace.section_blocks, currentBlockIndex, -1))}
                  >
                    ← 上一段
                  </button>
                  <button
                    className="px-3 py-2 bg-primary"
                    onClick={() => selectBlock(nextBlockIndex(workspace.section_blocks, currentBlockIndex))}
                  >
                    下一段 →
                  </button>
                  {currentBlock && selectedModelBlock?.block_id !== currentBlock.block_id && (
                    <button className="px-3 py-2 bg-white" onClick={() => selectBlock(currentBlockIndex)}>
                      选中整个段落块
                    </button>
                  )}
                </div>
              )}
            </section>

            <section className="annotation-bars street-sticker bg-surface-lighter p-3 sm:p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
                <div>
                  <h2 className="text-xl">1. 选择连续小节</h2>
                  <p className="text-xs mt-1">
                    {waitingForEnd ? '已定起点，再点一个小节作为终点。' : '点一次定起点，再点一次定终点。'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold bg-white border-2 border-black rounded-md px-3 py-1">
                    {selectedLabel}
                  </span>
                  <button
                    className="px-3 py-1 bg-white text-sm"
                    onClick={() => {
                      resetPlaybackMode()
                      setSelectionStart(0)
                      setSelectionEnd(0)
                      setWaitingForEnd(false)
                    }}
                  >
                    重选
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto pb-3">
                <div className="flex gap-2 min-w-max">
                  {workspace.bars.map(bar => {
                    const selected = bar.bar_index >= selectedRange.start && bar.bar_index < selectedRange.end
                    const sectionRecord = annotationAt(draft.annotations, 'structure.section_label', bar.bar_index)
                    return (
                      <button
                        key={bar.bar_index}
                        className={`w-40 shrink-0 text-left p-2 align-top ${selected ? 'bg-primary' : 'bg-white'}`}
                        onClick={() => selectBar(bar.bar_index)}
                      >
                        <div className="flex justify-between items-baseline">
                          <strong>小节 {bar.bar_index + 1}</strong>
                          <span className="text-[10px]">{formatTime(bar.start_sec)}</span>
                        </div>
                        <div className="mt-2 text-xs border-t-2 border-black pt-1">
                          <div>建议段落：{SECTION_LABELS[bar.section.value]}</div>
                          <div className="font-bold mt-1">
                            {sectionRecord ? `已标：${SECTION_LABELS[sectionRecord.value as SectionLabel]}` : '尚未人工确认'}
                          </div>
                        </div>
                        <div className="mt-2 grid grid-cols-2 gap-1 text-[10px]">
                          {ELEMENT_OPTIONS.map(element => {
                            const taskId = `elements.${element.value}.state` as AnnotationTaskId
                            const confirmed = annotationAt(draft.annotations, taskId, bar.bar_index)
                            const display = confirmed?.value ?? bar.elements[element.value].value
                            return (
                              <span key={element.value} className={confirmed ? 'font-bold underline' : ''}>
                                {element.label} {STATE_LABELS[display as ElementState]}
                              </span>
                            )
                          })}
                        </div>
                      </button>
                    )
                  })}
                </div>
              </div>
            </section>

            <InstrumentCandidatePanel
              candidates={instrumentCandidates}
              selectedRange={selectedRange}
              onSeek={seekToCandidate}
            />

            <EdmStructureCandidatePanel
              candidates={edmStructureCandidates}
              selectedRange={selectedRange}
              onSeek={seekToCandidate}
            />

            <section className="grid xl:grid-cols-2 gap-4">
              <div className="annotation-sections street-sticker bg-surface-lighter p-3 sm:p-4">
                <div className="flex flex-wrap justify-between gap-2 mb-3">
                  <div>
                    <h2 className="text-xl">2. 标记段落</h2>
                    <p className="text-xs mt-1">标签会应用到 {selectedLabel}</p>
                  </div>
                  <button
                    className="px-3 py-1 bg-white text-sm"
                    onClick={() => acceptCandidates('structure.section_label')}
                  >
                    采用系统段落建议
                  </button>
                </div>
                <div className="grid sm:grid-cols-3 gap-2">
                  {SECTION_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      className="px-3 py-2 bg-white text-sm"
                      onClick={() => applyLabel('structure.section_label', option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="annotation-elements street-sticker bg-surface-lighter p-3 sm:p-4">
                <div className="flex flex-wrap justify-between gap-2 mb-3">
                  <div>
                    <h2 className="text-xl">3. 标记元素状态</h2>
                    <p className="text-xs mt-1">先选元素，再选它在这段里的状态</p>
                  </div>
                  <button
                    className="px-3 py-1 bg-white text-sm"
                    onClick={() => acceptCandidates(`elements.${activeElement}.state`)}
                  >
                    采用该元素建议
                  </button>
                </div>
                <div className="flex flex-wrap gap-2 mb-3">
                  {ELEMENT_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      className={activeElement === option.value ? 'px-3 py-2 bg-primary' : 'px-3 py-2 bg-white'}
                      onClick={() => setActiveElement(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <div className="grid sm:grid-cols-3 gap-2">
                  {STATE_OPTIONS.map(option => (
                    <button
                      key={option.value}
                      className="px-3 py-2 bg-white text-sm"
                      onClick={() => applyLabel(`elements.${activeElement}.state`, option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <section className="annotation-savebar street-sticker bg-surface-lighter p-3 flex flex-wrap items-center justify-between gap-3">
              <div className="text-sm">
                <strong>{confirmedCount}</strong> 条人工记录 · 修订 {workspace.revision}
                {dirty ? ' · 有尚未保存的修改' : ' · 已与服务器同步'}
              </div>
              <button
                className="px-6 py-2 bg-primary disabled:opacity-50"
                disabled={!dirty || saving}
                onClick={() => void save()}
              >
                {saving ? '正在保存…' : '保存本首歌曲'}
              </button>
            </section>
          </>
        )}

        {!workspace && !loading && !error && (
          <section className="editorial-state editorial-state--empty street-sticker bg-surface-lighter p-8 text-center">
            <BrandIllustration variant="headphones" />
            <h2 className="text-2xl">从上方选择一首已经分析过的歌曲</h2>
            <p className="text-sm mt-2">歌曲需要先有可用的 Beat Grid，工作台才会生成统一的小节边界。</p>
          </section>
        )}
      </div>
    </main>
  )
}
