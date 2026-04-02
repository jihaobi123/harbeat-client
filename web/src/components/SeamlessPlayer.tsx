import { useRef, useState, useEffect } from 'react'
import { getProcessedStreamUrl } from '../api/client'

export interface SeamlessTrack {
  songId: number
  title: string
  artist: string
  filePath: string
}

interface Props {
  tracks: SeamlessTrack[]
  crossfadeSec?: number
  accentColor?: string
  onEnd?: () => void
}

function fmt(sec: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function SeamlessPlayer({
  tracks,
  crossfadeSec = 4,
  accentColor = '#8b5cf6',
  onEnd,
}: Props) {
  const [playing, setPlaying] = useState(false)
  const [idx, setIdx] = useState(0)
  const [time, setTime] = useState(0)
  const [dur, setDur] = useState(0)
  const [fading, setFading] = useState(false)

  const audioA = useRef<HTMLAudioElement | null>(null)
  const audioB = useRef<HTMLAudioElement | null>(null)

  // All mutable state in a single ref to avoid stale closures
  const st = useRef({
    slot: 'A' as 'A' | 'B',
    idx: 0,
    fading: false,
    playing: false,
    alive: false,
    raf: 0,
  })

  // Latest-value refs
  const tracksR = useRef(tracks)
  tracksR.current = tracks
  const onEndR = useRef(onEnd)
  onEndR.current = onEnd
  const xfR = useRef(crossfadeSec)
  xfR.current = crossfadeSec

  // Reference to startTick function defined inside effect
  const ctrlR = useRef<{ startTick: () => void }>({ startTick: () => {} })

  // Active / next audio getter
  const ac = () => (st.current.slot === 'A' ? audioA : audioB).current
  const nx = () => (st.current.slot === 'A' ? audioB : audioA).current

  // ── Main setup effect ──────────────────────────────────────────────────
  useEffect(() => {
    const r = st.current
    r.alive = true
    r.slot = 'A'
    r.idx = 0
    r.fading = false
    r.playing = false
    setIdx(0)
    setTime(0)
    setDur(0)
    setFading(false)

    const a = new Audio()
    const b = new Audio()
    audioA.current = a
    audioB.current = b

    // ── RAF tick: time updates + crossfade trigger + volume animation ──
    function tick() {
      if (!r.playing || !r.alive) return
      const active = ac()
      if (active && isFinite(active.duration) && active.duration > 0) {
        setTime(active.currentTime)
        setDur(active.duration)

        const left = active.duration - active.currentTime
        const xf = xfR.current
        const ni = r.idx + 1

        // Trigger crossfade when near end (only if track is long enough)
        if (
          !r.fading &&
          left <= xf &&
          left > 0.05 &&
          active.duration > xf * 2.5 &&
          ni < tracksR.current.length
        ) {
          r.fading = true
          setFading(true)
          const next = nx()!
          const rdy = () => {
            next.removeEventListener('canplay', rdy)
            if (r.alive) next.play().catch(() => {})
          }
          next.addEventListener('canplay', rdy)
          next.src = getProcessedStreamUrl(tracksR.current[ni].filePath)
          next.volume = 0
          next.load()
        }

        // Equal-power crossfade (cosine / sine curve)
        if (r.fading) {
          const tl = Math.max(0, active.duration - active.currentTime)
          const p = Math.max(0, Math.min(1, 1 - tl / xf))
          active.volume = Math.cos(p * Math.PI / 2)
          const next = nx()
          if (next) next.volume = Math.sin(p * Math.PI / 2)
        }
      }
      r.raf = requestAnimationFrame(tick)
    }

    function startTick() {
      cancelAnimationFrame(r.raf)
      if (r.playing && r.alive) r.raf = requestAnimationFrame(tick)
    }
    ctrlR.current = { startTick }

    // ── Track ended handler ──
    function doEnded() {
      if (!r.alive) return
      if (r.fading) {
        // Crossfade complete – switch to the incoming track
        const out = ac()!
        out.pause()
        out.volume = 1
        out.src = ''
        r.slot = r.slot === 'A' ? 'B' : 'A'
        r.fading = false
        setFading(false)
        r.idx += 1
        setIdx(r.idx)
      } else {
        // No crossfade – advance gaplessly or end
        const ni = r.idx + 1
        if (ni < tracksR.current.length) {
          r.idx = ni
          setIdx(ni)
          const c = ac()!
          const rdy = () => {
            c.removeEventListener('canplay', rdy)
            if (r.alive && r.idx === ni) c.play().catch(() => {})
          }
          c.addEventListener('canplay', rdy)
          c.src = getProcessedStreamUrl(tracksR.current[ni].filePath)
          c.volume = 1
          c.load()
        } else {
          r.playing = false
          setPlaying(false)
          cancelAnimationFrame(r.raf)
          onEndR.current?.()
        }
      }
    }

    a.onended = () => { if (r.slot === 'A') doEnded() }
    b.onended = () => { if (r.slot === 'B') doEnded() }
    a.onerror = () => { if (r.slot === 'A' && r.alive) doEnded() }
    b.onerror = () => { if (r.slot === 'B' && r.alive) doEnded() }

    // ── Auto-play first track ──
    if (tracksR.current.length) {
      const rdy = () => {
        a.removeEventListener('canplay', rdy)
        if (!r.alive) return
        a.play()
          .then(() => {
            r.playing = true
            setPlaying(true)
            startTick()
          })
          .catch(() => {})
      }
      a.addEventListener('canplay', rdy)
      a.src = getProcessedStreamUrl(tracksR.current[0].filePath)
      a.volume = 1
      a.load()
    }

    return () => {
      r.alive = false
      cancelAnimationFrame(r.raf)
      a.onended = null; b.onended = null
      a.onerror = null; b.onerror = null
      a.pause(); a.src = ''
      b.pause(); b.src = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracks])

  // ── Controls ─────────────────────────────────────────────────────────
  const togglePlay = () => {
    const r = st.current
    if (!r.alive) return
    if (r.playing) {
      ac()?.pause()
      if (r.fading) nx()?.pause()
      r.playing = false
      setPlaying(false)
      cancelAnimationFrame(r.raf)
    } else {
      ac()?.play().catch(() => {})
      if (r.fading) nx()?.play().catch(() => {})
      r.playing = true
      setPlaying(true)
      ctrlR.current.startTick()
    }
  }

  const skipTo = (ti: number) => {
    const r = st.current
    if (ti < 0 || ti >= tracksR.current.length || !r.alive) return
    cancelAnimationFrame(r.raf)
    audioA.current?.pause()
    audioB.current?.pause()
    r.fading = false
    setFading(false)
    r.slot = 'A'
    r.idx = ti
    setIdx(ti)

    const a = audioA.current!
    const rdy = () => {
      a.removeEventListener('canplay', rdy)
      if (!r.alive || r.idx !== ti) return
      a.play()
        .then(() => {
          r.playing = true
          setPlaying(true)
          ctrlR.current.startTick()
        })
        .catch(() => {})
    }
    a.addEventListener('canplay', rdy)
    a.src = getProcessedStreamUrl(tracksR.current[ti].filePath)
    a.volume = 1
    a.load()
  }

  // ── Derived ──────────────────────────────────────────────────────────
  const track = tracks[idx]
  const nextTrack = idx + 1 < tracks.length ? tracks[idx + 1] : null
  const pct = dur > 0 ? (time / dur) * 100 : 0

  if (!tracks.length) return null

  // ── Render ───────────────────────────────────────────────────────────
  return (
    <div className="bg-gradient-to-b from-surface-light to-surface rounded-xl border border-gray-700/50 overflow-hidden shadow-xl">
      {/* Header */}
      <div className="px-4 py-2.5 flex items-center gap-2 border-b border-gray-700/50">
        <span className="relative flex h-2.5 w-2.5">
          {playing && (
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
              style={{ background: accentColor }}
            />
          )}
          <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: accentColor }} />
        </span>
        <span className="text-xs font-bold text-white tracking-wide">丝滑连续播放</span>
        {fading && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-full animate-pulse"
            style={{ background: accentColor + '33', color: accentColor }}
          >
            ⇄ 过渡中
          </span>
        )}
        <span className="text-[10px] text-gray-500 ml-auto tabular-nums">
          {idx + 1} / {tracks.length}
        </span>
      </div>

      {/* Controls + current track */}
      <div className="px-4 py-3 flex items-center gap-3">
        <button
          onClick={() => skipTo(idx - 1)}
          disabled={idx === 0}
          className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" />
          </svg>
        </button>
        <button
          onClick={togglePlay}
          className="w-10 h-10 rounded-full flex items-center justify-center transition hover:scale-110 shadow-lg"
          style={{ background: accentColor }}
        >
          {playing ? (
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
              <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" />
            </svg>
          ) : (
            <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
        <button
          onClick={() => skipTo(idx + 1)}
          disabled={!nextTrack}
          className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1"
        >
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
          </svg>
        </button>

        <div className="flex-1 min-w-0 ml-1">
          <div className="text-sm text-white truncate font-medium">{track?.title}</div>
          <div className="text-[11px] text-gray-500 truncate">{track?.artist}</div>
        </div>

        {fading && nextTrack && (
          <div
            className="flex items-center gap-1 px-2 py-1 rounded-full text-[10px] shrink-0"
            style={{ background: accentColor + '22', color: accentColor }}
          >
            <span className="animate-pulse">→</span>
            <span className="truncate max-w-[72px]">{nextTrack.title}</span>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="px-4 pb-2 flex items-center gap-2">
        <span className="text-[10px] text-gray-500 w-8 text-right tabular-nums">{fmt(time)}</span>
        <div className="flex-1 h-1.5 bg-gray-700/60 rounded-full relative overflow-hidden">
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-300"
            style={{ width: `${pct}%`, background: accentColor }}
          />
          {fading && (
            <div
              className="absolute inset-y-0 right-0 rounded-full animate-pulse"
              style={{
                width: `${Math.min(100, (crossfadeSec / (dur || 1)) * 100)}%`,
                background: 'rgba(250,204,21,0.25)',
              }}
            />
          )}
        </div>
        <span className="text-[10px] text-gray-500 w-8 tabular-nums">{fmt(dur)}</span>
      </div>

      {/* Track list */}
      <div className="px-3 pb-3 max-h-40 overflow-y-auto">
        {tracks.map((t, i) => (
          <button
            key={`${t.songId}-${i}`}
            onClick={() => skipTo(i)}
            className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg text-left text-xs transition hover:bg-white/5 ${
              i === idx ? 'bg-white/10' : i < idx ? 'opacity-40' : ''
            }`}
          >
            <span
              className="w-5 text-center shrink-0 text-[11px]"
              style={i === idx ? { color: accentColor } : { color: '#6b7280' }}
            >
              {i === idx && playing ? '♫' : i + 1}
            </span>
            <span
              className="flex-1 truncate"
              style={i === idx ? { color: '#fff' } : { color: '#d1d5db' }}
            >
              {t.title}
            </span>
            <span className="text-gray-600 truncate max-w-[80px] shrink-0">{t.artist}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
