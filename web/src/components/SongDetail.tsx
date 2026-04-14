import { useCallback, useEffect, useRef, useState } from 'react'
import { useMusicStore } from '../store/useMusicStore'
import WaveformPlayer from './WaveformPlayer'
import * as api from '../api/client'
import { getStemStreamUrl, getProcessedStreamUrl } from '../api/client'
import { DANCE_STYLES, DANCE_STYLE_LABELS, DANCE_STYLE_COLORS } from '../types'
import type { DanceStyle, QualityMode, StyleProcessResult } from '../types'

function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '--:--'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const STEM_INFO: Record<string, { label: string; emoji: string; color: string }> = {
  vocals: { label: '人声', emoji: '🎤', color: '#f472b6' },
  drums: { label: '鼓点', emoji: '🥁', color: '#fb923c' },
  bass: { label: '贝斯', emoji: '🎸', color: '#34d399' },
  other: { label: '其他', emoji: '🎹', color: '#60a5fa' },
}

/* ─── Synchronized Stem Player (Web Audio API) ─── */
function StemPlayer({ songId }: { songId: string }) {
  const audioRefs = useRef<Record<string, HTMLAudioElement | null>>({})
  const audioCtxRef = useRef<AudioContext | null>(null)
  const gainNodesRef = useRef<Record<string, GainNode>>({})
  const connectedRef = useRef(false)
  const syncTimerRef = useRef<number>(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [volumes, setVolumes] = useState<Record<string, number>>({ vocals: 1, drums: 1, bass: 1, other: 1 })
  const [muted, setMuted] = useState<Record<string, boolean>>({ vocals: false, drums: false, bass: false, other: false })
  const [ready, setReady] = useState(false)
  const stemNames = ['vocals', 'drums', 'bass', 'other']

  // Connect audio elements to Web Audio API graph (lazy, on first user gesture)
  const ensureAudioGraph = useCallback(() => {
    if (connectedRef.current) return
    const ctx = new AudioContext()
    audioCtxRef.current = ctx

    stemNames.forEach(name => {
      const audio = audioRefs.current[name]
      if (audio) {
        const source = ctx.createMediaElementSource(audio)
        const gain = ctx.createGain()
        source.connect(gain)
        gain.connect(ctx.destination)
        gainNodesRef.current[name] = gain
      }
    })
    connectedRef.current = true
  }, [])

  useEffect(() => {
    setIsPlaying(false)
    setReady(false)
    setVolumes({ vocals: 1, drums: 1, bass: 1, other: 1 })
    setMuted({ vocals: false, drums: false, bass: false, other: false })

    let loaded = 0
    const checkReady = () => {
      loaded++
      if (loaded >= stemNames.length) setReady(true)
    }

    stemNames.forEach(name => {
      const audio = audioRefs.current[name]
      if (audio) {
        audio.src = getStemStreamUrl(songId, name)
        audio.preload = 'auto'
        audio.crossOrigin = 'anonymous'
        audio.oncanplaythrough = checkReady
        audio.onended = () => setIsPlaying(false)
      }
    })

    return () => {
      if (syncTimerRef.current) cancelAnimationFrame(syncTimerRef.current)
      stemNames.forEach(name => {
        const audio = audioRefs.current[name]
        if (audio) { audio.pause(); audio.src = '' }
      })
      audioCtxRef.current?.close()
      audioCtxRef.current = null
      gainNodesRef.current = {}
      connectedRef.current = false
    }
  }, [songId])

  // Drift correction: keep all stems within 30ms of master
  const startSyncLoop = useCallback(() => {
    const tick = () => {
      const master = audioRefs.current.vocals
      if (!master || master.paused) return
      const masterTime = master.currentTime
      stemNames.forEach(name => {
        if (name === 'vocals') return
        const audio = audioRefs.current[name]
        if (audio && Math.abs(audio.currentTime - masterTime) > 0.03) {
          audio.currentTime = masterTime
        }
      })
      syncTimerRef.current = requestAnimationFrame(tick)
    }
    syncTimerRef.current = requestAnimationFrame(tick)
  }, [])

  const togglePlay = useCallback(() => {
    ensureAudioGraph()
    const ctx = audioCtxRef.current
    if (ctx?.state === 'suspended') ctx.resume()

    const refs = stemNames.map(n => audioRefs.current[n]).filter(Boolean) as HTMLAudioElement[]
    if (isPlaying) {
      refs.forEach(a => a.pause())
      if (syncTimerRef.current) cancelAnimationFrame(syncTimerRef.current)
    } else {
      // Sync all to master's time, then start simultaneously
      const master = refs[0]
      if (master) refs.forEach(a => { a.currentTime = master.currentTime })
      Promise.all(refs.map(a => a.play())).catch(() => {})
      startSyncLoop()
    }
    setIsPlaying(!isPlaying)
  }, [isPlaying, ensureAudioGraph, startSyncLoop])

  const handleVolumeChange = useCallback((stem: string, value: number) => {
    setVolumes(prev => ({ ...prev, [stem]: value }))
    const gain = gainNodesRef.current[stem]
    if (gain) {
      gain.gain.value = value
    } else {
      // Fallback before AudioContext is created
      const audio = audioRefs.current[stem]
      if (audio) audio.volume = value
    }
    setMuted(prev => ({ ...prev, [stem]: value === 0 }))
  }, [])

  const toggleMute = useCallback((stem: string) => {
    setMuted(prev => {
      const next = { ...prev, [stem]: !prev[stem] }
      const gain = gainNodesRef.current[stem]
      if (gain) {
        if (next[stem]) {
          gain.gain.value = 0
        } else {
          const vol = volumes[stem] === 0 ? 1 : volumes[stem]
          gain.gain.value = vol
          if (volumes[stem] === 0) setVolumes(v => ({ ...v, [stem]: 1 }))
        }
      } else {
        const audio = audioRefs.current[stem]
        if (audio) {
          audio.muted = next[stem]
          if (!next[stem] && volumes[stem] === 0) {
            setVolumes(v => ({ ...v, [stem]: 1 }))
            audio.volume = 1
          }
        }
      }
      return next
    })
  }, [volumes])

  return (
    <div className="bg-surface rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-white">🎛️ 音轨分离播放</h4>
        <button
          onClick={togglePlay}
          disabled={!ready}
          className="text-xs bg-primary hover:bg-primary-dark disabled:opacity-40 text-white px-3 py-1 rounded-lg transition"
        >
          {isPlaying ? '⏸ 暂停全部' : '▶ 同步播放'}
        </button>
      </div>
      <div className="space-y-2">
        {stemNames.map(name => {
          const info = STEM_INFO[name] || { label: name, emoji: '🎵', color: '#aaa' }
          const vol = volumes[name]
          const isMuted = muted[name]
          return (
            <div key={name} className="flex items-center gap-2.5 px-3 py-2 bg-surface-lighter rounded-lg">
              <audio ref={el => { audioRefs.current[name] = el }} />
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: info.color }} />
              <span className="text-xs text-gray-300 w-16 shrink-0">{info.emoji} {info.label}</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={isMuted ? 0 : vol}
                onChange={e => handleVolumeChange(name, parseFloat(e.target.value))}
                className="flex-1 h-1.5 appearance-none rounded-full cursor-pointer"
                style={{
                  background: `linear-gradient(to right, ${info.color} ${(isMuted ? 0 : vol) * 100}%, #374151 ${(isMuted ? 0 : vol) * 100}%)`,
                  accentColor: info.color,
                }}
              />
              <span className="text-xs text-gray-500 w-8 text-right shrink-0">
                {isMuted ? 0 : Math.round(vol * 100)}%
              </span>
              <button
                onClick={() => toggleMute(name)}
                className={`w-7 h-7 flex items-center justify-center rounded text-sm transition shrink-0 ${
                  isMuted
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-surface text-gray-400 hover:text-white'
                }`}
                title={isMuted ? '取消静音' : '静音'}
              >
                {isMuted ? '🔇' : vol > 0.5 ? '🔊' : vol > 0 ? '🔉' : '🔈'}
              </button>
            </div>
          )
        })}
      </div>
      {!ready && (
        <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
          <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          加载音轨中...
        </div>
      )}
    </div>
  )
}

