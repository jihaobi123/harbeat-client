import React, { useState } from 'react'
import { BarChart3, Zap, MapPin } from 'lucide-react'
import { Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration } from '../utils/format'

interface Props {
  song: Song
}

export const AnalysisPanel: React.FC<Props> = ({ song }) => {
  const updateSong = useMusicStore((s) => s.updateSong)
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  const handleAnalyze = async () => {
    if (isAnalyzing || song.analysisStatus === 'analyzing') return

    setIsAnalyzing(true)
    updateSong(song.id, { analysisStatus: 'analyzing' })

    try {
      if (song.sourcePath) {
        // Real analysis in main process (Node.js) — no Web Audio API, no renderer crash
        const result = await window.electronAPI.analyzeAudio(song.sourcePath, song.duration)

        if (result.error) {
          console.error('[Analysis error]', result.error)
          updateSong(song.id, { analysisStatus: 'error' })
        } else {
          updateSong(song.id, {
            analysisStatus: 'completed',
            bpm: result.bpm ?? null,
            beatPoints: result.beatPoints ?? [],
            cuePoints: (result.cuePoints ?? []).map((c, i) => ({
              id: `cue-${song.id}-${i}`,
              ...c,
            })),
          })
        }
      } else {
        // No local file available for analysis
        updateSong(song.id, { analysisStatus: 'error' })
      }
    } catch (err) {
      console.error('[Analysis error]', err)
      updateSong(song.id, { analysisStatus: 'error' })
    } finally {
      setIsAnalyzing(false)
    }
  }

  const statusDot =
    song.analysisStatus === 'completed'
      ? 'bg-green-400'
      : song.analysisStatus === 'analyzing'
      ? 'bg-yellow-400 animate-pulse'
      : song.analysisStatus === 'error'
      ? 'bg-red-400'
      : 'bg-slate-600'

  const statusText =
    song.analysisStatus === 'completed'
      ? '分析完成（FFmpeg 解码 + DSP 检测）'
      : song.analysisStatus === 'analyzing'
      ? '正在分析音频...'
      : song.analysisStatus === 'error'
      ? '分析失败'
      : '未分析'

  return (
    <div className="bg-surface rounded-xl p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white">分析结果</h3>
        {song.analysisStatus !== 'completed' && (
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="flex items-center gap-1.5 bg-primary/10 hover:bg-primary/20 text-primary px-3 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50 active:scale-95"
          >
            {isAnalyzing ? (
              <>
                <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                分析中...
              </>
            ) : (
              <>
                <Zap size={12} />
                开始分析
              </>
            )}
          </button>
        )}
      </div>

      <div className="space-y-2.5">
        {/* BPM */}
        <div className="flex items-center gap-3 p-3 bg-surface-dark rounded-lg border border-border/30">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <BarChart3 size={16} className="text-primary" />
          </div>
          <div>
            <p className="text-[11px] text-slate-500">BPM (每分钟节拍数)</p>
            <p className="text-sm font-bold text-white mt-0.5">
              {song.analysisStatus === 'completed' && song.bpm
                ? song.bpm
                : song.analysisStatus === 'analyzing'
                ? '分析中...'
                : '待分析'}
            </p>
          </div>
        </div>

        {/* Beat Points */}
        <div className="flex items-center gap-3 p-3 bg-surface-dark rounded-lg border border-border/30">
          <div className="w-9 h-9 rounded-lg bg-cyan-500/10 flex items-center justify-center flex-shrink-0">
            <Zap size={16} className="text-cyan-400" />
          </div>
          <div>
            <p className="text-[11px] text-slate-500">Beat Points (节拍点)</p>
            <p className="text-sm font-bold text-white mt-0.5">
              {song.analysisStatus === 'completed'
                ? `${song.beatPoints.length} 个节拍点`
                : song.analysisStatus === 'analyzing'
                ? '分析中...'
                : '待分析'}
            </p>
          </div>
        </div>

        {/* Cue Points */}
        <div className="p-3 bg-surface-dark rounded-lg border border-border/30">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
              <MapPin size={16} className="text-amber-400" />
            </div>
            <div>
              <p className="text-[11px] text-slate-500">Cue Points (标记点)</p>
              <p className="text-sm font-bold text-white mt-0.5">
                {song.analysisStatus === 'completed'
                  ? `${song.cuePoints.length} 个标记点`
                  : song.analysisStatus === 'analyzing'
                  ? '分析中...'
                  : '待分析'}
              </p>
            </div>
          </div>

          {/* Cue point list */}
          {song.cuePoints.length > 0 && (
            <div className="ml-12 mt-2.5 space-y-1.5">
              {song.cuePoints.map((cue) => (
                <div
                  key={cue.id}
                  className="flex items-center gap-2 text-xs"
                >
                  <div
                    className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: cue.color }}
                  />
                  <span className="text-slate-300 font-medium">
                    {cue.label}
                  </span>
                  <span className="text-slate-500 font-mono">
                    {formatDuration(cue.time)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Analysis Status */}
        <div className="flex items-center gap-2 text-xs text-slate-500 pt-1">
          <div className={`w-2 h-2 rounded-full ${statusDot}`} />
          <span>{statusText}</span>
        </div>
      </div>
    </div>
  )
}
