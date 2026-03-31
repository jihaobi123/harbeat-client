import { useState } from 'react'
import { useMusicStore } from '../store/useMusicStore'
import WaveformPlayer from './WaveformPlayer'
import * as api from '../api/client'

function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '--:--'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

const STEM_LABELS: Record<string, string> = {
  vocals: '🎤 人声',
  drums: '🥁 鼓点',
  bass: '🎸 贝斯',
  other: '🎹 其他',
}

export default function SongDetail() {
  const { selectedSong, playSong, analyzeSong, deleteSong } = useMusicStore()
  const [analyzing, setAnalyzing] = useState(false)
  const [separating, setSeparating] = useState(false)
  const [stems, setStems] = useState<Record<string, string> | null>(null)
  const [stemError, setStemError] = useState('')
  const [playingStem, setPlayingStem] = useState<string | null>(null)
  const [stemAudio, setStemAudio] = useState<HTMLAudioElement | null>(null)

  if (!selectedSong) {
    return null
  }

  const song = selectedSong

  const handleAnalyze = async () => {
    setAnalyzing(true)
    try { await analyzeSong(song.id) } finally { setAnalyzing(false) }
  }

  const handleSeparateStems = async () => {
    setSeparating(true)
    setStemError('')
    setStems(null)
    try {
      const result = await api.separateStems(song.id)
      setStems(result.stems)
    } catch (e: any) {
      setStemError(e.message || '分离失败')
    } finally {
      setSeparating(false)
    }
  }

  const playStemTrack = (stemKey: string, url: string) => {
    if (stemAudio) {
      stemAudio.pause()
      stemAudio.src = ''
    }
    if (playingStem === stemKey) {
      setPlayingStem(null)
      setStemAudio(null)
      return
    }
    const audio = new Audio(url)
    audio.play()
    audio.onended = () => { setPlayingStem(null); setStemAudio(null) }
    setStemAudio(audio)
    setPlayingStem(stemKey)
  }

  return (
    <div className="w-96 bg-surface-light border-l border-gray-700 flex flex-col shrink-0 overflow-y-auto">
      {/* Header */}
      <div className="p-5">
        <div className="w-full aspect-video bg-surface rounded-xl flex items-center justify-center text-5xl mb-4">
          🎵
        </div>
        <h3 className="text-lg font-bold text-white truncate">{song.title}</h3>
        <p className="text-sm text-gray-400 truncate">{song.artist}</p>
      </div>

      {/* Metadata cards */}
      <div className="px-5 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <MetaCard label="BPM" value={song.bpm ? `${Math.round(song.bpm)}` : '未分析'} accent={!!song.bpm} />
          <MetaCard label="时长" value={formatDuration(song.duration)} />
          <MetaCard label="格式" value={song.format?.toUpperCase() || '-'} />
          <MetaCard label="大小" value={song.file_size ? `${(song.file_size / (1024 * 1024)).toFixed(1)} MB` : '-'} />
        </div>

        {/* Beat points count */}
        {song.beat_points.length > 0 && (
          <MetaCard label="Beat 节拍点" value={`${song.beat_points.length} 个`} />
        )}
      </div>

      {/* Waveform player */}
      <div className="px-5 mt-4">
        <WaveformPlayer song={song} />
      </div>

      {/* Stem separation */}
      <div className="px-5 mt-4">
        <div className="bg-surface rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-semibold text-white">🥁 鼓点分离</h4>
            <button
              onClick={handleSeparateStems}
              disabled={separating}
              className="text-xs bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-3 py-1 rounded-lg transition"
            >
              {separating ? '分离中...' : stems ? '重新分离' : '开始分离'}
            </button>
          </div>
          {separating && (
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              使用 Demucs 进行音轨分离，可能需要几分钟...
            </div>
          )}
          {stemError && <p className="text-xs text-red-400">{stemError}</p>}
          {stems && (
            <div className="space-y-1.5">
              {Object.entries(stems).map(([key, url]) => (
                <button
                  key={key}
                  onClick={() => playStemTrack(key, url)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
                    playingStem === key ? 'bg-primary/20 text-primary' : 'bg-surface-lighter text-gray-300 hover:text-white'
                  }`}
                >
                  <span>{STEM_LABELS[key] || key}</span>
                  <span className="ml-auto text-xs">{playingStem === key ? '⏸ 停止' : '▶ 播放'}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="p-5 mt-auto space-y-2">
        <button
          onClick={() => playSong(song)}
          className="w-full bg-primary hover:bg-primary-dark text-white text-sm font-medium py-2 rounded-lg transition"
        >
          ▶ 播放
        </button>
        <button
          onClick={handleAnalyze}
          disabled={analyzing}
          className="w-full bg-surface hover:bg-surface-lighter disabled:opacity-50 text-gray-300 text-sm py-2 rounded-lg border border-gray-600 transition"
        >
          {analyzing ? '⏳ 分析中...' : '🔍 分析 BPM / Key'}
        </button>
        <button
          onClick={() => { if (confirm('确定删除此歌曲？')) deleteSong(song.id) }}
          className="w-full text-gray-500 hover:text-red-400 text-sm py-2 transition"
        >
          删除
        </button>
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
