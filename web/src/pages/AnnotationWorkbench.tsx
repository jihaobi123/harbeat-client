import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from '../api/client'
import { applyRangeLabel, candidateSourceForBar, normalizeRange } from '../annotation/state'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import type {
  AnnotationDraft,
  AnnotationRecord,
  AnnotationTaskId,
  AnnotationValue,
  AnnotationWorkspace,
  BarRange,
  ElementName,
  ElementState,
  SectionLabel,
} from '../types/annotation'


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


export default function AnnotationWorkbench({ onDirtyChange }: Props) {
  const { user } = useAuthStore()
  const { songs, songsLoading, loadSongs } = useMusicStore()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [trackId, setTrackId] = useState('')
  const [workspace, setWorkspace] = useState<AnnotationWorkspace | null>(null)
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

  useEffect(() => {
    if (songs.length === 0) loadSongs()
  }, [loadSongs, songs.length])

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
    setDraft(null)
    setDirty(false)
    setMessage('')
    setError('')
    setConflict(false)
    setWaitingForEnd(false)
    setSelectionStart(0)
    setSelectionEnd(0)
    setLoopSelection(false)
    if (!nextTrackId) return
    setLoading(true)
    try {
      const next = await api.getAnnotationWorkspace(nextTrackId, DATASET_VERSION)
      setWorkspace(next)
      setDraft({
        datasetVersion: next.dataset_version,
        trackId: next.track_id,
        annotatorId: `producer-${user?.id ?? 'unknown'}`,
        bars: next.bars,
        annotations: next.annotations,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '工作区加载失败')
    } finally {
      setLoading(false)
    }
  }

  const selectBar = (barIndex: number) => {
    if (!waitingForEnd) {
      setSelectionStart(barIndex)
      setSelectionEnd(barIndex)
      setWaitingForEnd(true)
    } else {
      setSelectionEnd(barIndex)
      setWaitingForEnd(false)
    }
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
      const next = await api.saveAnnotationWorkspace(workspace.track_id, {
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
    try {
      await audioRef.current.play()
    } catch {
      setError('浏览器没有允许播放，请先点一下播放器的播放按钮')
    }
  }

  const handleAudioTime = () => {
    if (!audioRef.current || !workspace || selectedRange.start >= selectedRange.end) return
    const end = workspace.bars[selectedRange.end - 1].end_sec
    if (audioRef.current.currentTime < end) return
    if (loopSelection) {
      audioRef.current.currentTime = workspace.bars[selectedRange.start].start_sec
      void audioRef.current.play()
    } else {
      audioRef.current.pause()
    }
  }

  const confirmedCount = draft?.annotations.filter(record => (
    record.annotation_status !== 'candidate' && record.annotation_status !== 'rejected'
  )).length ?? 0
  const selectedLabel = selectedRange.start < selectedRange.end
    ? `第 ${selectedRange.start + 1}–${selectedRange.end} 小节`
    : '尚未选择'

  return (
    <main className="flex-1 min-w-0 min-h-0 overflow-y-auto bg-surface-light street-sticker p-3 sm:p-5">
      <div className="max-w-[1500px] mx-auto space-y-4">
        <section className="flex flex-col xl:flex-row xl:items-end gap-3">
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
              disabled={songsLoading || dirty}
              title={dirty ? '请先保存当前修改，再切换歌曲' : undefined}
            >
              <option value="">{songsLoading ? '正在读取歌曲…' : '请选择歌曲'}</option>
              {songs.map(song => (
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
            <section className="street-sticker bg-surface-lighter p-3 sm:p-4 grid lg:grid-cols-[minmax(0,1fr)_auto] gap-4">
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
                  src={api.getStreamUrl(workspace.track_id)}
                  onTimeUpdate={handleAudioTime}
                />
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
                  onClick={() => setLoopSelection(value => !value)}
                >
                  {loopSelection ? '↻ 正在循环' : '↻ 循环所选'}
                </button>
              </div>
            </section>

            <section className="street-sticker bg-surface-lighter p-3 sm:p-4">
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

            <section className="grid xl:grid-cols-2 gap-4">
              <div className="street-sticker bg-surface-lighter p-3 sm:p-4">
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

              <div className="street-sticker bg-surface-lighter p-3 sm:p-4">
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

            <section className="sticky bottom-2 z-10 street-sticker bg-surface-lighter p-3 flex flex-wrap items-center justify-between gap-3">
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
          <section className="street-sticker bg-surface-lighter p-8 text-center">
            <div className="text-4xl mb-3">🏷️</div>
            <h2 className="text-2xl">从上方选择一首已经分析过的歌曲</h2>
            <p className="text-sm mt-2">歌曲需要先有可用的 Beat Grid，工作台才会生成统一的小节边界。</p>
          </section>
        )}
      </div>
    </main>
  )
}
