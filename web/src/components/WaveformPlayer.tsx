import { useCallback, useEffect, useRef, useState } from 'react'
import { useMusicStore } from '../store/useMusicStore'
import { getStreamUrl } from '../api/client'
import type { LibrarySong, CuePoint } from '../types'

const NUM_BARS = 200
const CUE_COLORS = ['#22c55e', '#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#64748b']

function formatTime(sec: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function drawWaveform(
  canvas: HTMLCanvasElement,
  peaks: number[],
  progress: number,
  cuePoints: CuePoint[],
  duration: number,
  loopA: number | null,
  loopB: number | null,
  fadeInSec: number = 0,
  fadeOutSec: number = 0,
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

  // A-B loop region
  if (duration > 0 && loopA != null && loopB != null) {
    const aX = (loopA / duration) * width
    const bX = (loopB / duration) * width
    ctx.fillStyle = 'rgba(99, 102, 241, 0.08)'
    ctx.fillRect(aX, 0, bX - aX, height)
  }

  // Fade zones visualization
  if (duration > 0 && fadeInSec > 0) {
    const fadeInX = (fadeInSec / duration) * width
    const grad = ctx.createLinearGradient(0, 0, fadeInX, 0)
    grad.addColorStop(0, 'rgba(34, 197, 94, 0.25)')
    grad.addColorStop(1, 'rgba(34, 197, 94, 0)')
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, fadeInX, height)
  }
  if (duration > 0 && fadeOutSec > 0) {
    const fadeOutX = ((duration - fadeOutSec) / duration) * width
    const grad = ctx.createLinearGradient(fadeOutX, 0, width, 0)
    grad.addColorStop(0, 'rgba(239, 68, 68, 0)')
    grad.addColorStop(1, 'rgba(239, 68, 68, 0.25)')
    ctx.fillStyle = grad
    ctx.fillRect(fadeOutX, 0, width - fadeOutX, height)
  }

  // Waveform bars
  const barWidth = Math.max(1, (width / peaks.length) * 0.7)
  const gap = width / peaks.length

  for (let i = 0; i < peaks.length; i++) {
    const x = i * gap + gap / 2 - barWidth / 2
    const amplitude = Math.max(0.05, peaks[i])
    const barHeight = amplitude * height * 0.9
    const y = (height - barHeight) / 2
    const progressIndex = progress * peaks.length
    ctx.fillStyle = i < progressIndex ? '#6366f1' : '#334155'
    ctx.beginPath()
    ctx.roundRect(x, y, barWidth, barHeight, 1)
    ctx.fill()
  }

  // Cue markers
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
      ctx.fillStyle = cue.color
      ctx.font = '9px sans-serif'
      ctx.fillText(cue.label, Math.min(x + 2, width - 30), 10)
    }
  }

  // A/B markers
  if (duration > 0 && loopA != null) {
    const x = (loopA / duration) * width
    ctx.strokeStyle = '#22c55e'
    ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
    ctx.fillStyle = '#22c55e'
    ctx.font = 'bold 10px sans-serif'
    ctx.fillText('A', x + 2, height - 3)
  }
  if (duration > 0 && loopB != null) {
    const x = (loopB / duration) * width
    ctx.strokeStyle = '#ef4444'
    ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke()
    ctx.fillStyle = '#ef4444'
    ctx.font = 'bold 10px sans-serif'
    ctx.fillText('B', x + 2, height - 3)
  }
}

/** Extract audio peaks using Web Audio API for waveform visualization */
async function extractPeaks(url: string, numBars: number): Promise<number[]> {
  try {
    const resp = await fetch(url)
    const arrayBuffer = await resp.arrayBuffer()
    const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
    const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)
    const channelData = audioBuffer.getChannelData(0)
    const blockSize = Math.floor(channelData.length / numBars)
    const peaks: number[] = []
    for (let i = 0; i < numBars; i++) {
      let sum = 0
      for (let j = 0; j < blockSize; j++) {
        sum += Math.abs(channelData[i * blockSize + j])
      }
      peaks.push(sum / blockSize)
    }
    const max = Math.max(...peaks, 0.01)
    audioCtx.close()
    return peaks.map(p => p / max)
  } catch {
    return new Array(numBars).fill(0.1)
  }
}

