import React, { useEffect, useRef, useState, useCallback } from 'react'
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Volume2,
  VolumeX,
} from 'lucide-react'
import { Song } from '../types'
import { formatDuration } from '../utils/format'

interface Props {
  song: Song
}

const NUM_BARS = 200

/** Draw waveform bars on a canvas */
function drawWaveform(
  canvas: HTMLCanvasElement,
  peaks: number[],
  progress: number // 0..1
) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, w, h)

  const barW = Math.max(1, (w / peaks.length) * 0.7)
  const gap = w / peaks.length

  for (let i = 0; i < peaks.length; i++) {
    const x = i * gap + gap / 2 - barW / 2
    const amp = Math.max(0.05, peaks[i])
    const barH = amp * h * 0.9
    const y = (h - barH) / 2

    const progressIdx = progress * peaks.length
    ctx.fillStyle = i < progressIdx ? '#7c3aed' : '#4c4c6d'
    ctx.beginPath()
    ctx.roundRect(x, y, barW, barH, 1)
    ctx.fill()
  }
}

export const WaveformPlayer: React.FC<Props> = ({ song }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const peaksRef = useRef<number[]>([])
  const rafRef = useRef<number>(0)

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [volume, setVolume] = useState(0.8)
  const [isMuted, setIsMuted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Animation loop – redraws canvas with current progress
  const startAnimLoop = useCallback(() => {
    const render = () => {
      const audio = audioRef.current
      const canvas = canvasRef.current
      if (audio && canvas && peaksRef.current.length) {
        const progress = audio.duration > 0 ? audio.currentTime / audio.duration : 0
        setCurrentTime(audio.currentTime)
        drawWaveform(canvas, peaksRef.current, progress)
      }
      rafRef.current = requestAnimationFrame(render)
    }
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(render)
  }, [])

  useEffect(() => {
    // Songs without local file can't be played
    if (!song.sourcePath) {
      setIsLoading(false)
      setError('platform')
      return
    }

    setIsLoading(true)
    setError(null)
    setCurrentTime(0)
    setDuration(0)
    setIsPlaying(false)

    let destroyed = false

    const init = async () => {
      try {
        // 1. Get audio URL + peaks in parallel
        const [audioUrl, peaks] = await Promise.all([
          window.electronAPI.getAudioUrl(song.sourcePath),
          window.electronAPI.getPeaks(song.sourcePath, NUM_BARS),
        ])
        if (destroyed) return

        peaksRef.current = peaks || new Array(NUM_BARS).fill(0.1)

        // 2. Create <audio> element – no Web Audio API at all
        const audio = document.createElement('audio')
        audio.preload = 'metadata'
        audio.src = audioUrl
        audioRef.current = audio

        audio.addEventListener('loadedmetadata', () => {
          if (destroyed) return
          setDuration(audio.duration)
          setIsLoading(false)
          audio.volume = volume
          // Initial draw
          if (canvasRef.current) {
            drawWaveform(canvasRef.current, peaksRef.current, 0)
          }
        })

        audio.addEventListener('play', () => !destroyed && setIsPlaying(true))
        audio.addEventListener('pause', () => !destroyed && setIsPlaying(false))
        audio.addEventListener('ended', () => {
          if (!destroyed) {
            setIsPlaying(false)
            setCurrentTime(0)
          }
        })

        audio.addEventListener('error', () => {
          console.error('[audio error]', audio.error)
          if (!destroyed) {
            setIsLoading(false)
            setError('load')
          }
        })

        // Start animation loop for progress
        startAnimLoop()
      } catch (err) {
        console.error('[WaveformPlayer init error]', err)
        if (!destroyed) {
          setIsLoading(false)
          setError('load')
        }
      }
    }

    init()

    return () => {
      destroyed = true
      cancelAnimationFrame(rafRef.current)
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
        audioRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [song.id])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) {
      audio.play()
    } else {
      audio.pause()
    }
  }, [])

  const skipForward = useCallback(() => {
    const audio = audioRef.current
    if (audio) audio.currentTime = Math.min(audio.currentTime + 5, audio.duration)
  }, [])

  const skipBack = useCallback(() => {
    const audio = audioRef.current
    if (audio) audio.currentTime = Math.max(audio.currentTime - 5, 0)
  }, [])

  const toggleMute = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (isMuted) {
      audio.volume = volume
      setIsMuted(false)
    } else {
      audio.volume = 0
      setIsMuted(true)
    }
  }, [isMuted, volume])

  const handleVolumeChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = parseFloat(e.target.value)
      setVolume(val)
      setIsMuted(false)
      if (audioRef.current) audioRef.current.volume = val
    },
    []
  )

  // Click on canvas to seek
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const audio = audioRef.current
      const canvas = canvasRef.current
      if (!audio || !canvas || !audio.duration) return
      const rect = canvas.getBoundingClientRect()
      const x = e.clientX - rect.left
      const ratio = x / rect.width
      audio.currentTime = ratio * audio.duration
    },
    []
  )

  // Platform song placeholder
  if (error === 'platform') {
    return (
      <div className="bg-surface rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3">波形 & 播放</h3>
        <div className="h-[100px] flex items-center justify-center bg-surface-dark rounded-lg border border-border/50">
          <p className="text-slate-500 text-sm">
            平台曲库歌曲 — 加入曲库并导入本地文件后可播放
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-surface rounded-xl p-5">
      <h3 className="text-sm font-semibold text-white mb-3">波形 & 播放</h3>

      {/* Waveform Container */}
      <div className="relative rounded-lg overflow-hidden bg-surface-dark border border-border/50" style={{ height: 100 }}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-dark z-10">
            <div className="flex items-center gap-2 text-slate-400 text-sm">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              加载波形中...
            </div>
          </div>
        )}
        {error === 'load' && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-dark z-10">
            <p className="text-red-400 text-sm">音频加载失败，请检查文件格式</p>
          </div>
        )}
        <canvas
          ref={canvasRef}
          className="w-full h-full cursor-pointer"
          onClick={handleCanvasClick}
        />
      </div>

      {/* Playback Controls */}
      <div className="flex items-center gap-4 mt-4">
        <div className="flex items-center gap-1">
          <button
            onClick={skipBack}
            className="p-2 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-hover"
            title="后退5秒"
          >
            <SkipBack size={16} />
          </button>
          <button
            onClick={togglePlay}
            className="p-3 bg-primary hover:bg-primary-hover text-white rounded-full transition-all active:scale-95 disabled:opacity-40"
            disabled={isLoading || !!error}
          >
            {isPlaying ? (
              <Pause size={18} />
            ) : (
              <Play size={18} className="ml-0.5" />
            )}
          </button>
          <button
            onClick={skipForward}
            className="p-2 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-hover"
            title="前进5秒"
          >
            <SkipForward size={16} />
          </button>
        </div>

        <div className="flex-1 flex items-center gap-2 text-xs text-slate-500">
          <span className="w-10 text-right font-mono text-slate-300">
            {formatDuration(currentTime)}
          </span>
          <div className="flex-1 h-1 bg-surface-dark rounded-full overflow-hidden">
            <div
              className="h-full bg-primary/60 rounded-full transition-all duration-100"
              style={{
                width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%',
              }}
            />
          </div>
          <span className="w-10 font-mono">{formatDuration(duration)}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={toggleMute}
            className="p-1.5 text-slate-400 hover:text-white transition-colors"
          >
            {isMuted || volume === 0 ? (
              <VolumeX size={16} />
            ) : (
              <Volume2 size={16} />
            )}
          </button>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={isMuted ? 0 : volume}
            onChange={handleVolumeChange}
            className="w-16 accent-primary"
          />
        </div>
      </div>
    </div>
  )
}
