import React, { useEffect, useRef, useState } from 'react'
import { BarChart3, Loader2, MapPin, Music, Scissors, Trash2, Volume2, VolumeX, Zap } from 'lucide-react'

import type { Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration } from '../utils/format'

interface Props {
  song: Song
}

export const AnalysisPanel: React.FC<Props> = ({ song }) => {
  const updateSong = useMusicStore((state) => state.updateSong)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isSeparating, setIsSeparating] = useState(false)
  const [stemError, setStemError] = useState<string | null>(null)

  const handleAnalyze = async () => {
    if (isAnalyzing || !song.sourcePath) return
    setIsAnalyzing(true)
    updateSong(song.id, { analysisStatus: 'analyzing' })

    try {
      const result = await window.electronAPI.analyzeAudio(song.sourcePath, song.duration)
      if (result.error) throw new Error(result.error)
      updateSong(song.id, {
        analysisStatus: 'completed',
        bpm: result.bpm ?? null,
        key: result.key ?? null,
        camelotKey: result.camelotKey ?? null,
        beatPoints: result.beatPoints ?? [],
        cuePoints: (result.cuePoints ?? []).map((cue, index) => ({
          id: `cue-${song.id}-${index}`,
          ...cue,
        })),
      })
    } catch (error) {
      console.error('[AnalysisPanel]', error)
      updateSong(song.id, { analysisStatus: 'error' })
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleSeparateStems = async () => {
    if (isSeparating || !song.sourcePath) return
    setIsSeparating(true)
    setStemError(null)

    try {
      const result = await window.electronAPI.separateStems(song.sourcePath)
      if (result.error) throw new Error(result.error)
      if (result.stems) {
        updateSong(song.id, { stems: result.stems })
      }
    } catch (error) {
      console.error('[StemSeparation]', error)
      setStemError(String(error))
    } finally {
      setIsSeparating(false)
    }
  }

  const handleDeleteCue = (cueId: string) => {
    updateSong(song.id, {
      cuePoints: song.cuePoints.filter((c) => c.id !== cueId),
    })
  }

  const statusText = {
    completed: 'Analysis completed',
    analyzing: 'Analyzing audio...',
    error: 'Analysis failed',
    none: 'Not analyzed yet',
  }[song.analysisStatus]

  return (
    <div className="bg-surface rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">Analysis</h3>
        <div className="flex items-center gap-2">
          {song.analysisStatus !== 'completed' && (
            <button
              onClick={handleAnalyze}
              disabled={isAnalyzing || !song.sourcePath}
              className="flex items-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary px-3 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50"
            >
              <Zap size={12} />
              {isAnalyzing ? 'Running...' : 'Run Analysis'}
            </button>
          )}
          {song.analysisStatus === 'completed' && !song.stems && (
            <button
              onClick={handleSeparateStems}
              disabled={isSeparating}
              className="flex items-center gap-1.5 bg-violet-500/10 hover:bg-violet-500/20 text-violet-400 px-3 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50"
            >
              {isSeparating ? <Loader2 size={12} className="animate-spin" /> : <Scissors size={12} />}
              {isSeparating ? 'Separating...' : 'Separate Stems'}
            </button>
          )}
        </div>
      </div>

      <div className="space-y-2.5">
        <MetricCard label="BPM" value={song.bpm ? String(song.bpm) : statusText} icon={<BarChart3 size={16} className="text-primary" />} />
        <MetricCard
          label="Key"
          value={song.key ? `${song.camelotKey}  ·  ${song.key}` : statusText}
          icon={<Music size={16} className="text-violet-400" />}
        />
        <MetricCard
          label="Beat Points"
          value={song.analysisStatus === 'completed' ? `${song.beatPoints.length}` : statusText}
          icon={<Zap size={16} className="text-cyan-400" />}
        />

        {/* Cue Points */}
        <div className="p-3 bg-surface-dark rounded-lg border border-border/30">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
              <MapPin size={16} className="text-amber-400" />
            </div>
            <div>
              <p className="text-[11px] text-slate-500">Cue Points</p>
              <p className="text-sm font-bold text-white mt-0.5">
                {song.analysisStatus === 'completed' ? `${song.cuePoints.length}` : statusText}
              </p>
            </div>
          </div>
          {song.cuePoints.length > 0 && (
            <div className="ml-12 mt-2.5 space-y-1.5">
              {song.cuePoints.map((cue) => (
                <div key={cue.id} className="flex items-center gap-2 text-xs group">
                  <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: cue.color }} />
                  <span className="text-slate-300 font-medium">{cue.label}</span>
                  <span className="text-slate-500 font-mono">{formatDuration(cue.time)}</span>
                  <button
                    onClick={() => handleDeleteCue(cue.id)}
                    className="ml-auto opacity-0 group-hover:opacity-100 p-0.5 text-slate-500 hover:text-red-400 transition-all"
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Stem Separation Error */}
        {stemError && (
          <p className="text-xs text-red-400 bg-red-500/10 rounded-lg p-2">{stemError}</p>
        )}

        {/* Stem Player */}
        {song.stems && <StemPlayer stems={song.stems} />}

        <p className="text-xs text-slate-500">{statusText}</p>
      </div>
    </div>
  )
}

const MetricCard: React.FC<{ label: string; value: string; icon: React.ReactNode }> = ({ label, value, icon }) => (
  <div className="flex items-center gap-3 p-3 bg-surface-dark rounded-lg border border-border/30">
    <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
      {icon}
    </div>
    <div>
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="text-sm font-bold text-white mt-0.5">{value}</p>
    </div>
  </div>
)

/* ── Stem Player: synchronized playback with individual mute toggles ── */

const STEM_LABELS: Record<string, { label: string; color: string }> = {
  vocals: { label: 'Vocals', color: '#f472b6' },
  drums: { label: 'Drums', color: '#fb923c' },
  bass: { label: 'Bass', color: '#34d399' },
  other: { label: 'Other', color: '#60a5fa' },
}

const StemPlayer: React.FC<{ stems: { vocals: string; drums: string; bass: string; other: string } }> = ({ stems }) => {
  const audioRefs = useRef<Record<string, HTMLAudioElement | null>>({})
  const [urls, setUrls] = useState<Record<string, string>>({})
  const [isPlaying, setIsPlaying] = useState(false)
  const [muted, setMuted] = useState<Record<string, boolean>>({ vocals: false, drums: false, bass: false, other: false })
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    const loadUrls = async () => {
      const result: Record<string, string> = {}
      for (const [name, filePath] of Object.entries(stems)) {
        result[name] = await window.electronAPI.getAudioUrl(filePath)
      }
      if (!cancelled) { setUrls(result); setReady(true) }
    }
    void loadUrls()
    return () => { cancelled = true }
  }, [stems])

  const togglePlay = () => {
    const refs = Object.values(audioRefs.current).filter(Boolean) as HTMLAudioElement[]
    if (isPlaying) {
      refs.forEach((a) => a.pause())
    } else {
      // Sync all to first track's time
      const master = refs[0]
      if (master) refs.forEach((a) => { a.currentTime = master.currentTime })
      refs.forEach((a) => void a.play())
    }
    setIsPlaying(!isPlaying)
  }

  const toggleMute = (stem: string) => {
    setMuted((prev) => {
      const next = { ...prev, [stem]: !prev[stem] }
      const audio = audioRefs.current[stem]
      if (audio) audio.muted = next[stem]
      return next
    })
  }

  if (!ready) return null

  return (
    <div className="p-3 bg-surface-dark rounded-lg border border-border/30">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[11px] text-slate-500 font-medium">Stems</p>
        <button
          onClick={togglePlay}
          className="flex items-center gap-1 text-xs text-primary hover:text-primary-hover transition-colors"
        >
          {isPlaying ? '⏸ Pause' : '▶ Play All'}
        </button>
      </div>
      <div className="space-y-1.5">
        {Object.entries(urls).map(([name, url]) => {
          const info = STEM_LABELS[name] || { label: name, color: '#aaa' }
          return (
            <div key={name} className="flex items-center gap-2">
              <audio
                ref={(el) => { audioRefs.current[name] = el }}
                src={url}
                preload="metadata"
                onEnded={() => setIsPlaying(false)}
              />
              <div className="w-2 h-2 rounded-full" style={{ backgroundColor: info.color }} />
              <span className="text-xs text-slate-300 w-14">{info.label}</span>
              <button
                onClick={() => toggleMute(name)}
                className={`p-1 rounded transition-colors ${muted[name] ? 'text-slate-600' : 'text-slate-300 hover:text-white'}`}
              >
                {muted[name] ? <VolumeX size={13} /> : <Volume2 size={13} />}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
