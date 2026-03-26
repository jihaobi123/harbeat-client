import React, { useCallback, useEffect, useRef, useState } from 'react'
import { MapPin, Pause, Play, Repeat, SkipBack, SkipForward, Volume2, VolumeX } from 'lucide-react'

import type { CuePoint, Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration } from '../utils/format'

interface Props {
  song: Song
}

const NUM_BARS = 200

const CUE_COLORS = ['#22c55e', '#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#64748b']

function drawWaveform(
  canvas: HTMLCanvasElement,
  peaks: number[],
  progress: number,
  cuePoints: CuePoint[],
  duration: number,
  loopA: number | null,
  loopB: number | null,
) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const dpr = window.devicePixelRatio || 1
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  canvas.width = width * dpr
  canvas.height = height * dpr
  ctx.scale(dpr, dpr)
  ctx.clearRect(0, 0, width, height)

  // Draw A-B loop region
  if (duration > 0 && loopA != null && loopB != null) {
    const aX = (loopA / duration) * width
    const bX = (loopB / duration) * width
    ctx.fillStyle = 'rgba(20, 184, 166, 0.08)'
    ctx.fillRect(aX, 0, bX - aX, height)
  }

  // Draw waveform bars
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

  // Draw cue markers
  if (duration > 0) {
    for (const cue of cuePoints) {
      const x = (cue.time / duration) * width
      ctx.strokeStyle = cue.color
      ctx.lineWidth = 1.5
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(x, 0)
      ctx.lineTo(x, height)
      ctx.stroke()
      ctx.setLineDash([])

      // Label
      ctx.fillStyle = cue.color
      ctx.font = '9px sans-serif'
      ctx.fillText(cue.label, Math.min(x + 2, width - 30), 10)
    }
  }

  // Draw A/B markers
  if (duration > 0 && loopA != null) {
    const x = (loopA / duration) * width
    ctx.strokeStyle = '#22c55e'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, height)
    ctx.stroke()
    ctx.fillStyle = '#22c55e'
    ctx.font = 'bold 10px sans-serif'
    ctx.fillText('A', x + 2, height - 3)
  }
  if (duration > 0 && loopB != null) {
    const x = (loopB / duration) * width
    ctx.strokeStyle = '#ef4444'
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, height)
    ctx.stroke()
    ctx.fillStyle = '#ef4444'
    ctx.font = 'bold 10px sans-serif'
    ctx.fillText('B', x + 2, height - 3)
  }
}

