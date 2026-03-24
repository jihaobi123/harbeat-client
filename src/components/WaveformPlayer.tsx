import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Pause, Play, SkipBack, SkipForward, Volume2, VolumeX } from 'lucide-react'

import type { Song } from '../types'
import { formatDuration } from '../utils/format'

interface Props {
  song: Song
}

const NUM_BARS = 200

function drawWaveform(canvas: HTMLCanvasElement, peaks: number[], progress: number) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const dpr = window.devicePixelRatio || 1
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  canvas.width = width * dpr
  canvas.height = height * dpr
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, width, height)

  const barWidth = Math.max(1, (width / peaks.length) * 0.7)
  const gap = width / peaks.length

  for (let index = 0; index < peaks.length; index += 1) {
    const x = index * gap + gap / 2 - barWidth / 2
    const amplitude = Math.max(0.05, peaks[index])
    const barHeight = amplitude * height * 0.9
    const y = (height - barHeight) / 2
    const progressIndex = progress * peaks.length
    ctx.fillStyle = index < progressIndex ? '#14b8a6' : '#334155'
    ctx.beginPath()
    ctx.roundRect(x, y, barWidth, barHeight, 1)
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

  const startAnimationLoop = useCallback(() => {
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
    if (!song.sourcePath) {
      setIsLoading(false)
      setError('No local audio file is available.')
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
        const [audioUrl, peaks] = await Promise.all([
          window.electronAPI.getAudioUrl(song.sourcePath),
          window.electronAPI.getPeaks(song.sourcePath, NUM_BARS),
        ])
        if (destroyed) return

        peaksRef.current = peaks || new Array(NUM_BARS).fill(0.1)

        const audio = document.createElement('audio')
        audio.preload = 'metadata'
        audio.src = audioUrl
        audio.volume = volume
        audioRef.current = audio

        audio.addEventListener('loadedmetadata', () => {
          if (destroyed) return
          setDuration(audio.duration)
          setIsLoading(false)
          if (canvasRef.current) drawWaveform(canvasRef.current, peaksRef.current, 0)
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
          if (!destroyed) {
            setIsLoading(false)
            setError('Failed to load audio.')
          }
        })

        startAnimationLoop()
      } catch (initError) {
        console.error('[WaveformPlayer]', initError)
        if (!destroyed) {
          setIsLoading(false)
          setError('Failed to initialize audio playback.')
        }
      }
    }

    void init()

    return () => {
      destroyed = true
      cancelAnimationFrame(rafRef.current)
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
        audioRef.current = null
      }
    }
  }, [song.id, song.sourcePath, startAnimationLoop, volume])

  const togglePlay = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (audio.paused) void audio.play()
    else audio.pause()
  }, [])

  const skipBack = useCallback(() => {
    const audio = audioRef.current
    if (audio) audio.currentTime = Math.max(audio.currentTime - 5, 0)
  }, [])

  const skipForward = useCallback(() => {
    const audio = audioRef.current
    if (audio) audio.currentTime = Math.min(audio.currentTime + 5, audio.duration)
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

  const handleVolumeChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const next = parseFloat(event.target.value)
    setVolume(next)
    setIsMuted(false)
    if (audioRef.current) audioRef.current.volume = next
  }, [])

  const handleSeek = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const audio = audioRef.current
    const canvas = canvasRef.current
    if (!audio || !canvas || !audio.duration) return
    const rect = canvas.getBoundingClientRect()
    const ratio = (event.clientX - rect.left) / rect.width
    audio.currentTime = ratio * audio.duration
  }, [])

  return (
    <div className="bg-surface rounded-xl p-5">
      <h3 className="text-sm font-semibold text-white mb-3">Waveform</h3>
      <div className="relative rounded-lg overflow-hidden bg-surface-dark border border-border/50" style={{ height: 100 }}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-dark z-10 text-slate-400 text-sm">
            Loading waveform...
          </div>
        )}
        {error && !isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-surface-dark z-10 text-red-400 text-sm">
            {error}
          </div>
        )}
        <canvas ref={canvasRef} className="w-full h-full cursor-pointer" onClick={handleSeek} />
      </div>

      <div className="flex items-center gap-4 mt-4">
        <div className="flex items-center gap-1">
          <button onClick={skipBack} className="p-2 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-hover">
            <SkipBack size={16} />
          </button>
          <button onClick={togglePlay} disabled={isLoading || Boolean(error)} className="p-3 bg-primary hover:bg-primary-hover text-white rounded-full transition-all disabled:opacity-40">
            {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-0.5" />}
          </button>
          <button onClick={skipForward} className="p-2 text-slate-400 hover:text-white transition-colors rounded-lg hover:bg-hover">
            <SkipForward size={16} />
          </button>
        </div>

        <div className="flex-1 flex items-center gap-2 text-xs text-slate-500">
          <span className="w-10 text-right font-mono text-slate-300">{formatDuration(currentTime)}</span>
          <div className="flex-1 h-1 bg-surface-dark rounded-full overflow-hidden">
            <div
              className="h-full bg-primary/60 rounded-full transition-all duration-100"
              style={{ width: duration > 0 ? `${(currentTime / duration) * 100}%` : '0%' }}
            />
          </div>
          <span className="w-10 font-mono">{formatDuration(duration)}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button onClick={toggleMute} className="p-1.5 text-slate-400 hover:text-white transition-colors">
            {isMuted || volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <input type="range" min="0" max="1" step="0.01" value={isMuted ? 0 : volume} onChange={handleVolumeChange} className="w-16 accent-primary" />
        </div>
      </div>
    </div>
  )
}
