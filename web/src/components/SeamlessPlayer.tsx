import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import type { DjTransitionPlanItem } from '../types'
import { getProcessedStreamUrl } from '../api/client'

// Superpowered main-thread imports
import { SuperpoweredGlue, SuperpoweredWebAudio } from '@superpoweredsdk/web'

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

function fmt(sec: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function modPositive(x: number, m: number): number {
  if (!isFinite(x) || !isFinite(m) || m <= 0) return 0
  const r = x % m
  return r < 0 ? r + m : r
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SpWebAudioManager = any
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SpNode = any

/* ─── Superpowered DJ Player ─── */

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
  const [spReady, setSpReady] = useState(false)

  const engineRef = useRef<{
    webaudioManager: SpWebAudioManager | null
    processorNode: SpNode | null
    alive: boolean
    slot: 'A' | 'B'
    idx: number
    fading: boolean
    playing: boolean
    transitionStartMs: number
    transitionDurationMs: number
    transitionTimer: ReturnType<typeof setTimeout> | 0
    preloadedNextIdx: number
    lastPosA: number
    lastDurA: number
    lastPosB: number
    lastDurB: number
  }>({
    webaudioManager: null,
    processorNode: null,
    alive: false,
    slot: 'A',
    idx: 0,
    fading: false,
    playing: false,
    transitionStartMs: 0,
    transitionDurationMs: 0,
    transitionTimer: 0,
    preloadedNextIdx: -1,
    lastPosA: 0,
    lastDurA: 0,
    lastPosB: 0,
    lastDurB: 0,
  })
  const tracksRef = useRef(tracks)
  tracksRef.current = tracks
  const onEndRef = useRef(onEnd)
  onEndRef.current = onEnd
  const seekingRef = useRef(false)
  seekingRef.current = seeking
  const crossfadeAmountRef = useRef(crossfadeAmount)
  crossfadeAmountRef.current = crossfadeAmount
  const tempoSyncRef = useRef(tempoSync)
  tempoSyncRef.current = tempoSync
  const keyLockRef = useRef(keyLock)
  keyLockRef.current = keyLock
  const crossfadeSecRef = useRef(crossfadeSec)
  crossfadeSecRef.current = crossfadeSec

  const transitionByIndex = useRef(new Map<number, DjTransitionPlanItem>())
  useEffect(() => {
    const map = new Map<number, DjTransitionPlanItem>()
    transitionPlan?.forEach((item, i) => map.set(i, item))
    transitionByIndex.current = map
  }, [transitionPlan])

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const sendToAudio = (msg: Record<string, any>) => {
    const node = engineRef.current.processorNode
    if (node?.sendMessageToAudioScope) {
      node.sendMessageToAudioScope(msg)
    }
  }
  const getNextDeck = () => (engineRef.current.slot === 'A' ? 'B' : 'A')

  const clearTransitionTimer = () => {
    const timer = engineRef.current.transitionTimer
    if (timer) { clearTimeout(timer); engineRef.current.transitionTimer = 0 }
  }

  const getActivePos = () => {
    const e = engineRef.current
    return e.slot === 'A' ? e.lastPosA : e.lastPosB
  }
  const getActiveDur = () => {
    const e = engineRef.current
    return e.slot === 'A' ? e.lastDurA : e.lastDurB
  }
  const getDisplayPos = () => {
    const e = engineRef.current
    if (!e.fading) return getActivePos()
    const xfDurMs = e.transitionDurationMs || 1
    const progress = Math.max(0, Math.min(1, (getActivePos() - e.transitionStartMs) / xfDurMs))
    return progress >= 0.5
      ? (e.slot === 'A' ? e.lastPosB : e.lastPosA)
      : getActivePos()
  }
  const getDisplayDur = () => {
    const e = engineRef.current
    if (!e.fading) return getActiveDur()
    const xfDurMs = e.transitionDurationMs || 1
    const progress = Math.max(0, Math.min(1, (getActivePos() - e.transitionStartMs) / xfDurMs))
    return progress >= 0.5
      ? (e.slot === 'A' ? e.lastDurB : e.lastDurA)
      : getActiveDur()
  }

  const completeTransition = () => {
    const e = engineRef.current
    if (!e.alive) return
    clearTransitionTimer()
    sendToAudio({ type: 'pause', deck: e.slot })
    e.slot = e.slot === 'A' ? 'B' : 'A'
    e.fading = false
    e.idx += 1
    e.transitionStartMs = 0
    e.transitionDurationMs = 0
    e.preloadedNextIdx = -1
    sendToAudio({ type: 'setGain', deck: e.slot, value: 1.0 })
    sendToAudio({ type: 'setGain', deck: e.slot === 'A' ? 'B' : 'A', value: 0.0 })
    sendToAudio({ type: 'setActiveDeck', deck: e.slot })
    sendToAudio({ type: 'setEq', deck: 'A', low: 1, mid: 1, high: 1 })
    sendToAudio({ type: 'setEq', deck: 'B', low: 1, mid: 1, high: 1 })
    sendToAudio({ type: 'setFilter', deck: 'A', lowpassHz: 20000, highpassHz: 20 })
    sendToAudio({ type: 'setFilter', deck: 'B', lowpassHz: 20000, highpassHz: 20 })
    setFading(false)
    setNextMixInSec(null)
    setIdx(e.idx)
  }

  const primeNextTrack = (nextTrack: SeamlessTrack | undefined, nextIndex: number) => {
    const e = engineRef.current
    if (!nextTrack || e.fading || nextIndex < 0) return
    if (e.preloadedNextIdx === nextIndex) return
    const nextDeck = getNextDeck()
    sendToAudio({ type: 'loadTrack', deck: nextDeck, url: getProcessedStreamUrl(nextTrack.filePath) })
    e.preloadedNextIdx = nextIndex
  }

  const getTransitionTriggerMs = (activeTrack: SeamlessTrack | undefined, nextTrack: SeamlessTrack | undefined): number | null => {
    const e = engineRef.current
    if (!activeTrack || !nextTrack) return null
    const plan = transitionByIndex.current.get(e.idx)
    const base = Math.max(1, plan?.crossfade_sec ?? crossfadeSecRef.current)
    const xfSec = Math.min(20, Math.max(1, base * crossfadeAmountRef.current))
    const activeDurMs = getActiveDur()
    const earlyMs = activeDurMs > 0 ? Math.max(0, activeDurMs - Math.max(xfSec, 12) * 1000) : null
    if (plan) {
      const exitMs = typeof plan.exit_time_sec === 'number' && plan.exit_time_sec > 0
        ? plan.exit_time_sec * 1000
        : (activeTrack.bpm && activeTrack.bpm > 0 ? (plan.exit_beat * 60 / activeTrack.bpm) * 1000 : undefined)
      if (exitMs != null) {
        const trigger = Math.max(0, exitMs - xfSec * 1000)
        return earlyMs != null ? Math.min(trigger, earlyMs) : trigger
      }
    }
    return activeDurMs > 0 ? Math.max(0, activeDurMs - Math.max(xfSec, 12) * 1000) : null
  }

  const tryTriggerTransition = () => {
    const e = engineRef.current
    if (e.fading || !e.playing || !e.alive) return
    const currentTrack = tracksRef.current[e.idx]
    const nextTrack = tracksRef.current[e.idx + 1]
    if (!currentTrack || !nextTrack) return

    const plan = transitionByIndex.current.get(e.idx)
    const base = Math.max(1, plan?.crossfade_sec ?? crossfadeSecRef.current)
    const xfSec = Math.min(20, Math.max(1, base * crossfadeAmountRef.current))
    const xfMs = xfSec * 1000
    const activePosMs = getActivePos()
    const activeDurMs = getActiveDur()
    const leftMs = activeDurMs > 0 ? activeDurMs - activePosMs : Infinity

    const triggerMs = getTransitionTriggerMs(currentTrack, nextTrack)
    let shouldStart = triggerMs != null ? activePosMs >= triggerMs : (activeDurMs > 0 ? leftMs <= xfMs : false)
    if (activeDurMs > 0 && activePosMs >= Math.max(0, activeDurMs - 350)) shouldStart = true
    if (!shouldStart || (activeDurMs > 0 && leftMs <= 50)) return

    e.fading = true
    e.transitionStartMs = activePosMs
    e.transitionDurationMs = xfMs
    e.preloadedNextIdx = -1
    setFading(true)
    setNextMixInSec(null)

    const nextDeck = getNextDeck()
    sendToAudio({ type: 'loadTrack', deck: nextDeck, url: getProcessedStreamUrl(nextTrack.filePath) })

    const tempoRatio = tempoSyncRef.current && plan && plan.tempo_ratio > 0 ? plan.tempo_ratio : 1
    sendToAudio({ type: 'setPlaybackRate', deck: nextDeck, value: tempoRatio })
    sendToAudio({ type: 'setTimeStretching', deck: nextDeck, enabled: keyLockRef.current })

    if (plan) {
      const entryMs = typeof plan.entry_time_sec === 'number' ? plan.entry_time_sec * 1000 : 0
      const fromInterval = typeof plan.from_beat_interval_sec === 'number' && plan.from_beat_interval_sec > 0
        ? plan.from_beat_interval_sec * 1000
        : (currentTrack.bpm && currentTrack.bpm > 0 ? 60000 / currentTrack.bpm : 500)
      const toIntervalBase = typeof plan.to_beat_interval_sec === 'number' && plan.to_beat_interval_sec > 0
        ? plan.to_beat_interval_sec * 1000
        : (nextTrack.bpm && nextTrack.bpm > 0 ? 60000 / nextTrack.bpm : 500)
      const toInterval = toIntervalBase / Math.max(tempoRatio, 1e-6)
      const anchorMs = typeof plan.phase_anchor_sec === 'number' ? plan.phase_anchor_sec * 1000 : Math.max(0, activePosMs)
      const phaseFromMs = modPositive(activePosMs - anchorMs, fromInterval)
      const phaseFraction = fromInterval > 0 ? phaseFromMs / fromInterval : 0
      const entryOffset = phaseFraction * toInterval
      sendToAudio({ type: 'setPosition', deck: nextDeck, ms: Math.max(0, entryMs + entryOffset) })
    } else {
      sendToAudio({ type: 'setPosition', deck: nextDeck, ms: 0 })
    }

    sendToAudio({ type: 'play', deck: nextDeck })

    // Crossfade + automation
    const startTime = performance.now()
    if (plan && plan.fx_automation.length > 0) {
      const sorted = [...plan.fx_automation].sort((a, b) => a.time_sec - b.time_sec)
      let pi = 0
      const automationTick = () => {
        if (!e.alive || !e.fading) return
        const elapsed = (performance.now() - startTime) / 1000
        while (pi < sorted.length && sorted[pi].time_sec <= elapsed) {
          sendToAudio({ type: 'transitionAutomation', point: sorted[pi] })
          pi++
        }
        const progress = Math.max(0, Math.min(1, elapsed / xfSec))
        sendToAudio({ type: 'setGain', deck: e.slot, value: Math.cos(progress * Math.PI * 0.5) })
        sendToAudio({ type: 'setGain', deck: nextDeck, value: Math.sin(progress * Math.PI * 0.5) })
        if (pi < sorted.length || progress < 1) requestAnimationFrame(automationTick)
      }
      requestAnimationFrame(automationTick)
    } else {
      const fadeTick = () => {
        if (!e.alive || !e.fading) return
        const progress = Math.max(0, Math.min(1, (performance.now() - startTime) / 1000 / xfSec))
        sendToAudio({ type: 'setGain', deck: e.slot, value: Math.cos(progress * Math.PI * 0.5) })
        sendToAudio({ type: 'setGain', deck: nextDeck, value: Math.sin(progress * Math.PI * 0.5) })
        if (progress < 1) requestAnimationFrame(fadeTick)
      }
      requestAnimationFrame(fadeTick)
    }

    clearTransitionTimer()
    e.transitionTimer = setTimeout(() => {
      if (!e.alive || !e.fading) return
      completeTransition()
    }, Math.max(120, xfMs + 80))
  }

  const handleEof = (deck: 'A' | 'B') => {
    const e = engineRef.current
    if (!e.alive || deck !== e.slot) return
    if (e.fading) { completeTransition(); return }
    const ni = e.idx + 1
    if (ni < tracksRef.current.length) {
      e.idx = ni
      e.preloadedNextIdx = -1
      setNextMixInSec(null)
      setIdx(ni)
      sendToAudio({ type: 'loadTrack', deck: e.slot, url: getProcessedStreamUrl(tracksRef.current[ni].filePath) })
    } else {
      e.playing = false
      setPlaying(false)
      setNextMixInSec(null)
      onEndRef.current?.()
    }
  }

  // ── Initialize Superpowered Engine ──
  useEffect(() => {
    const e = engineRef.current
    e.alive = true
    e.slot = 'A'
    e.idx = 0
    e.fading = false
    e.playing = false
    e.preloadedNextIdx = -1
    setIdx(0); setTime(0); setSeekValue(0); setDur(0)
    setFading(false); setPlaying(false); setSeeking(false)
    setNextMixInSec(null); setSpReady(false)

    let destroyed = false

    async function init() {
      try {
        const superpowered = await SuperpoweredGlue.Instantiate(
          'ExampleLicenseKey-WillExpire-OnNextUpdate'
        )
        if (destroyed) return

        const webaudioManager = new SuperpoweredWebAudio(44100, superpowered)
        e.webaudioManager = webaudioManager

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const onMessage = (message: any) => {
          if (!e.alive) return
          if (message.event === 'ready') {
            setSpReady(true)
            if (tracksRef.current.length > 0) {
              sendToAudio({ type: 'loadTrack', deck: 'A', url: getProcessedStreamUrl(tracksRef.current[0].filePath) })
            }
            return
          }
          if (message.event === 'trackLoaded') {
            const deck = message.deck as string
            const durMs = message.durationMs as number
            if (deck === e.slot && !e.fading) {
              setDur(durMs / 1000)
              if (e.playing) sendToAudio({ type: 'play', deck })
            }
            return
          }
          if (message.event === 'positions') {
            e.lastPosA = (message.aPosMs as number) || 0
            e.lastDurA = (message.aDurMs as number) || 0
            e.lastPosB = (message.bPosMs as number) || 0
            e.lastDurB = (message.bDurMs as number) || 0
            if (message.aEof && e.slot === 'A') handleEof('A')
            if (message.bEof && e.slot === 'B') handleEof('B')
            if (!seekingRef.current) {
              const posMs = getDisplayPos()
              const durMs = getDisplayDur()
              setTime(posMs / 1000)
              setSeekValue(posMs / 1000)
              if (durMs > 0) setDur(durMs / 1000)
            }
            if (e.playing && !e.fading) {
              const currentTrack = tracksRef.current[e.idx]
              const nextTrack = tracksRef.current[e.idx + 1]
              if (nextTrack) {
                primeNextTrack(nextTrack, e.idx + 1)
                const triggerMs = getTransitionTriggerMs(currentTrack, nextTrack)
                if (triggerMs != null) {
                  const remain = (triggerMs - getActivePos()) / 1000
                  setNextMixInSec(isFinite(remain) ? Math.max(0, remain) : null)
                }
                tryTriggerTransition()
              }
            }
          }
        }

        const processorUrl = new URL('/processors/djProcessor.js', window.location.origin).href
        const node = await webaudioManager.createAudioNodeAsync(processorUrl, 'DjProcessor', onMessage)
        if (destroyed) { node.disconnect(); return }
        e.processorNode = node
        node.connect(webaudioManager.audioContext.destination)
      } catch (err) {
        console.error('[Superpowered] Init error:', err)
      }
    }

    init()

    return () => {
      destroyed = true
      e.alive = false
      clearTransitionTimer()
      if (e.processorNode) {
        try { e.processorNode.destruct?.(); e.processorNode.disconnect?.() } catch { /* */ }
        e.processorNode = null
      }
      if (e.webaudioManager) {
        try { e.webaudioManager.audioContext.close() } catch { /* */ }
        e.webaudioManager = null
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracks])

  const togglePlay = async () => {
    const e = engineRef.current
    if (!e.alive || !e.processorNode) return
    const wam = e.webaudioManager
    if (wam && wam.audioContext.state === 'suspended') await wam.audioContext.resume().catch(() => {})
    if (e.playing) {
      sendToAudio({ type: 'pause', deck: e.slot })
      if (e.fading) sendToAudio({ type: 'pause', deck: getNextDeck() })
      e.playing = false; setPlaying(false); setNextMixInSec(null); return
    }
    sendToAudio({ type: 'play', deck: e.slot })
    if (e.fading) sendToAudio({ type: 'play', deck: getNextDeck() })
    e.playing = true; setPlaying(true)
  }

  const skipTo = (ti: number) => {
    const e = engineRef.current
    if (ti < 0 || ti >= tracksRef.current.length || !e.alive) return
    clearTransitionTimer()
    sendToAudio({ type: 'pause', deck: 'A' })
    sendToAudio({ type: 'pause', deck: 'B' })
    e.fading = false; e.slot = 'A'; e.idx = ti; e.preloadedNextIdx = -1
    setFading(false); setNextMixInSec(null); setIdx(ti); setTime(0); setSeekValue(0)
    sendToAudio({ type: 'setGain', deck: 'A', value: 1.0 })
    sendToAudio({ type: 'setGain', deck: 'B', value: 0.0 })
    sendToAudio({ type: 'setActiveDeck', deck: 'A' })
    sendToAudio({ type: 'setEq', deck: 'A', low: 1, mid: 1, high: 1 })
    sendToAudio({ type: 'setEq', deck: 'B', low: 1, mid: 1, high: 1 })
    sendToAudio({ type: 'setFilter', deck: 'A', lowpassHz: 20000, highpassHz: 20 })
    sendToAudio({ type: 'setFilter', deck: 'B', lowpassHz: 20000, highpassHz: 20 })
    sendToAudio({ type: 'setPlaybackRate', deck: 'A', value: 1 })
    sendToAudio({ type: 'setTimeStretching', deck: 'A', enabled: true })
    sendToAudio({ type: 'loadTrack', deck: 'A', url: getProcessedStreamUrl(tracksRef.current[ti].filePath) })
  }

  const emergencyCut = () => {
    const e = engineRef.current
    if (!e.fading) return
    clearTransitionTimer()
    sendToAudio({ type: 'pause', deck: e.slot })
    e.slot = e.slot === 'A' ? 'B' : 'A'
    e.fading = false; e.preloadedNextIdx = -1; e.idx += 1
    setFading(false); setNextMixInSec(null); setIdx(e.idx)
    sendToAudio({ type: 'setGain', deck: e.slot, value: 1.0 })
    sendToAudio({ type: 'setGain', deck: e.slot === 'A' ? 'B' : 'A', value: 0.0 })
    sendToAudio({ type: 'setActiveDeck', deck: e.slot })
    sendToAudio({ type: 'setEq', deck: 'A', low: 1, mid: 1, high: 1 })
    sendToAudio({ type: 'setEq', deck: 'B', low: 1, mid: 1, high: 1 })
  }

  const beginSeek = () => setSeeking(true)
  const handleSeekChange = (ev: ChangeEvent<HTMLInputElement>) => {
    const v = parseFloat(ev.target.value)
    if (!isFinite(v)) return
    if (!seeking) setSeeking(true)
    setSeekValue(v)
  }
  const commitSeek = () => {
    const target = seekValue
    if (isFinite(target) && dur > 0) {
      sendToAudio({ type: 'seek', deck: engineRef.current.slot, percent: Math.max(0, Math.min(1, target / dur)) })
      setTime(target); setSeekValue(target)
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
      {/* Header */}
      <div className="px-4 py-2.5 flex items-center gap-2 border-b border-gray-700/50">
        <span className="relative flex h-2.5 w-2.5">
          {playing && <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: accentColor }} />}
          <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: accentColor }} />
        </span>
        <span className="text-xs font-bold text-white tracking-wide">
          DJ Seamless Mix
          <span className="ml-1.5 text-[9px] font-medium px-1 py-0.5 rounded bg-white/10 text-gray-300">Superpowered</span>
        </span>
        {!spReady && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 animate-pulse">Loading engine...</span>}
        {fading && <span className="text-[10px] px-1.5 py-0.5 rounded-full animate-pulse" style={{ background: `${accentColor}33`, color: accentColor }}>Transition</span>}
        {!fading && playing && nextTrack && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: '#f59e0b22', color: '#f59e0b' }}>
            {nextMixInSec != null ? `Next mix in ${nextMixInSec.toFixed(1)}s` : 'Next mix arming...'}
          </span>
        )}
        <span className="text-[10px] text-gray-500 ml-auto tabular-nums">{idx + 1} / {tracks.length}</span>
      </div>

      {/* Controls */}
      <div className="px-4 py-3 flex items-center gap-3">
        <button onClick={() => skipTo(idx - 1)} disabled={idx === 0} className="text-gray-400 hover:text-white disabled:opacity-30 transition p-1">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6 8.5 6V6z" /></svg>
        </button>
        <button onClick={togglePlay} disabled={!spReady} className="w-10 h-10 rounded-full flex items-center justify-center transition hover:scale-110 shadow-lg disabled:opacity-40" style={{ background: accentColor }}>
          {playing
            ? <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
            : <svg className="w-5 h-5 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>}
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
            <span className="animate-pulse">▶</span>
            <span className="truncate max-w-[72px]">{nextTrack.title}</span>
          </div>
        )}
      </div>

      {/* Progress */}
      <div className="px-4 pb-2 flex items-center gap-2">
        <span className="text-[10px] text-gray-500 w-8 text-right tabular-nums">{fmt(shownTime)}</span>
        <div className="flex-1 h-2 relative">
          <div className="absolute inset-0 bg-gray-700/60 rounded-full overflow-hidden">
            <div className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-200" style={{ width: `${pct}%`, background: accentColor }} />
          </div>
          <input
            type="range" min={0} max={dur || 0} step={0.05} value={shownTime}
            onChange={handleSeekChange}
            onMouseDown={beginSeek} onMouseUp={commitSeek}
            onTouchStart={beginSeek} onTouchEnd={commitSeek}
            onKeyUp={commitSeek}
            className="absolute inset-0 w-full opacity-0 cursor-pointer"
          />
        </div>
        <span className="text-[10px] text-gray-500 w-8 tabular-nums">{fmt(dur)}</span>
      </div>

      {/* DJ Controls */}
      <div className="px-4 pb-2 grid grid-cols-1 sm:grid-cols-3 gap-2 text-[10px]">
        <label className="text-gray-400 flex items-center gap-1 col-span-2">
          Crossfade
          <input type="range" min={0.5} max={2} step={0.05} value={crossfadeAmount} onChange={(ev) => setCrossfadeAmount(parseFloat(ev.target.value))} className="flex-1 accent-primary" />
          <span className="text-gray-500 w-8 text-right">{crossfadeAmount.toFixed(2)}x</span>
        </label>
        <div className="flex items-center justify-end gap-2">
          <button onClick={() => setTempoSync((v) => !v)} className={`rounded px-2 py-1 border transition ${tempoSync ? 'border-primary text-primary' : 'border-gray-600 text-gray-400'}`}>Tempo Sync</button>
          <button onClick={() => setKeyLock((v) => !v)} className={`rounded px-2 py-1 border transition ${keyLock ? 'border-primary text-primary' : 'border-gray-600 text-gray-400'}`}>Key Lock</button>
        </div>
      </div>

      {fading && (
        <div className="px-4 pb-2">
          <button onClick={emergencyCut} className="w-full rounded bg-red-500/20 text-red-300 border border-red-500/40 py-1.5 text-[11px] hover:bg-red-500/30 transition">Emergency Cut</button>
        </div>
      )}

      {/* Track List */}
      <div className="px-3 pb-3 max-h-40 overflow-y-auto">
        {tracks.map((t, i) => (
          <button key={`${t.songId}-${i}`} onClick={() => skipTo(i)} className={`w-full flex items-center gap-2 py-1.5 px-2 rounded-lg text-left text-xs transition hover:bg-white/5 ${i === idx ? 'bg-white/10' : i < idx ? 'opacity-40' : ''}`}>
            <span className="w-5 text-center shrink-0 text-[11px]" style={i === idx ? { color: accentColor } : { color: '#6b7280' }}>{i === idx && playing ? '♫' : i + 1}</span>
            <span className="flex-1 truncate" style={i === idx ? { color: '#fff' } : { color: '#d1d5db' }}>{t.title}</span>
            <span className="text-gray-600 truncate max-w-[80px] shrink-0">{t.artist}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