export const WaveformPlayer: React.FC<Props> = ({ song }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const peaksRef = useRef<number[]>([])
  const rafRef = useRef<number>(0)
  const loopARef = useRef<number | null>(null)
  const loopBRef = useRef<number | null>(null)

  const updateSong = useMusicStore((state) => state.updateSong)

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [volume, setVolume] = useState(0.8)
  const [isMuted, setIsMuted] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // A-B loop
  const [loopA, setLoopA] = useState<number | null>(null)
  const [loopB, setLoopB] = useState<number | null>(null)
  const [loopEnabled, setLoopEnabled] = useState(false)

  // BPM sync
  const [targetBpm, setTargetBpm] = useState<string>('')
  const [playbackRate, setPlaybackRate] = useState(1)

  // DJ fade
  const [fadeIn, setFadeIn] = useState(0)
  const [fadeOut, setFadeOut] = useState(0)

  // Keep refs in sync for animation loop
  useEffect(() => { loopARef.current = loopA }, [loopA])
  useEffect(() => { loopBRef.current = loopB }, [loopB])

  const startAnimationLoop = useCallback(() => {
    const render = () => {
      const audio = audioRef.current
      const canvas = canvasRef.current
      if (audio && canvas && peaksRef.current.length) {
        // A-B loop enforcement
        if (loopARef.current != null && loopBRef.current != null && audio.currentTime >= loopBRef.current) {
          audio.currentTime = loopARef.current
        }

        // DJ fade volume control
        const baseVol = volume
        let effectiveVol = baseVol
        if (fadeIn > 0 && audio.currentTime < fadeIn) {
          effectiveVol = (audio.currentTime / fadeIn) * baseVol
        }
        if (fadeOut > 0 && audio.duration > 0 && (audio.duration - audio.currentTime) < fadeOut) {
          effectiveVol = Math.min(effectiveVol, ((audio.duration - audio.currentTime) / fadeOut) * baseVol)
        }
        if (!isMuted) audio.volume = Math.max(0, Math.min(1, effectiveVol))

        const progress = audio.duration > 0 ? audio.currentTime / audio.duration : 0
        setCurrentTime(audio.currentTime)
        drawWaveform(canvas, peaksRef.current, progress, song.cuePoints, audio.duration, loopARef.current, loopBRef.current)
      }
      rafRef.current = requestAnimationFrame(render)
    }
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(render)
  }, [volume, isMuted, fadeIn, fadeOut, song.cuePoints])

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
    setLoopA(null)
    setLoopB(null)
    setTargetBpm('')
    setPlaybackRate(1)

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
          if (canvasRef.current) drawWaveform(canvasRef.current, peaksRef.current, 0, song.cuePoints, audio.duration, null, null)
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

  // BPM sync: adjust playback rate when targetBpm changes
  useEffect(() => {
    const parsed = parseFloat(targetBpm)
    if (song.bpm && parsed > 0) {
      const rate = Math.max(0.25, Math.min(4, parsed / song.bpm))
      setPlaybackRate(rate)
      if (audioRef.current) audioRef.current.playbackRate = rate
    } else {
      setPlaybackRate(1)
      if (audioRef.current) audioRef.current.playbackRate = 1
    }
  }, [targetBpm, song.bpm])

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

  // Feature 3: Add cue at current position
  const handleAddCue = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    const time = Math.round(audio.currentTime * 100) / 100
    const nextIndex = song.cuePoints.length
    const newCue: CuePoint = {
      id: `cue-${song.id}-manual-${Date.now()}`,
      time,
      label: `Cue ${nextIndex + 1}`,
      color: CUE_COLORS[nextIndex % CUE_COLORS.length],
    }
    updateSong(song.id, {
      cuePoints: [...song.cuePoints, newCue].sort((a, b) => a.time - b.time),
    })
  }, [song.id, song.cuePoints, updateSong])

  // Feature 4: A-B loop
  const handleSetA = useCallback(() => {
    const audio = audioRef.current
    if (audio) setLoopA(Math.round(audio.currentTime * 100) / 100)
  }, [])

  const handleSetB = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      const b = Math.round(audio.currentTime * 100) / 100
      if (loopA != null && b > loopA) setLoopB(b)
    }
  }, [loopA])

  const handleClearLoop = useCallback(() => {
    setLoopA(null)
    setLoopB(null)
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

      {/* Transport controls */}
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

      {/* Extended controls: Cue · A-B Loop · BPM Sync · Fade */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mt-3 pt-3 border-t border-border/30 text-xs">
        {/* Cue */}
        <button
          onClick={handleAddCue}
          className="flex items-center gap-1 text-amber-400 hover:text-amber-300 transition-colors"
        >
          <MapPin size={13} /> Add Cue
        </button>

        {/* A-B Loop */}
        <div className="flex items-center gap-1.5">
          <Repeat size={13} className={loopA != null && loopB != null ? 'text-primary' : 'text-slate-500'} />
          <button onClick={handleSetA} className="px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors">
            A{loopA != null ? ` ${formatDuration(loopA)}` : ''}
          </button>
          <button onClick={handleSetB} disabled={loopA == null} className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors disabled:opacity-40">
            B{loopB != null ? ` ${formatDuration(loopB)}` : ''}
          </button>
          {(loopA != null || loopB != null) && (
            <button onClick={handleClearLoop} className="text-slate-500 hover:text-slate-300 transition-colors">
              Clear
            </button>
          )}
        </div>

        {/* BPM Sync */}
        {song.bpm && (
          <div className="flex items-center gap-1.5 text-slate-400">
            <span>BPM:</span>
            <input
              type="number"
              min="40"
              max="300"
              placeholder={String(song.bpm)}
              value={targetBpm}
              onChange={(e) => setTargetBpm(e.target.value)}
              className="w-14 px-1.5 py-0.5 bg-surface-dark border border-border/50 rounded text-white text-center text-xs focus:outline-none focus:border-primary"
            />
            {playbackRate !== 1 && (
              <span className="text-primary font-medium">{playbackRate.toFixed(2)}x</span>
            )}
          </div>
        )}

        {/* DJ Fade */}
        <div className="flex items-center gap-1.5 text-slate-400">
          <span>Fade:</span>
          <label className="flex items-center gap-0.5">
            In
            <input
              type="number"
              min="0"
              max="30"
              step="0.5"
              value={fadeIn || ''}
              onChange={(e) => setFadeIn(parseFloat(e.target.value) || 0)}
              className="w-10 px-1 py-0.5 bg-surface-dark border border-border/50 rounded text-white text-center text-xs focus:outline-none focus:border-primary"
            />
            s
          </label>
          <label className="flex items-center gap-0.5">
            Out
            <input
              type="number"
              min="0"
              max="30"
              step="0.5"
              value={fadeOut || ''}
              onChange={(e) => setFadeOut(parseFloat(e.target.value) || 0)}
              className="w-10 px-1 py-0.5 bg-surface-dark border border-border/50 rounded text-white text-center text-xs focus:outline-none focus:border-primary"
            />
            s
          </label>
        </div>
      </div>
    </div>
  )
}
