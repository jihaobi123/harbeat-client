import { useRef, useState, useEffect, useCallback } from 'react'
import { getProcessedStreamUrl } from '../api/client'
import type { TransitionAutomation } from '../types'

export interface SeamlessTrack {
  songId: number
  title: string
  artist: string
  filePath: string
  stemFiles?: Record<string, string>
  /** Segment: play from this time (seconds into the file) */
  playStart?: number
  /** Segment: stop at this time */
  playEnd?: number
  /** Transition automation for entering this track (from previous) */
  transitionIn?: TransitionAutomation | null
  /** Overlap duration in seconds for incoming transition */
  overlapSec?: number
}

interface Props {
  tracks: SeamlessTrack[]
  crossfadeSec?: number
  accentColor?: string
  onEnd?: () => void
}

const STEM_NAMES = ['drums', 'bass', 'vocals', 'other'] as const
type StemName = (typeof STEM_NAMES)[number]

const STEM_LABELS: Record<StemName, string> = {
  drums: '🥁 鼓', bass: '🎸 低音', vocals: '🎤 人声', other: '🎹 其他',
}
const STEM_COLORS: Record<StemName, string> = {
  drums: '#ef4444', bass: '#f59e0b', vocals: '#3b82f6', other: '#8b5cf6',
}

