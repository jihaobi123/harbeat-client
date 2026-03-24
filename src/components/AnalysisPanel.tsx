import React, { useState } from 'react'
import { BarChart3, MapPin, Zap } from 'lucide-react'

import type { Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration } from '../utils/format'

interface Props {
  song: Song
}

export const AnalysisPanel: React.FC<Props> = ({ song }) => {
  const updateSong = useMusicStore((state) => state.updateSong)
  const [isAnalyzing, setIsAnalyzing] = useState(false)

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
      </div>

      <div className="space-y-2.5">
        <MetricCard label="BPM" value={song.bpm ? String(song.bpm) : statusText} icon={<BarChart3 size={16} className="text-primary" />} />
        <MetricCard
          label="Beat Points"
          value={song.analysisStatus === 'completed' ? `${song.beatPoints.length}` : statusText}
          icon={<Zap size={16} className="text-cyan-400" />}
        />
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
                <div key={cue.id} className="flex items-center gap-2 text-xs">
                  <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: cue.color }} />
                  <span className="text-slate-300 font-medium">{cue.label}</span>
                  <span className="text-slate-500 font-mono">{formatDuration(cue.time)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
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
