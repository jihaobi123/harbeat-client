import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import type { DjTransitionPlanItem } from '../types'
import { getProcessedStreamUrl } from '../api/client'

export interface SeamlessTrack {
  songId: number
  title: string
  artist: string
  filePath: string
  bpm?: number | null
  duration?: number | null
}

interface Props {
  tracks: SeamlessTrack[]
  crossfadeSec?: number
  accentColor?: string
  transitionPlan?: DjTransitionPlanItem[]
  onEnd?: () => void
}

interface DeckNodes {
  source: MediaElementAudioSourceNode
  highpass: BiquadFilterNode
  lowpass: BiquadFilterNode
  eqLow: BiquadFilterNode
  eqMid: BiquadFilterNode
  eqHigh: BiquadFilterNode
  fxGain: GainNode
  gain: GainNode
}

function fmt(sec: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function dbToGain(db: number): number {
  return Math.pow(10, db / 20)
}

function setPitchLock(audio: HTMLAudioElement, enabled: boolean) {
  const media = audio as HTMLAudioElement & {
    preservesPitch?: boolean
    mozPreservesPitch?: boolean
    webkitPreservesPitch?: boolean
  }
  media.preservesPitch = enabled
  media.mozPreservesPitch = enabled
  media.webkitPreservesPitch = enabled
}

function modPositive(x: number, m: number): number {
  if (!isFinite(x) || !isFinite(m) || m <= 0) return 0
  const r = x % m
  return r < 0 ? r + m : r
}

function mediaDuration(audio: HTMLAudioElement | null, fallback = 0): number {
  if (!audio) return fallback
  if (isFinite(audio.duration) && audio.duration > 0) return audio.duration
  try {
    if (audio.seekable.length > 0) {
      const end = audio.seekable.end(audio.seekable.length - 1)
      if (isFinite(end) && end > 0) return end
    }
  } catch {
    // ignore
  }
  return fallback
}

export default function SeamlessPlayer({
  tracks,
  crossfadeSec = 4,
  accentColor = '#8b5cf6',
  transitionPlan,
  onEnd,
}: Props) {
  const [playing, setPlaying] = useState(false)
  const [idx, setIdx] = useState(0)
  const [time, setTime] = useState(0)
  const [dur, setDur] = useState(0)
  const [fading, setFading] = useState(false)
  const [crossfadeAmount, setCrossfadeAmount] = useState(1)
  const [tempoSync, setTempoSync] = useState(true)
  const [keyLock, setKeyLock] = useState(true)
  const [seeking, setSeeking] = useState(false)
  const [seekValue, setSeekValue] = useState(0)
  const [nextMixInSec, setNextMixInSec] = useState<number | null>(null)

  const audioA = useRef<HTMLAudioElement | null>(null)
  const audioB = useRef<HTMLAudioElement | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const nodesA = useRef<DeckNodes | null>(null)
  const nodesB = useRef<DeckNodes | null>(null)
  const tickFnRef = useRef<() => void>(() => {})
  const seekingRef = useRef(false)
  seekingRef.current = seeking

  const st = useRef({
    slot: 'A' as 'A' | 'B',
    idx: 0,
    fading: false,
    playing: false,
    alive: false,
    raf: 0,
    transitionStartSec: 0,
    transitionDurationSec: 0,
    transitionTimer: 0 as ReturnType<typeof window.setTimeout> | 0,
    preloadedNextIdx: -1,
  })

  const tracksR = useRef(tracks)
  tracksR.current = tracks
  const onEndR = useRef(onEnd)
  onEndR.current = onEnd

  const transitionByIndex = useMemo(() => {
    const map = new Map<number, DjTransitionPlanItem>()
    transitionPlan?.forEach((item, i) => {
      map.set(i, item)
    })
    return map
  }, [transitionPlan])

  const ac = () => (st.current.slot === 'A' ? audioA.current : audioB.current)
  const nx = () => (st.current.slot === 'A' ? audioB.current : audioA.current)
  const acNodes = () => (st.current.slot === 'A' ? nodesA.current : nodesB.current)
  const nxNodes = () => (st.current.slot === 'A' ? nodesB.current : nodesA.current)
  const clearTransitionTimer = () => {
    const timer = st.current.transitionTimer
    if (timer) {
      window.clearTimeout(timer)
      st.current.transitionTimer = 0
    }
  }
  const getDisplayDeck = () => {
    const active = ac()
    if (!active) return null
    if (!st.current.fading) return active
    const incoming = nx()
    if (!incoming) return active
    const xf = Math.max(0.001, st.current.transitionDurationSec || 0.001)
    const progress = Math.max(0, Math.min(1, (active.currentTime - st.current.transitionStartSec) / xf))
    return progress >= 0.5 ? incoming : active
  }
  const getTrackDuration = (track: SeamlessTrack | undefined): number =>
    track?.duration && isFinite(track.duration) && track.duration > 0 ? track.duration : 0

  const ensureAudioContext = () => {
    if (!ctxRef.current) {
      const Ctx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctx) return null
      ctxRef.current = new Ctx()
    }
    return ctxRef.current
  }

  const connectDeck = (ctx: AudioContext, audio: HTMLAudioElement): DeckNodes => {
    const source = ctx.createMediaElementSource(audio)
    const highpass = ctx.createBiquadFilter()
    highpass.type = 'highpass'
    highpass.frequency.value = 30

    const lowpass = ctx.createBiquadFilter()
    lowpass.type = 'lowpass'
    lowpass.frequency.value = 18000

    const eqLow = ctx.createBiquadFilter()
    eqLow.type = 'lowshelf'
    eqLow.frequency.value = 180
    eqLow.gain.value = 0

    const eqMid = ctx.createBiquadFilter()
    eqMid.type = 'peaking'
    eqMid.frequency.value = 1200
    eqMid.Q.value = 1
    eqMid.gain.value = 0

    const eqHigh = ctx.createBiquadFilter()
    eqHigh.type = 'highshelf'
    eqHigh.frequency.value = 6000
    eqHigh.gain.value = 0

    const fxGain = ctx.createGain()
    fxGain.gain.value = 1
    const gain = ctx.createGain()
    gain.gain.value = 1

    source.connect(highpass)
    highpass.connect(lowpass)
    lowpass.connect(eqLow)
    eqLow.connect(eqMid)
    eqMid.connect(eqHigh)
    eqHigh.connect(fxGain)
    fxGain.connect(gain)
    gain.connect(ctx.destination)

    return { source, highpass, lowpass, eqLow, eqMid, eqHigh, fxGain, gain }
  }

  const resetDeckNodes = (nodes: DeckNodes | null, at: number, gain = 1) => {
    if (!nodes) return
    nodes.gain.gain.cancelScheduledValues(at)
    nodes.gain.gain.setValueAtTime(gain, at)

    nodes.fxGain.gain.cancelScheduledValues(at)
    nodes.fxGain.gain.setValueAtTime(1, at)

    nodes.lowpass.frequency.cancelScheduledValues(at)
    nodes.lowpass.frequency.setValueAtTime(18000, at)

    nodes.highpass.frequency.cancelScheduledValues(at)
    nodes.highpass.frequency.setValueAtTime(30, at)

    nodes.eqLow.gain.cancelScheduledValues(at)
    nodes.eqLow.gain.setValueAtTime(0, at)

    nodes.eqMid.gain.cancelScheduledValues(at)
    nodes.eqMid.gain.setValueAtTime(0, at)

    nodes.eqHigh.gain.cancelScheduledValues(at)
    nodes.eqHigh.gain.setValueAtTime(0, at)
  }

  const scheduleTransitionAutomation = (fromNodes: DeckNodes, toNodes: DeckNodes, plan: DjTransitionPlanItem | undefined, xfSec: number) => {
    const ctx = ensureAudioContext()
    if (!ctx) return
    const now = ctx.currentTime

    resetDeckNodes(fromNodes, now, 1)
    resetDeckNodes(toNodes, now, 0.0001)

    fromNodes.gain.gain.linearRampToValueAtTime(0.0001, now + xfSec)
    toNodes.gain.gain.linearRampToValueAtTime(1.0, now + xfSec)

    if (!plan || !plan.fx_automation.length) {
      return
    }

    for (const point of plan.fx_automation) {
      const t = now + Math.max(0, Math.min(xfSec, point.time_sec))
      const targetNodes = point.target === 'from' ? fromNodes : toNodes
      targetNodes.fxGain.gain.linearRampToValueAtTime(dbToGain(point.gain_db), t)
      targetNodes.lowpass.frequency.linearRampToValueAtTime(point.lowpass_hz, t)
      targetNodes.highpass.frequency.linearRampToValueAtTime(point.highpass_hz, t)
      targetNodes.eqLow.gain.linearRampToValueAtTime(point.eq_low_db, t)
      targetNodes.eqMid.gain.linearRampToValueAtTime(point.eq_mid_db, t)
      targetNodes.eqHigh.gain.linearRampToValueAtTime(point.eq_high_db, t)
    }
  }

  useEffect(() => {
    const r = st.current
    r.alive = true
    r.slot = 'A'
    r.idx = 0
    r.fading = false
    r.playing = false
    r.transitionStartSec = 0
    r.transitionDurationSec = 0
    r.transitionTimer = 0
    r.preloadedNextIdx = -1

    setIdx(0)
    setTime(0)
    setSeekValue(0)
    setDur(0)
    setFading(false)
    setPlaying(false)
    setSeeking(false)
    setNextMixInSec(null)

    const a = new Audio()
    const b = new Audio()
    a.preload = 'auto'
    b.preload = 'auto'
    audioA.current = a
    audioB.current = b

    const ctx = ensureAudioContext()
    if (ctx) {
      nodesA.current = connectDeck(ctx, a)
      nodesB.current = connectDeck(ctx, b)
      resetDeckNodes(nodesA.current, ctx.currentTime, 1)
      resetDeckNodes(nodesB.current, ctx.currentTime, 0.0001)
    }

    function completeTransition() {
      clearTransitionTimer()
      const out = ac()
      const incoming = nx()
      if (out) {
        out.pause()
        out.src = ''
      }
      r.slot = r.slot === 'A' ? 'B' : 'A'
      r.fading = false
      setFading(false)
      setNextMixInSec(null)
      r.idx += 1
      setIdx(r.idx)
      r.transitionStartSec = 0
      r.transitionDurationSec = 0

      const ctxNow = ctxRef.current?.currentTime
      if (ctxNow != null) {
        resetDeckNodes(acNodes(), ctxNow, 1)
        resetDeckNodes(nxNodes(), ctxNow, 0.0001)
      }

      if (incoming && isFinite(incoming.duration) && incoming.duration > 0) {
        setTime(incoming.currentTime)
        setSeekValue(incoming.currentTime)
        setDur(incoming.duration)
      }
      r.preloadedNextIdx = -1
    }

    function primeNextTrack(nextTrack: SeamlessTrack | undefined, nextIndex: number) {
      if (!nextTrack || r.fading || nextIndex < 0) return
      if (r.preloadedNextIdx === nextIndex) return
      const nextDeck = nx()
      if (!nextDeck) return
      const nextSrc = getProcessedStreamUrl(nextTrack.filePath)
      if (nextDeck.getAttribute('src') !== nextSrc) {
        nextDeck.src = nextSrc
        nextDeck.preload = 'auto'
        nextDeck.load()
      }
      r.preloadedNextIdx = nextIndex
    }

    function getTransitionTriggerSec(
      active: HTMLAudioElement,
      activeTrack: SeamlessTrack | undefined,
      nextTrack: SeamlessTrack | undefined,
    ): number | null {
      if (!activeTrack || !nextTrack) return null
      const plan = transitionByIndex.get(r.idx)
      const base = Math.max(1, plan?.crossfade_sec ?? crossfadeSec)
      const xf = Math.min(20, Math.max(1, base * crossfadeAmount))
      const activeDuration = mediaDuration(active, getTrackDuration(activeTrack))
      const earlyFallback = activeDuration > 0 ? Math.max(0, activeDuration - Math.max(xf, 12)) : null

      if (plan) {
        const plannedExitSec = typeof plan.exit_time_sec === 'number' && plan.exit_time_sec > 0
          ? plan.exit_time_sec
          : (activeTrack.bpm && activeTrack.bpm > 0 ? (plan.exit_beat * 60) / activeTrack.bpm : undefined)
        if (plannedExitSec != null) {
          const plannedTrigger = Math.max(0, plannedExitSec - xf)
          return earlyFallback != null ? Math.min(plannedTrigger, earlyFallback) : plannedTrigger
        }
      }

      if (activeDuration > 0) {
        return Math.max(0, activeDuration - Math.max(xf, 12))
      }
      return null
    }

    function getTransitionCountdown(
      active: HTMLAudioElement,
      activeTrack: SeamlessTrack | undefined,
      nextTrack: SeamlessTrack | undefined,
    ): number | null {
      if (!activeTrack || !nextTrack || r.fading) return null
      const triggerSec = getTransitionTriggerSec(active, activeTrack, nextTrack)
      if (triggerSec == null) return null
      const remain = triggerSec - active.currentTime
      if (!isFinite(remain)) return null
      return Math.max(0, remain)
    }

    function tryTriggerTransition(active: HTMLAudioElement, activeTrack: SeamlessTrack, nextTrack: SeamlessTrack | undefined) {
      if (!nextTrack || r.fading) return

      const plan = transitionByIndex.get(r.idx)
      const base = Math.max(1, plan?.crossfade_sec ?? crossfadeSec)
      const xf = Math.min(20, Math.max(1, base * crossfadeAmount))
      const activeDuration = mediaDuration(active, getTrackDuration(activeTrack))
      const left = activeDuration > 0 ? (activeDuration - active.currentTime) : Number.POSITIVE_INFINITY

      const triggerSec = getTransitionTriggerSec(active, activeTrack, nextTrack)
      let shouldStart = triggerSec != null
        ? active.currentTime >= triggerSec
        : (activeDuration > 0 ? left <= xf : false)
      if (activeDuration > 0 && active.currentTime >= Math.max(0, activeDuration - 0.35)) {
        shouldStart = true
      }

      if (!shouldStart || (activeDuration > 0 && left <= 0.05)) return

      r.fading = true
      r.transitionStartSec = active.currentTime
      r.transitionDurationSec = xf
      setFading(true)
      setNextMixInSec(null)
      r.preloadedNextIdx = -1

      const next = nx()
      if (!next) {
        r.fading = false
        setFading(false)
        return
      }

      const nextSrc = getProcessedStreamUrl(nextTrack.filePath)
      if (next.getAttribute('src') !== nextSrc) {
        next.src = nextSrc
      }
      const tempoRatio = tempoSync && plan && plan.tempo_ratio > 0 ? plan.tempo_ratio : 1
      next.playbackRate = tempoRatio
      setPitchLock(next, keyLock)

      const onReady = () => {
        next.removeEventListener('canplay', onReady)
        next.removeEventListener('error', onError)
        if (!r.alive) return

        if (plan) {
          const entryTime = typeof plan.entry_time_sec === 'number' ? plan.entry_time_sec : 0
          const fromInterval = typeof plan.from_beat_interval_sec === 'number' && plan.from_beat_interval_sec > 0
            ? plan.from_beat_interval_sec
            : (activeTrack.bpm && activeTrack.bpm > 0 ? 60 / activeTrack.bpm : 0.5)
          const toIntervalBase = typeof plan.to_beat_interval_sec === 'number' && plan.to_beat_interval_sec > 0
            ? plan.to_beat_interval_sec
            : (nextTrack.bpm && nextTrack.bpm > 0 ? 60 / nextTrack.bpm : 0.5)
          const toInterval = toIntervalBase / Math.max(tempoRatio, 1e-6)
          const anchorSec = typeof plan.phase_anchor_sec === 'number'
            ? plan.phase_anchor_sec
            : Math.max(0, active.currentTime)

          const phaseFromSec = modPositive(active.currentTime - anchorSec, fromInterval)
          const phaseFraction = fromInterval > 0 ? (phaseFromSec / fromInterval) : 0
          const entryOffset = phaseFraction * toInterval
          const phaseLockedStart = Math.max(0, entryTime + entryOffset)
          const nextDuration = mediaDuration(next, getTrackDuration(nextTrack))
          const safeStart = nextDuration > 0
            ? Math.min(Math.max(0, nextDuration - 0.1), phaseLockedStart)
            : phaseLockedStart
          next.currentTime = safeStart
        } else {
          next.currentTime = 0
        }

        const fromNodes = acNodes()
        const toNodes = nxNodes()
        if (fromNodes && toNodes) {
          scheduleTransitionAutomation(fromNodes, toNodes, plan, xf)
        }

        next.play().catch(() => {})

        clearTransitionTimer()
        r.transitionTimer = window.setTimeout(() => {
          if (!r.alive || !r.fading) return
          completeTransition()
        }, Math.max(120, xf * 1000 + 80))
      }

      const onError = () => {
        next.removeEventListener('canplay', onReady)
        next.removeEventListener('error', onError)
        clearTransitionTimer()
        r.fading = false
        setFading(false)
      }

      if (next.readyState >= 2) {
        onReady()
      } else {
        next.addEventListener('canplay', onReady)
        next.addEventListener('error', onError)
        next.load()
      }
    }

    function tick() {
      if (!r.playing || !r.alive) return
      const active = ac()
      if (active) {
        const currentTrack = tracksR.current[r.idx]
        const nextTrack = tracksR.current[r.idx + 1]
        primeNextTrack(nextTrack, r.idx + 1)

        const display = getDisplayDeck()
        const displayDuration = display
          ? mediaDuration(display, display === nx() ? getTrackDuration(nextTrack) : getTrackDuration(currentTrack))
          : 0
        if (display && !seekingRef.current) {
          setTime(display.currentTime)
          setSeekValue(display.currentTime)
          if (displayDuration > 0) {
            setDur(displayDuration)
          }
        }
        const countdown = getTransitionCountdown(active, currentTrack, nextTrack)
        setNextMixInSec(countdown)
        if (currentTrack) {
          tryTriggerTransition(active, currentTrack, nextTrack)
        }
      }
      r.raf = requestAnimationFrame(tick)
    }
    tickFnRef.current = tick

    function doEnded() {
      if (!r.alive) return
      if (r.fading) {
        completeTransition()
      } else {
        const ni = r.idx + 1
        if (ni < tracksR.current.length) {
          r.idx = ni
          r.preloadedNextIdx = -1
          setNextMixInSec(null)
          setIdx(ni)
          const c = ac()
          if (!c) return
          c.src = getProcessedStreamUrl(tracksR.current[ni].filePath)
          c.playbackRate = 1
          setPitchLock(c, keyLock)
          const onReady = () => {
            c.removeEventListener('canplay', onReady)
            if (r.alive && r.idx === ni) c.play().catch(() => {})
          }
          c.addEventListener('canplay', onReady)
          c.load()
        } else {
          r.playing = false
          setPlaying(false)
          setNextMixInSec(null)
          cancelAnimationFrame(r.raf)
          onEndR.current?.()
        }
      }
    }

    a.onended = () => {
      if (r.slot === 'A') doEnded()
    }
    b.onended = () => {
      if (r.slot === 'B') doEnded()
    }
    a.onerror = () => {
      if (r.slot === 'A' && r.alive) doEnded()
    }
    b.onerror = () => {
      if (r.slot === 'B' && r.alive) doEnded()
    }

    if (tracksR.current.length) {
      a.src = getProcessedStreamUrl(tracksR.current[0].filePath)
      a.playbackRate = 1
      setPitchLock(a, keyLock)
      a.load()
    }

    return () => {
      r.alive = false
      clearTransitionTimer()
      cancelAnimationFrame(r.raf)
      tickFnRef.current = () => {}
      a.onended = null
      b.onended = null
      a.onerror = null
      b.onerror = null
      a.pause()
      b.pause()
      a.src = ''
      b.src = ''
      nodesA.current = null
      nodesB.current = null
    }
  }, [tracks, transitionByIndex, crossfadeAmount, crossfadeSec, tempoSync, keyLock])

  const togglePlay = async () => {
    const r = st.current
    if (!r.alive) return
    const ctx = ensureAudioContext()
    if (ctx && ctx.state === 'suspended') {
      await ctx.resume().catch(() => {})
    }

    if (r.playing) {
      ac()?.pause()
      if (r.fading) nx()?.pause()
      r.playing = false
      setPlaying(false)
      setNextMixInSec(null)
      cancelAnimationFrame(r.raf)
      return
    }

    const current = ac()
    if (current) {
      setPitchLock(current, keyLock)
    }
    ac()?.play().catch(() => {})
    if (r.fading) nx()?.play().catch(() => {})
    r.playing = true
    setPlaying(true)
    cancelAnimationFrame(r.raf)
    r.raf = requestAnimationFrame(() => tickFnRef.current())
  }

  const skipTo = (ti: number) => {
    const r = st.current
    if (ti < 0 || ti >= tracksR.current.length || !r.alive) return

    clearTransitionTimer()
    cancelAnimationFrame(r.raf)
    audioA.current?.pause()
    audioB.current?.pause()

    r.fading = false
    r.slot = 'A'
    r.idx = ti
    r.preloadedNextIdx = -1
    setFading(false)
    setNextMixInSec(null)
    setIdx(ti)
    setTime(0)
    setSeekValue(0)

    const ctxNow = ctxRef.current?.currentTime
    if (ctxNow != null) {
      resetDeckNodes(nodesA.current, ctxNow, 1)
      resetDeckNodes(nodesB.current, ctxNow, 0.0001)
    }

    const a = audioA.current
    if (!a) return

    a.src = getProcessedStreamUrl(tracksR.current[ti].filePath)
    a.playbackRate = 1
    setPitchLock(a, keyLock)
    const onReady = () => {
      a.removeEventListener('canplay', onReady)
      if (!r.alive || r.idx !== ti) return
      if (!r.playing) return
      a.play().catch(() => {})
      cancelAnimationFrame(r.raf)
      r.raf = requestAnimationFrame(() => tickFnRef.current())
    }
    a.addEventListener('canplay', onReady)
    a.load()
  }

  const emergencyCut = () => {
    const r = st.current
    if (!r.fading) return
    clearTransitionTimer()
    const out = ac()
    const incoming = nx()
    if (!incoming) return

    out?.pause()
    if (out) out.src = ''
    incoming.currentTime = Math.max(0, incoming.currentTime)

    r.slot = r.slot === 'A' ? 'B' : 'A'
    r.fading = false
    r.preloadedNextIdx = -1
    setFading(false)
    setNextMixInSec(null)
    r.idx += 1
    setIdx(r.idx)

    const now = ctxRef.current?.currentTime
    if (now != null) {
      resetDeckNodes(acNodes(), now, 1)
      resetDeckNodes(nxNodes(), now, 0.0001)
    }
  }

  const beginSeek = () => {
    setSeeking(true)
  }

  const handleSeekChange = (e: ChangeEvent<HTMLInputElement>) => {
    const value = parseFloat(e.target.value)
    if (!isFinite(value)) return
    if (!seeking) setSeeking(true)
    setSeekValue(value)
  }

  const commitSeek = () => {
    const target = seekValue
    const deck = getDisplayDeck()
    if (deck && isFinite(target)) {
      const currentTrack = tracksR.current[st.current.idx]
      const nextTrack = tracksR.current[st.current.idx + 1]
      const fallback = deck === nx() ? getTrackDuration(nextTrack) : getTrackDuration(currentTrack)
      const md = mediaDuration(deck, fallback)
      const max = md > 0 ? Math.max(0, md - 0.05) : target
      const nextTime = Math.max(0, Math.min(target, max))
      deck.currentTime = nextTime
      setTime(nextTime)
      setSeekValue(nextTime)
      if (md > 0) {
        setDur(md)
      }
      if (st.current.playing) {
        cancelAnimationFrame(st.current.raf)
        st.current.raf = requestAnimationFrame(() => tickFnRef.current())
      }
    }
    setSeeking(false)
  }

  const track = tracks[idx]
  const nextTrack = idx + 1 < tracks.length ? tracks[idx + 1] : null
  const shownTime = seeking ? seekValue : time
  const pct = dur > 0 ? (shownTime / dur) * 100 : 0

  if (!tracks.length) return null

  return (
    <div className="bg-gradient-to-b from-surface-light to-surface rounded-xl border border-gray-700/50 overflow-hidden shadow-xl">
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
        <span className="text-xs font-bold text-white tracking-wide">DJ Seamless Mix</span>
        {fading && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full animate-pulse" style={{ background: `${accentColor}33`, color: accentColor }}>
            Transition
          </span>
        )}
        {!fading && playing && nextTrack && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: '#f59e0b22', color: '#f59e0b' }}>
            {nextMixInSec != null ? `Next mix in ${nextMixInSec.toFixed(1)}s` : 'Next mix arming...'}
          </span>
        )}
        <span className="text-[10px] text-gray-500 ml-auto tabular-nums">
          {idx + 1} / {tracks.length}
        </span>
      </div>

      <div className="px-4 py-3 flex items-center gap-3">
        <button onClick={() => skipTo(idx - 1)} disabled={idx === 0} className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" /></svg>
        </button>
        <button onClick={togglePlay} className="w-10 h-10 rounded-full flex items-center justify-center transition hover:scale-110 shadow-lg" style={{ background: accentColor }}>
          {playing ? (
            <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
          ) : (
            <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          )}
        </button>
        <button onClick={() => skipTo(idx + 1)} disabled={!nextTrack} className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" /></svg>
        </button>

        <div className="flex-1 min-w-0 ml-1">
          <div className="text-sm text-white truncate font-medium">{track?.title}</div>
          <div className="text-[11px] text-gray-500 truncate">{track?.artist}</div>
        </div>

        {fading && nextTrack && (
          <div className="flex items-center gap-1 px-2 py-1 rounded-full text-[10px] shrink-0" style={{ background: `${accentColor}22`, color: accentColor }}>
            <span className="animate-pulse">��</span>
            <span className="truncate max-w-[72px]">{nextTrack.title}</span>
          </div>
        )}
      </div>

      <div className="px-4 pb-2 flex items-center gap-2">
        <span className="text-[10px] text-gray-500 w-8 text-right tabular-nums">{fmt(shownTime)}</span>
        <div className="flex-1 h-2 relative">
          <div className="absolute inset-0 bg-gray-700/60 rounded-full overflow-hidden">
            <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-200" style={{ width: `${pct}%`, background: accentColor }} />
          </div>
          <input
            type="range"
            min={0}
            max={dur || 0}
            step={0.05}
            value={shownTime}
            onChange={handleSeekChange}
            onMouseDown={beginSeek}
            onMouseUp={commitSeek}
            onTouchStart={beginSeek}
            onTouchEnd={commitSeek}
            onKeyUp={commitSeek}
            className="absolute inset-0 w-full opacity-0 cursor-pointer"
          />
        </div>
        <span className="text-[10px] text-gray-500 w-8 tabular-nums">{fmt(dur)}</span>
      </div>

      <div className="px-4 pb-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-[10px]">
        <label className="text-gray-400 flex items-center gap-1 col-span-2">
          Crossfade
          <input
            type="range"
            min={0.5}
            max={2}
            step={0.05}
            value={crossfadeAmount}
            onChange={(e) => setCrossfadeAmount(parseFloat(e.target.value))}
            className="flex-1 accent-primary"
          />
          <span className="text-gray-500 w-8 text-right">{crossfadeAmount.toFixed(2)}x</span>
        </label>
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={() => setTempoSync((v) => !v)}
            className={`rounded px-2 py-1 border transition ${tempoSync ? 'border-primary text-primary' : 'border-gray-600 text-gray-400'}`}
          >
            Tempo Sync
          </button>
          <button
            onClick={() => setKeyLock((v) => !v)}
            className={`rounded px-2 py-1 border transition ${keyLock ? 'border-primary text-primary' : 'border-gray-600 text-gray-400'}`}
          >
            Key Lock
          </button>
        </div>
      </div>

      {fading && (
        <div className="px-4 pb-2">
          <button onClick={emergencyCut} className="w-full rounded bg-red-500/20 text-red-300 border border-red-500/40 py-1.5 text-[11px] hover:bg-red-500/30 transition">
            Emergency Cut
          </button>
        </div>
      )}

      <div className="px-3 pb-3 max-h-40 overflow-y-auto">
        {tracks.map((t, i) => (
          <button
            key={`${t.songId}-${i}`}
            onClick={() => skipTo(i)}
            className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg text-left text-xs transition hover:bg-white/5 ${i === idx ? 'bg-white/10' : i < idx ? 'opacity-40' : ''}`}
          >
            <span className="w-5 text-center shrink-0 text-[11px]" style={i === idx ? { color: accentColor } : { color: '#6b7280' }}>
              {i === idx && playing ? '��' : i + 1}
            </span>
            <span className="flex-1 truncate" style={i === idx ? { color: '#fff' } : { color: '#d1d5db' }}>{t.title}</span>
            <span className="text-gray-600 truncate max-w-[80px] shrink-0">{t.artist}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