export default function WaveformPlayer({ song }: { song: LibrarySong }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const peaksRef = useRef<number[]>([])
  const rafRef = useRef<number>(0)
  const loopARef = useRef<number | null>(null)
  const loopBRef = useRef<number | null>(null)

  const { updateLibrarySongLocal } = useMusicStore()

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [volume, setVolumeState] = useState(0.8)
  const [isMuted, setIsMuted] = useState(false)

  // A-B loop
  const [loopA, setLoopA] = useState<number | null>(null)
  const [loopB, setLoopB] = useState<number | null>(null)

  // BPM sync
  const [targetBpm, setTargetBpm] = useState('')
  const [playbackRate, setPlaybackRate] = useState(1)

  // DJ fade — default 3s for noticeable effect
  const [fadeIn, setFadeIn] = useState(3)
  const [fadeOut, setFadeOut] = useState(3)

  useEffect(() => { loopARef.current = loopA }, [loopA])
  useEffect(() => { loopBRef.current = loopB }, [loopB])

  const startAnimLoop = useCallback(() => {
    const render = () => {
      const audio = audioRef.current
      const canvas = canvasRef.current
      if (audio && canvas && peaksRef.current.length) {
        // A-B loop enforcement
        if (loopARef.current != null && loopBRef.current != null && audio.currentTime >= loopBRef.current) {
          audio.currentTime = loopARef.current
        }
        // DJ fade — exponential curve for more natural/noticeable effect
        const baseVol = volume
        let effectiveVol = baseVol
        if (fadeIn > 0 && audio.currentTime < fadeIn) {
          const t = audio.currentTime / fadeIn // 0→1
          effectiveVol = Math.pow(t, 2) * baseVol // exponential ease-in
        }
        if (fadeOut > 0 && audio.duration > 0 && (audio.duration - audio.currentTime) < fadeOut) {
          const t = (audio.duration - audio.currentTime) / fadeOut // 1→0
          const fadeOutVol = Math.pow(t, 2) * baseVol // exponential ease-out
          effectiveVol = Math.min(effectiveVol, fadeOutVol)
        }
        if (!isMuted) audio.volume = Math.max(0, Math.min(1, effectiveVol))

        const progress = audio.duration > 0 ? audio.currentTime / audio.duration : 0
        setCurrentTime(audio.currentTime)
        drawWaveform(canvas, peaksRef.current, progress, song.cue_points, audio.duration, loopARef.current, loopBRef.current, fadeIn, fadeOut)
      }
      rafRef.current = requestAnimationFrame(render)
    }
    cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(render)
  }, [volume, isMuted, fadeIn, fadeOut, song.cue_points])

  // Load audio on song change
  useEffect(() => {
    setIsLoading(true)
    setCurrentTime(0)
    setDuration(0)
    setIsPlaying(false)
    setLoopA(null)
    setLoopB(null)
    setTargetBpm('')
    setPlaybackRate(1)

    let destroyed = false
    const streamUrl = getStreamUrl(song.id)

    // Create audio element immediately so playback can start without waiting for waveform
    const audio = document.createElement('audio')
    audio.preload = 'auto'
    audio.src = streamUrl
    audio.volume = volume
    audioRef.current = audio

    audio.addEventListener('loadedmetadata', () => {
      if (destroyed) return
      setDuration(audio.duration)
      setIsLoading(false)
      if (canvasRef.current) drawWaveform(canvasRef.current, peaksRef.current, 0, song.cue_points, audio.duration, null, null, fadeIn, fadeOut)
    })
    audio.addEventListener('play', () => !destroyed && setIsPlaying(true))
    audio.addEventListener('pause', () => !destroyed && setIsPlaying(false))
    audio.addEventListener('ended', () => { if (!destroyed) { setIsPlaying(false); setCurrentTime(0) } })

    startAnimLoop()

    // Load waveform peaks in background (non-blocking)
    extractPeaks(streamUrl, NUM_BARS).then(peaks => {
      if (destroyed) return
      peaksRef.current = peaks
      if (canvasRef.current && audio.duration) {
        drawWaveform(canvasRef.current, peaks, audio.duration > 0 ? audio.currentTime / audio.duration : 0, song.cue_points, audio.duration, null, null, fadeIn, fadeOut)
      }
    })

    return () => {
      destroyed = true
      cancelAnimationFrame(rafRef.current)
      if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = ''; audioRef.current = null }
    }
  }, [song.id])

  // BPM sync
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
    const a = audioRef.current
    if (!a) return
    if (a.paused) a.play().catch(() => {})
    else a.pause()
  }, [])

  const skip = useCallback((delta: number) => {
    const a = audioRef.current
    if (a) a.currentTime = Math.max(0, Math.min(a.currentTime + delta, a.duration))
  }, [])

  const handleSeek = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const a = audioRef.current, c = canvasRef.current
    if (!a || !c || !a.duration) return
    const rect = c.getBoundingClientRect()
    a.currentTime = ((e.clientX - rect.left) / rect.width) * a.duration
  }, [])

  const handleAddCue = useCallback(() => {
    const a = audioRef.current
    if (!a) return
    const time = Math.round(a.currentTime * 100) / 100
    const idx = song.cue_points.length
    const newCue: CuePoint = {
      id: `cue-${song.id}-${Date.now()}`,
      time,
      label: `Cue ${idx + 1}`,
      color: CUE_COLORS[idx % CUE_COLORS.length],
    }
    updateLibrarySongLocal(song.id, {
      cue_points: [...song.cue_points, newCue].sort((a, b) => a.time - b.time),
    })
  }, [song.id, song.cue_points, updateLibrarySongLocal])

  const handleDeleteCue = useCallback((cueId: string) => {
    updateLibrarySongLocal(song.id, {
      cue_points: song.cue_points.filter(c => c.id !== cueId),
    })
  }, [song.id, song.cue_points, updateLibrarySongLocal])

  const handleSetA = useCallback(() => { if (audioRef.current) setLoopA(Math.round(audioRef.current.currentTime * 100) / 100) }, [])
  const handleSetB = useCallback(() => {
    if (!audioRef.current) return
    const b = Math.round(audioRef.current.currentTime * 100) / 100
    if (loopA != null && b > loopA) setLoopB(b)
  }, [loopA])

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div className="bg-surface rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-white">波形播放器</h3>

      {/* Waveform canvas */}
      <div className="relative rounded-lg overflow-hidden bg-surface border border-gray-700" style={{ height: 100 }}>
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center z-10 text-gray-400 text-sm">加载波形...</div>
        )}
        <canvas ref={canvasRef} className="w-full h-full cursor-pointer" onClick={handleSeek} />
      </div>

      {/* Transport */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <button onClick={() => skip(-5)} className="p-1.5 text-gray-400 hover:text-white rounded transition text-sm">⏪</button>
          <button
            onClick={togglePlay}
            disabled={isLoading}
            className="w-9 h-9 rounded-full bg-primary hover:bg-primary-dark text-white flex items-center justify-center text-sm transition disabled:opacity-40"
          >
            {isPlaying ? '⏸' : '▶'}
          </button>
          <button onClick={() => skip(5)} className="p-1.5 text-gray-400 hover:text-white rounded transition text-sm">⏩</button>
        </div>

        <div className="flex-1 flex items-center gap-2 text-xs">
          <span className="text-gray-300 w-10 text-right font-mono">{formatTime(currentTime)}</span>
          <div className="flex-1 h-1 bg-gray-700 rounded-full overflow-hidden">
            <div className="h-full bg-primary/60 rounded-full" style={{ width: `${progress}%` }} />
          </div>
          <span className="text-gray-500 w-10 font-mono">{formatTime(duration)}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button onClick={() => { setIsMuted(!isMuted); if (audioRef.current) audioRef.current.volume = isMuted ? volume : 0 }} className="text-gray-400 hover:text-white text-sm">
            {isMuted ? '🔇' : '🔊'}
          </button>
          <input
            type="range" min={0} max={1} step={0.01}
            value={isMuted ? 0 : volume}
            onChange={(e) => { const v = parseFloat(e.target.value); setVolumeState(v); setIsMuted(false); if (audioRef.current) audioRef.current.volume = v }}
            className="w-16 accent-primary"
          />
        </div>
      </div>

      {/* Extended controls */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-2 border-t border-gray-700/50 text-xs">
        {/* Cue */}
        <button onClick={handleAddCue} className="flex items-center gap-1 text-amber-400 hover:text-amber-300 transition">📌 添加 Cue</button>

        {/* A-B Loop */}
        <div className="flex items-center gap-1.5">
          <span className={loopA != null && loopB != null ? 'text-primary' : 'text-gray-500'}>🔁</span>
          <button onClick={handleSetA} className="px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 hover:bg-green-500/20 transition">
            A{loopA != null ? ` ${formatTime(loopA)}` : ''}
          </button>
          <button onClick={handleSetB} disabled={loopA == null} className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition disabled:opacity-40">
            B{loopB != null ? ` ${formatTime(loopB)}` : ''}
          </button>
          {(loopA != null || loopB != null) && (
            <button onClick={() => { setLoopA(null); setLoopB(null) }} className="text-gray-500 hover:text-gray-300 transition">清除</button>
          )}
        </div>

        {/* BPM Sync */}
        {song.bpm && (
          <div className="flex items-center gap-1.5 text-gray-400">
            <span>BPM同步:</span>
            <input
              type="number" min={40} max={300}
              placeholder={String(Math.round(song.bpm))}
              value={targetBpm}
              onChange={(e) => setTargetBpm(e.target.value)}
              className="w-14 px-1.5 py-0.5 bg-surface border border-gray-600 rounded text-white text-center text-xs focus:outline-none focus:border-primary"
            />
            {playbackRate !== 1 && <span className="text-primary font-medium">{playbackRate.toFixed(2)}x</span>}
          </div>
        )}

        {/* DJ Fade — green=fade in, red=fade out */}
        <div className="flex items-center gap-1.5 text-gray-400">
          <span>🎚️ 淡入淡出:</span>
          <label className="flex items-center gap-0.5">
            <span className="text-green-400">入</span>
            <input
              type="number" min={0} max={30} step={0.5}
              value={fadeIn || ''}
              onChange={(e) => setFadeIn(parseFloat(e.target.value) || 0)}
              className="w-10 px-1 py-0.5 bg-surface border border-green-600/50 rounded text-white text-center text-xs focus:outline-none focus:border-green-400"
            />
            <span>s</span>
          </label>
          <label className="flex items-center gap-0.5">
            <span className="text-red-400">出</span>
            <input
              type="number" min={0} max={30} step={0.5}
              value={fadeOut || ''}
              onChange={(e) => setFadeOut(parseFloat(e.target.value) || 0)}
              className="w-10 px-1 py-0.5 bg-surface border border-red-600/50 rounded text-white text-center text-xs focus:outline-none focus:border-red-400"
            />
            <span>s</span>
          </label>
          {(fadeIn > 0 || fadeOut > 0) && (
            <span className="text-gray-500 text-[10px]">波形绿区=渐入 红区=渐出</span>
          )}
        </div>
      </div>

      {/* Cue Points list */}
      {song.cue_points.length > 0 && (
        <div className="pt-2 border-t border-gray-700/50">
          <h4 className="text-xs font-semibold text-gray-500 mb-1.5">Cue 标记点</h4>
          <div className="space-y-1">
            {song.cue_points.map(cue => (
              <div key={cue.id} className="flex items-center gap-2 text-xs group">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: cue.color }} />
                <span className="text-gray-300">{cue.label}</span>
                <span className="text-gray-500 font-mono">{formatTime(cue.time)}</span>
                <button
                  onClick={() => { if (audioRef.current) audioRef.current.currentTime = cue.time }}
                  className="text-primary hover:text-primary-dark transition ml-auto"
                >跳转</button>
                <button
                  onClick={() => handleDeleteCue(cue.id)}
                  className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 transition"
                >删除</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
