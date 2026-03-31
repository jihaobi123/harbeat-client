import { useCallback, useEffect, useRef, useState } from 'react'
import { useMusicStore } from '../store/useMusicStore'
import WaveformPlayer from './WaveformPlayer'
import * as api from '../api/client'
import { getStemStreamUrl } from '../api/client'

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

/* ─── Synchronized Stem Player ─── */
function StemPlayer({ songId }: { songId: string }) {
  const audioRefs = useRef<Record<string, HTMLAudioElement | null>>({})
  const [isPlaying, setIsPlaying] = useState(false)
  const [muted, setMuted] = useState<Record<string, boolean>>({ vocals: false, drums: false, bass: false, other: false })
  const [ready, setReady] = useState(false)
  const stemNames = ['vocals', 'drums', 'bass', 'other']

  useEffect(() => {
    // Reset state when songId changes
    setIsPlaying(false)
    setReady(false)
    setMuted({ vocals: false, drums: false, bass: false, other: false })

    let loaded = 0
    const checkReady = () => { loaded++; if (loaded >= stemNames.length) setReady(true) }

    stemNames.forEach(name => {
      const audio = audioRefs.current[name]
      if (audio) {
        audio.src = getStemStreamUrl(songId, name)
        audio.preload = 'metadata'
        audio.muted = false
        audio.oncanplaythrough = checkReady
        audio.onended = () => setIsPlaying(false)
      }
    })

    return () => {
      stemNames.forEach(name => {
        const audio = audioRefs.current[name]
        if (audio) { audio.pause(); audio.src = '' }
      })
    }
  }, [songId])

  const togglePlay = useCallback(() => {
    const refs = stemNames.map(n => audioRefs.current[n]).filter(Boolean) as HTMLAudioElement[]
    if (isPlaying) {
      refs.forEach(a => a.pause())
    } else {
      // Sync all to master's time
      const master = refs[0]
      if (master) refs.forEach(a => { a.currentTime = master.currentTime })
      refs.forEach(a => a.play().catch(() => {}))
    }
    setIsPlaying(!isPlaying)
  }, [isPlaying])

  const toggleMute = useCallback((stem: string) => {
    setMuted(prev => {
      const next = { ...prev, [stem]: !prev[stem] }
      const audio = audioRefs.current[stem]
      if (audio) audio.muted = next[stem]
      return next
    })
  }, [])

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
          return (
            <div key={name} className="flex items-center gap-3 px-3 py-2 bg-surface-lighter rounded-lg">
              <audio ref={el => { audioRefs.current[name] = el }} />
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: info.color }} />
              <span className="text-xs text-gray-300 w-16">{info.emoji} {info.label}</span>
              <div className="flex-1" />
              <button
                onClick={() => toggleMute(name)}
                className={`px-2 py-0.5 rounded text-xs transition ${
                  muted[name]
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-green-500/10 text-green-400 hover:bg-green-500/20'
                }`}
              >
                {muted[name] ? '🔇 静音' : '🔊 开启'}
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

/* ─── Main SongDetail ─── */
export default function SongDetail() {
  const { selectedSong, playSong, analyzeSong, deleteSong, updateLibrarySongLocal } = useMusicStore()
  const [analyzing, setAnalyzing] = useState(false)
  const [separating, setSeparating] = useState(false)
  const [stemError, setStemError] = useState('')

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
  const analysisText = {
    completed: '分析完成',
    analyzing: '分析中...',
    error: '分析失败',
    none: '未分析',
  }[song.analysis_status] || '未分析'

  return (
    <div className="w-96 bg-surface-light border-l border-gray-700 flex flex-col shrink-0 overflow-y-auto">
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
      </div>

      {/* Waveform player */}
      <div className="px-5 mt-4">
        <WaveformPlayer song={song} />
      </div>

      {/* Stem separation */}
      <div className="px-5 mt-4 space-y-3">
        {!song.stems && (
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
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="w-full bg-surface hover:bg-surface-lighter disabled:opacity-50 text-gray-300 text-sm py-2 rounded-lg border border-gray-600 transition"
        >
          {analyzing ? '⏳ 分析中...' : analysisCompleted ? '🔄 重新分析' : '🔍 分析 BPM / Key'}
        </button>
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