/* ─── Song Tag Editor ─── */
const ENERGY_OPTIONS = [
  { value: 'low', label: '🔋 低' },
  { value: 'medium', label: '⚡ 中' },
  { value: 'high', label: '🔥 高' },
]
const SCENE_OPTIONS = [
  { value: 'freeplay', label: '🎧 自由' },
  { value: 'cypher', label: '🔄 Cypher' },
  { value: 'battle', label: '⚔️ Battle' },
  { value: 'showcase', label: '🎭 Showcase' },
  { value: 'training', label: '📚 训练' },
]

function SongTagEditor({ title, artist }: { title: string; artist: string }) {
  const [styles, setStyles] = useState<DanceStyle[]>([])
  const [energy, setEnergy] = useState<string[]>([])
  const [scenes, setScenes] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const toggleItem = <T extends string>(list: T[], item: T): T[] =>
    list.includes(item) ? list.filter(x => x !== item) : [...list, item]

  const toggleStyle = (s: DanceStyle) => {
    setStyles(prev => toggleItem(prev, s))
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.upsertSongTags({
        title,
        artist,
        tags: styles,
        energy: energy.length ? energy : undefined,
        scenes: scenes.length ? scenes : undefined,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      // silently fail
    } finally {
      setSaving(false)
    }
  }

  const hasAnyTag = styles.length > 0 || energy.length > 0 || scenes.length > 0

  return (
    <div className="bg-surface rounded-xl p-4">
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <h4 className="text-sm font-semibold text-white">🏷️ 标签管理</h4>
        <span className="text-xs text-gray-500">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          {/* Dance styles */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">舞种风格</label>
            <div className="flex flex-wrap gap-1">
              {DANCE_STYLES.map(style => (
                <button
                  key={style}
                  onClick={() => toggleStyle(style)}
                  className="px-2 py-0.5 rounded-full text-[11px] font-medium transition"
                  style={{
                    background: styles.includes(style) ? DANCE_STYLE_COLORS[style] + '33' : 'transparent',
                    color: styles.includes(style) ? DANCE_STYLE_COLORS[style] : '#6b7280',
                    border: `1px solid ${styles.includes(style) ? DANCE_STYLE_COLORS[style] : '#374151'}`,
                  }}
                >
                  {DANCE_STYLE_LABELS[style]}
                </button>
              ))}
            </div>
          </div>

          {/* Energy */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">能量等级（可多选）</label>
            <div className="flex gap-1.5">
              {ENERGY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => { setEnergy(prev => toggleItem(prev, opt.value)); setSaved(false) }}
                  className={`px-2.5 py-0.5 rounded-lg text-[11px] transition ${
                    energy.includes(opt.value)
                      ? 'bg-primary/20 text-primary border border-primary'
                      : 'bg-surface-lighter text-gray-500 border border-gray-700 hover:border-gray-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Scene */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">适用场景（可多选）</label>
            <div className="flex flex-wrap gap-1.5">
              {SCENE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => { setScenes(prev => toggleItem(prev, opt.value)); setSaved(false) }}
                  className={`px-2.5 py-0.5 rounded-lg text-[11px] transition ${
                    scenes.includes(opt.value)
                      ? 'bg-primary/20 text-primary border border-primary'
                      : 'bg-surface-lighter text-gray-500 border border-gray-700 hover:border-gray-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Save */}
          <button
            onClick={handleSave}
            disabled={!hasAnyTag || saving}
            className={`w-full py-1.5 rounded-lg text-xs font-medium transition ${
              saved
                ? 'bg-green-500/20 text-green-400'
                : 'bg-primary/20 text-primary hover:bg-primary/30 disabled:opacity-40'
            }`}
          >
            {saved ? '✓ 已保存' : saving ? '保存中...' : '💾 保存标签'}
          </button>
          <p className="text-[10px] text-gray-600">标签用于智能推荐和练习列表生成</p>
        </div>
      )}
    </div>
  )
}

/* ─── Dance Style Processor ─── */
const QUALITY_OPTIONS: { value: QualityMode; label: string }[] = [
  { value: 'fast', label: '⚡ 快速预览' },
  { value: 'balanced', label: '⚖️ 均衡' },
  { value: 'hq', label: '💎 高质量' },
]

function StyleProcessor({ songId, title }: { songId: string; title: string }) {
  const [selectedStyles, setSelectedStyles] = useState<DanceStyle[]>([])
  const [quality, setQuality] = useState<QualityMode>('balanced')
  const [processing, setProcessing] = useState(false)
  const [result, setResult] = useState<StyleProcessResult | null>(null)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [playingStyle, setPlayingStyle] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const togglePlay = (style: string, filePath: string) => {
    if (playingStyle === style) {
      audioRef.current?.pause()
      setPlayingStyle(null)
      return
    }
    if (audioRef.current) {
      audioRef.current.pause()
    }
    const audio = new Audio(getProcessedStreamUrl(filePath))
    audio.onended = () => setPlayingStyle(null)
    audio.onerror = () => setPlayingStyle(null)
    audio.play()
    audioRef.current = audio
    setPlayingStyle(style)
  }

  const toggleStyle = (s: DanceStyle) =>
    setSelectedStyles(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])

  const handleProcess = async () => {
    if (selectedStyles.length === 0) return
    setProcessing(true)
    setError('')
    setResult(null)
    try {
      const catalogSong = await api.getCatalogSongs()
      const match = catalogSong.songs.find(s => s.title === title)
      if (!match) { setError('服务器未找到此歌曲的目录记录'); return }
      const res = await api.processSongStyle(match.id, {
        styles: selectedStyles,
        quality_mode: quality,
      })
      setResult(res)
    } catch (e: any) {
      setError(e.message || '处理失败')
    } finally {
      setProcessing(false)
    }
  }

  return (
    <div className="bg-surface rounded-xl p-4">
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <h4 className="text-sm font-semibold text-white">🎶 街舞风格处理</h4>
        <span className="text-xs text-gray-500">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          <p className="text-[10px] text-gray-500">选择舞种，自动生成适合该风格的音乐成品（BPM调整 + 鼓点强化 + 能量适配）</p>

          {/* Style selection */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">目标舞种（可多选）</label>
            <div className="flex flex-wrap gap-1">
              {DANCE_STYLES.filter(s => s !== 'other').map(style => (
                <button
                  key={style}
                  onClick={() => toggleStyle(style)}
                  className="px-2 py-0.5 rounded-full text-[11px] font-medium transition"
                  style={{
                    background: selectedStyles.includes(style) ? DANCE_STYLE_COLORS[style] + '33' : 'transparent',
                    color: selectedStyles.includes(style) ? DANCE_STYLE_COLORS[style] : '#6b7280',
                    border: `1px solid ${selectedStyles.includes(style) ? DANCE_STYLE_COLORS[style] : '#374151'}`,
                  }}
                >
                  {DANCE_STYLE_LABELS[style]}
                </button>
              ))}
            </div>
          </div>

          {/* Quality mode */}
          <div>
            <label className="text-[10px] text-gray-500 mb-1 block">处理质量</label>
            <div className="flex gap-1.5">
              {QUALITY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setQuality(opt.value)}
                  className={`px-2.5 py-0.5 rounded-lg text-[11px] transition ${
                    quality === opt.value
                      ? 'bg-primary/20 text-primary border border-primary'
                      : 'bg-surface-lighter text-gray-500 border border-gray-700 hover:border-gray-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Process button */}
          <button
            onClick={handleProcess}
            disabled={selectedStyles.length === 0 || processing}
            className="w-full py-2 rounded-lg text-xs font-semibold transition bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 disabled:opacity-40 text-white"
          >
            {processing ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                处理中...
              </span>
            ) : `🔥 生成 ${selectedStyles.length} 种风格成品`}
          </button>

          {/* Error */}
          {error && <p className="text-xs text-red-400">{error}</p>}

          {/* Results */}
          {result && (
            <div className="space-y-2 mt-2">
              <h5 className="text-[11px] text-gray-400 font-medium">✅ 处理完成</h5>
              {Object.entries(result.processed_files).map(([style, filePath]) => {
                const styleMeta = result.meta[style]
                const styleKey = style as DanceStyle
                return (
                  <div key={style} className="bg-surface-lighter rounded-lg p-3 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => togglePlay(style, filePath)}
                        className="w-6 h-6 rounded-full flex items-center justify-center text-xs transition hover:scale-110"
                        style={{ background: DANCE_STYLE_COLORS[styleKey] || '#64748b' }}
                        title={playingStyle === style ? '暂停' : '播放'}
                      >
                        {playingStyle === style ? '⏸' : '▶'}
                      </button>
                      <span className="text-sm font-medium text-white">
                        {DANCE_STYLE_LABELS[styleKey] || style}
                      </span>
                      {styleMeta?.bpm && (
                        <span className="text-[10px] text-gray-500 ml-auto">BPM: {styleMeta.bpm}</span>
                      )}
                    </div>
                    {styleMeta?.selected_models && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Object.entries(styleMeta.selected_models).slice(0, 4).map(([k, v]) => (
                          <span key={k} className="text-[9px] bg-surface px-1.5 py-0.5 rounded text-gray-500">
                            {k}: {(v as string).split(':')[0]}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── Main SongDetail ─── */
export default function SongDetail() {
  const { selectedSong, playSong, analyzeSong, deleteSong, updateLibrarySongLocal } = useMusicStore()
  const [analyzing, setAnalyzing] = useState(false)
  const [separating, setSeparating] = useState(false)
  const [stemError, setStemError] = useState('')

  // Auto-poll when analysis is in progress
  useEffect(() => {
    if (!selectedSong) return
    const inProgress = selectedSong.analysis_status === 'pending' || selectedSong.analysis_status === 'analyzing' || selectedSong.analysis_status === 'none'
    if (!inProgress) return
    const timer = setInterval(async () => {
      try {
        const updated = await api.getLibrarySong(selectedSong.id)
        if (updated && updated.analysis_status !== selectedSong.analysis_status) {
          updateLibrarySongLocal(selectedSong.id, updated)
        }
      } catch { /* ignore polling errors */ }
    }, 5000)
    return () => clearInterval(timer)
  }, [selectedSong?.id, selectedSong?.analysis_status, updateLibrarySongLocal])

  if (!selectedSong) return null
  const song = selectedSong

  const handleAnalyze = async () => {
    setAnalyzing(true)
    try { await analyzeSong(song.id) } finally { setAnalyzing(false) }
  }

  const handleSeparateStems = async () => {
    setSeparating(true)
    setStemError('')
    try {
      await api.separateStems(song.id)
      // Reload song data to get updated stems field
      const res = await api.getLibrarySongs()
      const updated = res.songs.find(s => s.id === song.id)
      if (updated) {
        updateLibrarySongLocal(song.id, updated)
      }
    } catch (e: any) {
      setStemError(e.message || '分离失败')
    } finally {
      setSeparating(false)
    }
  }

  const handleDeleteCue = (cueId: string) => {
    updateLibrarySongLocal(song.id, {
      cue_points: song.cue_points.filter(c => c.id !== cueId),
    })
  }

  const analysisCompleted = song.analysis_status === 'completed'
  const analysisInProgress = song.analysis_status === 'pending' || song.analysis_status === 'analyzing' || song.analysis_status === 'none'
  const analysisText = {
    completed: '分析完成',
    analyzing: '⏳ 分析中...',
    pending: '⏳ 处理中...',
    none: '⏳ 等待分析...',
    error: '分析失败',
  }[song.analysis_status] || '未分析'

  return (
    <div className="hidden md:flex w-96 bg-surface-light border-l border-gray-700 flex-col shrink-0 overflow-y-auto">
      {/* Header */}
      <div className="p-5">
        <div className="w-full aspect-video bg-surface rounded-xl flex items-center justify-center text-5xl mb-4">🎵</div>
        <h3 className="text-lg font-bold text-white truncate">{song.title}</h3>
        <p className="text-sm text-gray-400 truncate">{song.artist}</p>
      </div>

      {/* Analysis cards */}
      <div className="px-5 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <MetaCard label="BPM" value={song.bpm ? `${Math.round(song.bpm)}` : analysisText} accent={!!song.bpm} />
          <MetaCard label="Key" value={song.key ? `${song.camelot_key} · ${song.key}` : analysisText} accent={!!song.key} />
          <MetaCard label="时长" value={formatDuration(song.duration)} />
          <MetaCard label="格式" value={song.format?.toUpperCase() || '-'} />
          <MetaCard label="大小" value={song.file_size ? `${(song.file_size / (1024 * 1024)).toFixed(1)} MB` : '-'} />
          {analysisCompleted && (
            <MetaCard label="Beat 节拍" value={`${song.beat_points.length} 个`} accent />
          )}
        </div>

        {/* Cue Points */}
        {song.cue_points.length > 0 && (
          <div className="bg-surface rounded-xl p-4">
            <h4 className="text-xs font-semibold text-gray-500 mb-2">📌 Cue 标记点 ({song.cue_points.length})</h4>
            <div className="space-y-1.5">
              {song.cue_points.map(cue => (
                <div key={cue.id} className="flex items-center gap-2 text-xs group">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: cue.color }} />
                  <span className="text-gray-300 font-medium">{cue.label}</span>
                  <span className="text-gray-500 font-mono">{formatDuration(cue.time)}</span>
                  <button
                    onClick={() => handleDeleteCue(cue.id)}
                    className="ml-auto opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition text-xs"
                  >✕</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tag editor */}
        <SongTagEditor title={song.title} artist={song.artist} />

        {/* Dance style processor */}
        <StyleProcessor songId={song.id} title={song.title} />
      </div>

      {/* Waveform player */}
      <div className="px-5 mt-4">
        <WaveformPlayer song={song} />
      </div>

      {/* Stem separation */}
      <div className="px-5 mt-4 space-y-3">
        {!song.stems && analysisInProgress && (
          <div className="bg-surface rounded-xl p-4">
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-semibold text-white">🎛️ 音轨分离</h4>
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                自动处理中...
              </div>
            </div>
          </div>
        )}
        {!song.stems && !analysisInProgress && (
          <div className="bg-surface rounded-xl p-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-white">🎛️ 音轨分离</h4>
              <button
                onClick={handleSeparateStems}
                disabled={separating}
                className="text-xs bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-3 py-1 rounded-lg transition"
              >
                {separating ? '分离中...' : '开始分离'}
              </button>
            </div>
            {separating && (
              <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
                <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                使用 Demucs 进行音轨分离，可能需要几分钟...
              </div>
            )}
            {stemError && <p className="text-xs text-red-400 mt-2">{stemError}</p>}
          </div>
        )}

        {/* Synchronized stem player */}
        {song.stems && <StemPlayer songId={song.id} />}
      </div>

      {/* Actions */}
      <div className="p-5 mt-auto space-y-2">
        <button
          onClick={() => playSong(song)}
          className="w-full bg-primary hover:bg-primary-dark text-white text-sm font-medium py-2 rounded-lg transition"
        >▶ 播放</button>
        {analysisInProgress ? (
          <div className="w-full bg-surface text-gray-400 text-sm py-2 rounded-lg border border-gray-600 text-center flex items-center justify-center gap-2">
            <div className="w-3.5 h-3.5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            自动分析处理中...
          </div>
        ) : (
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            className="w-full bg-surface hover:bg-surface-lighter disabled:opacity-50 text-gray-300 text-sm py-2 rounded-lg border border-gray-600 transition"
          >
            {analyzing ? '⏳ 分析中...' : analysisCompleted ? '🔄 重新分析' : '🔍 分析 BPM / Key'}
          </button>
        )}
        <button
          onClick={() => { if (confirm('确定删除此歌曲？')) deleteSong(song.id) }}
          className="w-full text-gray-500 hover:text-red-400 text-sm py-2 transition"
        >删除</button>
      </div>
    </div>
  )
}

function MetaCard({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="bg-surface rounded-lg p-3">
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      <div className={`text-sm font-medium ${accent ? 'text-primary' : 'text-white'}`}>{value}</div>
    </div>
  )
}