function fmt(sec: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/* ─── Slot: manages 4 stem audios or 1 mixed audio ─────────────────── */
function createSlot() {
  const stems: Record<StemName, HTMLAudioElement> = {
    drums: new Audio(), bass: new Audio(), vocals: new Audio(), other: new Audio(),
  }
  const mixed = new Audio()
  let isStem = false

  return {
    stems, mixed,
    get isStem() { return isStem },

    load(track: SeamlessTrack, onReady: () => void) {
      isStem = !!(track.stemFiles && Object.keys(track.stemFiles).length === 4)
      let ready = 0
      const needed = isStem ? 4 : 1
      const check = () => { if (++ready >= needed) onReady() }

      if (isStem) {
        mixed.removeAttribute('src'); mixed.load()
        for (const n of STEM_NAMES) {
          const a = stems[n]
          a.addEventListener('canplay', check, { once: true })
          a.src = getProcessedStreamUrl(track.stemFiles![n])
          a.load()
        }
      } else {
        for (const n of STEM_NAMES) { stems[n].removeAttribute('src'); stems[n].load() }
        mixed.addEventListener('canplay', check, { once: true })
        mixed.src = getProcessedStreamUrl(track.filePath)
        mixed.load()
      }
    },

    play() {
      if (isStem) { for (const n of STEM_NAMES) stems[n].play().catch(() => {}) }
      else mixed.play().catch(() => {})
    },

    pause() {
      if (isStem) { for (const n of STEM_NAMES) stems[n].pause() }
      else mixed.pause()
    },

    /** Set per-stem volumes (for DJ automation) */
    setStemVolumes(gains: Record<StemName, number>, master: number) {
      if (isStem) {
        for (const n of STEM_NAMES)
          stems[n].volume = Math.min(1, Math.max(0, gains[n] * master))
      } else {
        mixed.volume = Math.min(1, Math.max(0, master))
      }
    },

    seek(t: number) {
      if (isStem) {
        for (const n of STEM_NAMES) { if (isFinite(stems[n].duration)) stems[n].currentTime = t }
      } else {
        if (isFinite(mixed.duration)) mixed.currentTime = t
      }
    },

    get currentTime() { return isStem ? (stems.drums.currentTime || 0) : (mixed.currentTime || 0) },
    get duration() { return isStem ? (stems.drums.duration || 0) : (mixed.duration || 0) },

    onEnded(cb: () => void) {
      if (isStem) stems.drums.onended = cb
      else mixed.onended = cb
    },

    cleanup() {
      for (const n of STEM_NAMES) {
        const a = stems[n]; a.onended = null; a.pause(); a.removeAttribute('src'); a.load()
      }
      mixed.onended = null; mixed.pause(); mixed.removeAttribute('src'); mixed.load()
      isStem = false
    },
  }
}
type Slot = ReturnType<typeof createSlot>

/* ─── Automation sampler: reads per-stem gains from automation curves ── */
function sampleAutomation(
  auto: TransitionAutomation | null | undefined,
  elapsed: number,
  totalSec: number,
  side: 'a' | 'b',
): Record<StemName, number> & { volume: number } {
  const full = { drums: 1, bass: 1, vocals: 1, other: 1, volume: 1 }
  if (!auto || totalSec <= 0) return full

  const sr = auto.sample_rate || 10
  const idx = Math.min(
    Math.floor(elapsed * sr),
    (side === 'a' ? auto.a_volume.length : auto.b_volume.length) - 1
  )
  if (idx < 0) return full

  if (side === 'a') {
    return {
      drums: auto.a_drums[idx] ?? 1,
      bass: auto.a_bass[idx] ?? 1,
      vocals: auto.a_vocals[idx] ?? 1,
      other: auto.a_other[idx] ?? 1,
      volume: auto.a_volume[idx] ?? 1,
    }
  }
  return {
    drums: auto.b_drums[idx] ?? 1,
    bass: auto.b_bass[idx] ?? 1,
    vocals: auto.b_vocals[idx] ?? 1,
    other: auto.b_other[idx] ?? 1,
    volume: auto.b_volume[idx] ?? 1,
  }
}

/* ─── Component ──────────────────────────────────────────────────────── */
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
  const [seeking, setSeeking] = useState(false)
  const [stemGains, setStemGains] = useState<Record<StemName, number>>({
    drums: 1, bass: 1, vocals: 1, other: 1,
  })
  const [hasStemMode, setHasStemMode] = useState(false)
  const [showStems, setShowStems] = useState(false)

  const slotA = useRef<Slot | null>(null)
  const slotB = useRef<Slot | null>(null)

  const st = useRef({
    active: 'A' as 'A' | 'B',
    idx: 0,
    fading: false,
    playing: false,
    alive: false,
    raf: 0,
    fadeStartTime: 0,   // when the overlap started (A's currentTime)
  })

  const tracksR = useRef(tracks); tracksR.current = tracks
  const onEndR = useRef(onEnd); onEndR.current = onEnd
  const xfR = useRef(crossfadeSec); xfR.current = crossfadeSec
  const stemGainsR = useRef(stemGains); stemGainsR.current = stemGains
  const seekingR = useRef(false)
  const seekTimeR = useRef(0)
  const ctrlR = useRef<{ startTick: () => void }>({ startTick: () => {} })

  const ac = () => (st.current.active === 'A' ? slotA : slotB).current!
  const nx = () => (st.current.active === 'A' ? slotB : slotA).current!

  /** Get the effective play boundaries for a track */
  const getPlayBounds = (t: SeamlessTrack, slotDur: number) => {
    const start = t.playStart ?? 0
    const end = t.playEnd && t.playEnd > start ? t.playEnd : slotDur
    return { start, end, dur: Math.max(0, end - start) }
  }

  // ── Main effect ────────────────────────────────────────────────────────
  useEffect(() => {
    const r = st.current
    r.alive = true; r.active = 'A'; r.idx = 0; r.fading = false; r.playing = false
    setIdx(0); setTime(0); setDur(0); setFading(false)

    slotA.current = createSlot()
    slotB.current = createSlot()

    function tick() {
      if (!r.playing || !r.alive) return
      const a = ac()
      const curTrack = tracksR.current[r.idx]
      const ct = a.currentTime
      const slotDur = a.duration
      const { start: pStart, end: pEnd, dur: pDur } = getPlayBounds(curTrack, slotDur)

      if (isFinite(slotDur) && slotDur > 0) {
        // Display time relative to segment
        const displayT = ct - pStart
        if (!seekingR.current) { setTime(Math.max(0, displayT)); setDur(pDur) }

        const left = pEnd - ct
        const ni = r.idx + 1
        const nextTrack = ni < tracksR.current.length ? tracksR.current[ni] : null

        // Determine crossfade duration: use overlap from next track's transition, or default
        const xfDur = nextTrack?.overlapSec || xfR.current

        // ── Trigger crossfade when approaching segment end ──
        if (!r.fading && left <= xfDur && left > 0.05 && pDur > xfDur * 1.5 && nextTrack) {
          r.fading = true; r.fadeStartTime = ct; setFading(true)
          const n = nx()
          n.load(nextTrack, () => {
            if (!r.alive) return
            // Seek B to its segment start
            const bStart = nextTrack.playStart || 0
            n.seek(bStart)
            n.setStemVolumes({ drums: 0, bass: 0, vocals: 0, other: 0 }, 0)
            n.play()
            setHasStemMode(n.isStem)
          })
        }

        // ── Check if we've passed the segment end (no crossfade needed) ──
        if (!r.fading && ct >= pEnd) {
          _advanceTrack(r)
          return
        }

        // ── Apply automation during crossfade ──
        if (r.fading && nextTrack) {
          const elapsed = ct - r.fadeStartTime
          const xf = nextTrack.overlapSec || xfR.current
          const automation = nextTrack.transitionIn

          if (automation && ac().isStem) {
            // Serato-style per-stem automation
            const aGains = sampleAutomation(automation, elapsed, xf, 'a')
            const bGains = sampleAutomation(automation, elapsed, xf, 'b')

            // Apply user stem gains on top of automation
            const ug = stemGainsR.current
            a.setStemVolumes({
              drums: aGains.drums * ug.drums,
              bass: aGains.bass * ug.bass,
              vocals: aGains.vocals * ug.vocals,
              other: aGains.other * ug.other,
            }, aGains.volume)
            nx().setStemVolumes({
              drums: bGains.drums * ug.drums,
              bass: bGains.bass * ug.bass,
              vocals: bGains.vocals * ug.vocals,
              other: bGains.other * ug.other,
            }, bGains.volume)
          } else {
            // Fallback: simple equal-power crossfade
            const p = Math.max(0, Math.min(1, elapsed / xf))
            const aVol = Math.cos(p * Math.PI / 2)
            const bVol = Math.sin(p * Math.PI / 2)
            a.setStemVolumes(stemGainsR.current, aVol)
            nx().setStemVolumes(stemGainsR.current, bVol)
          }
        } else if (!r.fading) {
          a.setStemVolumes(stemGainsR.current, 1)
        }
      }
      r.raf = requestAnimationFrame(tick)
    }

    function _advanceTrack(r: typeof st.current) {
      const ni = r.idx + 1
      if (r.fading) {
        ac().pause(); ac().cleanup()
        r.active = r.active === 'A' ? 'B' : 'A'
        r.fading = false; setFading(false)
        r.idx = ni; setIdx(ni)
        const t = tracksR.current[ni]
        if (t) setHasStemMode(!!(t.stemFiles && Object.keys(t.stemFiles).length === 4))
        bindEnded(ac(), r.active)
      } else if (ni < tracksR.current.length) {
        r.idx = ni; setIdx(ni)
        const t = tracksR.current[ni]
        if (t) setHasStemMode(!!(t.stemFiles && Object.keys(t.stemFiles).length === 4))
        const slot = ac()
        slot.load(t, () => {
          if (!r.alive || r.idx !== ni) return
          const bStart = t.playStart || 0
          slot.seek(bStart)
          slot.setStemVolumes(stemGainsR.current, 1)
          slot.play()
          bindEnded(slot, r.active)
        })
      } else {
        r.playing = false; setPlaying(false)
        cancelAnimationFrame(r.raf)
        onEndR.current?.()
      }
    }

    function startTick() {
      cancelAnimationFrame(r.raf)
      if (r.playing && r.alive) r.raf = requestAnimationFrame(tick)
    }
    ctrlR.current = { startTick }

    function bindEnded(slot: Slot, which: 'A' | 'B') {
      slot.onEnded(() => {
        if (!r.alive || r.active !== which) return
        _advanceTrack(r)
      })
    }

    if (tracksR.current.length) {
      const firstTrack = tracksR.current[0]
      setHasStemMode(!!(firstTrack.stemFiles && Object.keys(firstTrack.stemFiles).length === 4))
      const a = slotA.current!
      a.load(firstTrack, () => {
        if (!r.alive) return
        // Seek to segment start
        const pStart = firstTrack.playStart || 0
        if (pStart > 0) a.seek(pStart)
        bindEnded(a, 'A')
        a.setStemVolumes(stemGainsR.current, 1)
        a.play()
        r.playing = true; setPlaying(true)
        startTick()
      })
    }

    return () => {
      r.alive = false; cancelAnimationFrame(r.raf)
      slotA.current?.cleanup(); slotB.current?.cleanup()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracks])

  // ── Controls ─────────────────────────────────────────────────────────
  const togglePlay = useCallback(() => {
    const r = st.current
    if (!r.alive) return
    if (r.playing) {
      ac().pause(); if (r.fading) nx().pause()
      r.playing = false; setPlaying(false); cancelAnimationFrame(r.raf)
    } else {
      ac().play(); if (r.fading) nx().play()
      r.playing = true; setPlaying(true); ctrlR.current.startTick()
    }
  }, [])

  const skipTo = useCallback((ti: number) => {
    const r = st.current
    if (ti < 0 || ti >= tracksR.current.length || !r.alive) return
    cancelAnimationFrame(r.raf)
    slotA.current?.pause(); slotB.current?.pause()
    slotA.current?.cleanup(); slotB.current?.cleanup()
    r.fading = false; setFading(false); r.active = 'A'; r.idx = ti; setIdx(ti)

    slotA.current = createSlot()
    slotB.current = createSlot()

    const t = tracksR.current[ti]
    setHasStemMode(!!(t.stemFiles && Object.keys(t.stemFiles).length === 4))
    const a = slotA.current!
    a.load(t, () => {
      if (!r.alive || r.idx !== ti) return
      const pStart = t.playStart || 0
      if (pStart > 0) a.seek(pStart)
      a.onEnded(() => { if (r.active === 'A' && r.alive) _triggerAdvance() })
      slotB.current!.onEnded(() => { if (r.active === 'B' && r.alive) _triggerAdvance() })
      a.setStemVolumes(stemGainsR.current, 1)
      a.play()
      r.playing = true; setPlaying(true); ctrlR.current.startTick()
    })
  }, [])

  const _triggerAdvance = useCallback(() => {
    const r = st.current
    const ni = r.idx + 1
    if (r.fading) {
      ac().pause(); ac().cleanup()
      r.active = r.active === 'A' ? 'B' : 'A'
      r.fading = false; setFading(false)
      r.idx = ni; setIdx(ni)
    } else if (ni < tracksR.current.length) {
      skipTo(ni)
    } else {
      r.playing = false; setPlaying(false); cancelAnimationFrame(r.raf); onEndR.current?.()
    }
  }, [])

  // ── Seek ──────────────────────────────────────────────────────────────
  const handleSeekInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    seekingR.current = true; setSeeking(true)
    const v = parseFloat(e.target.value)
    seekTimeR.current = v; setTime(v)
  }, [])

  const handleSeekCommit = useCallback(() => {
    // Offset by segment start
    const t = tracksR.current[st.current.idx]
    const offset = t?.playStart || 0
    ac().seek(seekTimeR.current + offset)
    seekingR.current = false; setSeeking(false)
  }, [])

  // ── Stem volume ──────────────────────────────────────────────────────
  const handleStemGain = useCallback((name: StemName, val: number) => {
    setStemGains(prev => {
      const next = { ...prev, [name]: val }
      stemGainsR.current = next
      return next
    })
  }, [])

  // ── Derived ──────────────────────────────────────────────────────────
  const track = tracks[idx]
  const nextTrack = idx + 1 < tracks.length ? tracks[idx + 1] : null
  const pct = dur > 0 ? (time / dur) * 100 : 0
  const displayTime = seeking ? seekTimeR.current : time

  if (!tracks.length) return null

  return (
    <div className="bg-gradient-to-b from-surface-light to-surface rounded-xl border border-gray-700/50 overflow-hidden shadow-xl">
      {/* Header */}
      <div className="px-4 py-2.5 flex items-center gap-2 border-b border-gray-700/50">
        <span className="relative flex h-2.5 w-2.5">
          {playing && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75"
              style={{ background: accentColor }} />
          )}
          <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: accentColor }} />
        </span>
        <span className="text-xs font-bold text-white tracking-wide">丝滑连续播放</span>
        {fading && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full animate-pulse"
            style={{ background: accentColor + '33', color: accentColor }}>⇄ 过渡中</span>
        )}
        {hasStemMode && (
          <button onClick={() => setShowStems(s => !s)}
            className="text-[10px] px-1.5 py-0.5 rounded-full transition"
            style={{
              background: showStems ? accentColor + '33' : 'transparent',
              color: showStems ? accentColor : '#6b7280',
              border: `1px solid ${showStems ? accentColor : '#374151'}`,
            }}>🎚 轨道</button>
        )}
        <span className="text-[10px] text-gray-500 ml-auto tabular-nums">{idx + 1} / {tracks.length}</span>
      </div>

      {/* Controls + current track */}
      <div className="px-4 py-3 flex items-center gap-3">
        <button onClick={() => skipTo(idx - 1)} disabled={idx === 0}
          className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" /></svg>
        </button>
        <button onClick={togglePlay}
          className="w-10 h-10 rounded-full flex items-center justify-center transition hover:scale-110 shadow-lg"
          style={{ background: accentColor }}>
          {playing ? (
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
          ) : (
            <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>
        <button onClick={() => skipTo(idx + 1)} disabled={!nextTrack}
          className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" /></svg>
        </button>
        <div className="flex-1 min-w-0 ml-1">
          <div className="text-sm text-white truncate font-medium">{track?.title}</div>
          <div className="text-[11px] text-gray-500 truncate">{track?.artist}</div>
        </div>
        {fading && nextTrack && (
          <div className="flex items-center gap-1 px-2 py-1 rounded-full text-[10px] shrink-0"
            style={{ background: accentColor + '22', color: accentColor }}>
            <span className="animate-pulse">→</span>
            <span className="truncate max-w-[72px]">{nextTrack.title}</span>
          </div>
        )}
      </div>

      {/* Seekable progress bar */}
      <div className="px-4 pb-2 flex items-center gap-2">
        <span className="text-[10px] text-gray-500 w-8 text-right tabular-nums">{fmt(displayTime)}</span>
        <div className="flex-1 relative h-4 group flex items-center">
          <div className="absolute inset-x-0 h-1.5 bg-gray-700/60 rounded-full top-1/2 -translate-y-1/2" />
          <div className="absolute h-1.5 rounded-full top-1/2 -translate-y-1/2 left-0"
            style={{ width: `${pct}%`, background: accentColor }} />
          {fading && (
            <div className="absolute h-1.5 rounded-full top-1/2 -translate-y-1/2 right-0 animate-pulse"
              style={{ width: `${Math.min(100, (crossfadeSec / (dur || 1)) * 100)}%`, background: 'rgba(250,204,21,0.25)' }} />
          )}
          <input type="range" min={0} max={dur || 0} step={0.1} value={displayTime}
            onChange={handleSeekInput}
            onMouseDown={() => { seekingR.current = true; setSeeking(true) }}
            onMouseUp={handleSeekCommit}
            onTouchStart={() => { seekingR.current = true; setSeeking(true) }}
            onTouchEnd={handleSeekCommit}
            className="absolute inset-0 w-full opacity-0 cursor-pointer z-10" />
          <div className="absolute w-3 h-3 rounded-full shadow-md top-1/2 -translate-y-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition pointer-events-none"
            style={{ left: `${pct}%`, background: accentColor }} />
        </div>
        <span className="text-[10px] text-gray-500 w-8 tabular-nums">{fmt(dur)}</span>
      </div>

      {/* Stem volume controls */}
      {showStems && hasStemMode && (
        <div className="px-4 pb-3 space-y-1.5">
          <div className="text-[10px] text-gray-500 mb-1">🎚 四轨音量控制</div>
          {STEM_NAMES.map(name => (
            <div key={name} className="flex items-center gap-2">
              <span className="text-[10px] w-14 shrink-0 font-medium" style={{ color: STEM_COLORS[name] }}>
                {STEM_LABELS[name]}
              </span>
              <div className="flex-1 relative h-3 flex items-center group">
                <div className="absolute inset-x-0 h-1 rounded-full top-1/2 -translate-y-1/2"
                  style={{ background: STEM_COLORS[name] + '33' }} />
                <div className="absolute h-1 rounded-full top-1/2 -translate-y-1/2 left-0"
                  style={{ width: `${Math.min(100, stemGains[name] / 1.5 * 100)}%`, background: STEM_COLORS[name] }} />
                <input type="range" min={0} max={1.5} step={0.01} value={stemGains[name]}
                  onChange={e => handleStemGain(name, parseFloat(e.target.value))}
                  className="absolute inset-0 w-full opacity-0 cursor-pointer z-10" />
              </div>
              <span className="text-[10px] text-gray-500 w-8 text-right tabular-nums">
                {Math.round(stemGains[name] * 100)}%
              </span>
              <button onClick={() => handleStemGain(name, stemGains[name] > 0.01 ? 0 : 1)}
                className="text-[10px] px-1 py-0.5 rounded transition"
                style={{ color: stemGains[name] > 0.01 ? STEM_COLORS[name] : '#4b5563',
                  background: stemGains[name] > 0.01 ? STEM_COLORS[name] + '15' : '#1f2937' }}>
                {stemGains[name] > 0.01 ? '🔊' : '🔇'}
              </button>
            </div>
          ))}
          <button onClick={() => { setStemGains({ drums: 1, bass: 1, vocals: 1, other: 1 }); stemGainsR.current = { drums: 1, bass: 1, vocals: 1, other: 1 } }}
            className="text-[10px] text-gray-500 hover:text-gray-300 transition mt-1">↩ 重置全部</button>
        </div>
      )}

      {/* Track list */}
      <div className="px-3 pb-3 max-h-40 overflow-y-auto">
        {tracks.map((t, i) => (
          <button key={`${t.songId}-${i}`} onClick={() => skipTo(i)}
            className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg text-left text-xs transition hover:bg-white/5 ${
              i === idx ? 'bg-white/10' : i < idx ? 'opacity-40' : ''}`}>
            <span className="w-5 text-center shrink-0 text-[11px]"
              style={i === idx ? { color: accentColor } : { color: '#6b7280' }}>
              {i === idx && playing ? '♫' : i + 1}
            </span>
            <span className="flex-1 truncate" style={i === idx ? { color: '#fff' } : { color: '#d1d5db' }}>
              {t.title}
            </span>
            <span className="text-gray-600 truncate max-w-[80px] shrink-0">{t.artist}</span>
            {t.stemFiles && Object.keys(t.stemFiles).length === 4 && (
              <span className="text-[9px] text-gray-600">4T</span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
