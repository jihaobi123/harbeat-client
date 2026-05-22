import { useEffect, useRef, useState } from 'react'
import { MixSessionController } from '../engine/MixSessionController'
import type { MixSessionSnapshot, EnergyPreference, MixStrategy as ControllerMixStrategy } from '../engine/MixSessionController'
import { MixAudioEngine } from '../engine/MixAudioEngine'
import { DJ_LIVE_SFX, playDjLiveSfx, type DjLiveSfxId } from '../engine/DjLiveSfx'
import type { DjMixPlanResult } from '../types/api'

/**
 * NewMixFeatures
 * -------------------------------------------------------------------------
 * 把 6 项新功能集中在一个独立面板里：
 *   1. 8 种 Mix 策略选择 + 能量曲线 + 风格        → POST /api/dev/mix-plan
 *   2. 能量曲线 6 槽 + 渐强 / V 形 / 双峰 预设
 *   3. 循环前 30 秒 / 退出循环 (语音 intent: loop_last_30s / loop_off)
 *   4. 能量 ↑ / 能量 ↓ / 按风格切歌
 *   5. 5 种 DJ 现场操作音效（客户端 Web Audio 合成，零延迟）
 *   6. MC 语音控制 (webkitSpeechRecognition + /api/voice/command)
 *
 * 该组件不修改任何已有 SessionPanel 状态/行为；所有副作用走自己 fetch +
 * 内置 <audio>。设计成可随时移除 / 折叠。
 * ------------------------------------------------------------------------- */

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

type MixStrategy =
  | 'CLEAN_BLEND'
  | 'FADE'
  | 'ECHO_OUT'
  | 'RISER'
  | 'CUT_SWAP'
  | 'HARD_CUT'
  | 'TRIPLET_SWAP'
  | 'MELODIC_RESET'

const MIX_STRATEGIES: { value: MixStrategy; desc: string }[] = [
  { value: 'CLEAN_BLEND', desc: '默认无缝混合' },
  { value: 'FADE', desc: '长淡入淡出' },
  { value: 'ECHO_OUT', desc: '回声尾出' },
  { value: 'RISER', desc: '上升过渡' },
  { value: 'CUT_SWAP', desc: '硬切换' },
  { value: 'HARD_CUT', desc: '紧急硬切' },
  { value: 'TRIPLET_SWAP', desc: '三连音切换' },
  { value: 'MELODIC_RESET', desc: '旋律归零' },
]

const ENERGY_PRESETS: { label: string; curve: number[] }[] = [
  { label: '渐强 (低→高)', curve: [3, 4, 5, 6, 7, 8] },
  { label: 'V 形 (高低高)', curve: [7, 5, 3, 5, 7, 9] },
  { label: '双峰', curve: [5, 8, 5, 8, 5, 7] },
  { label: '清空', curve: [5, 5, 5, 5, 5, 5] },
]

const STYLES = ['hiphop', 'popping', 'locking', 'breaking', 'house', 'waacking', 'krump', 'jazz']

function authHeaders(): Record<string, string> {
  const t = localStorage.getItem('harbeat_token')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function postJson<T>(path: string, body: any): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  const j: ApiEnvelope<T> = await r.json()
  if (j.code !== 0) throw new Error(j.message || 'request failed')
  return j.data
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: authHeaders() })
  const j: ApiEnvelope<T> = await r.json()
  if (j.code !== 0) throw new Error(j.message || 'request failed')
  return j.data
}

// ---------- Web Speech recognition (best-effort) ----------
type SRConstructor = new () => any
function getSR(): SRConstructor | null {
  const w = window as any
  return (w.SpeechRecognition || w.webkitSpeechRecognition || null) as SRConstructor | null
}

export default function NewMixFeatures() {
  // ---------- Mix plan controls ----------
  const [style, setStyle] = useState<string>('hiphop')
  const [duration, setDuration] = useState<number>(10)
  const [strategy, setStrategy] = useState<MixStrategy>('CLEAN_BLEND')
  const [curve, setCurve] = useState<number[]>([5, 5, 5, 5, 5, 5])
  const [planLoading, setPlanLoading] = useState(false)
  const [planResult, setPlanResult] = useState<any>(null)
  const [planError, setPlanError] = useState('')

  // ---------- DJ Live SFX (客户端 Web Audio 合成) ----------
  const [sfxError, setSfxError] = useState('')

  // ---------- Online mix playback (MixSessionController + MixAudioEngine) ----------
  const controllerRef = useRef<MixSessionController | null>(null)
  const [mixSnapshot, setMixSnapshot] = useState<MixSessionSnapshot | null>(null)
  const mixLoopingRef = useRef<boolean>(false)
  const [mixPlaying, setMixPlaying] = useState(false)
  const [mixIndex, setMixIndex] = useState(-1)
  const [mixCurrentTitle, setMixCurrentTitle] = useState('')
  const [mixError, setMixError] = useState('')
  const [mixLooping, setMixLooping] = useState(false)

  const getController = (): MixSessionController => {
    if (!controllerRef.current) {
      controllerRef.current = new MixSessionController()
      controllerRef.current.setOnStateChange((snap) => {
        setMixSnapshot(snap)
        const active = snap.state === 'playing' || snap.state === 'transitioning' || snap.state === 'loading'
        setMixPlaying(active)
        setMixIndex(snap.currentIndex)
        setMixCurrentTitle(
          snap.currentTrack ? `${snap.currentTrack.title} — ${snap.currentTrack.artist}` : ''
        )
        if (snap.error) setMixError(snap.error)
        if (!active && snap.state !== 'loading') {
          mixLoopingRef.current = false
          setMixLooping(false)
        }
      })
    }
    return controllerRef.current
  }

  // ---------- Voice ----------
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [lastIntent, setLastIntent] = useState('')
  const [voiceError, setVoiceError] = useState('')
  const [listening, setListening] = useState(false)
  const srRef = useRef<any>(null)

  // ---------- Cmd feedback (for switch buttons / loop) ----------
  const [cmdMsg, setCmdMsg] = useState('')

  // ---------- Pending library_song_ids from MixtapeBuilder import ----------
  const [pendingIds, setPendingIds] = useState<string[]>(() => {
    try {
      const raw = window.localStorage.getItem('harbeat_pending_library_ids')
      const arr = raw ? JSON.parse(raw) : []
      return Array.isArray(arr) ? arr.filter((x: any) => typeof x === 'string') : []
    } catch { return [] }
  })

  useEffect(() => {
    const handler = (e: any) => {
      const ids = e?.detail?.library_song_ids
      if (Array.isArray(ids)) setPendingIds(ids.filter((x: any) => typeof x === 'string'))
    }
    window.addEventListener('harbeat:mixtape-imported', handler)
    return () => window.removeEventListener('harbeat:mixtape-imported', handler)
  }, [])

  const applyPreset = (curveValues: number[]) => setCurve([...curveValues])
  const updateCurveSlot = (i: number, v: number) => {
    setCurve((prev) => prev.map((x, idx) => (idx === i ? Math.max(1, Math.min(10, v)) : x)))
  }

  const generatePlan = async () => {
    setPlanLoading(true)
    setPlanError('')
    setPlanResult(null)
    try {
      const allSame = curve.every((v) => v === curve[0])
      const body: any = {
        style,
        duration_minutes: duration,
        quality_mode: 'balanced',
        diversity: 0.35,
      }
      if (!allSame) body.target_energy_curve = curve
      if (pendingIds.length >= 2) body.library_song_ids = pendingIds
      const data = await postJson<any>('/api/dev/mix-plan', body)
      setPlanResult({ strategy, ...data })
    } catch (e: any) {
      setPlanError(e.message)
    } finally {
      setPlanLoading(false)
    }
  }

  const sendVoiceCmd = async (text: string) => {
    setCmdMsg('')
    try {
      const data = await postJson<any>('/api/voice/command', { text })
      setLastIntent(`${data.intent} (${Math.round((data.confidence ?? 0) * 100)}%)`)
      setCmdMsg(`✔ ${data.action_taken || data.intent}`)
      // Wire intents to the active online-mix player so they actually affect audio.
      switch (data.intent) {
        case 'loop_last_30s':
          loopLastSecondsOnActive(30)
          break
        case 'loop_off':
          loopOffOnActive()
          break
        case 'next':
          skipMixToNext()
          break
        case 'lift_energy':
          skipByEnergy('higher')
          break
        case 'drop_energy':
          skipByEnergy('lower')
          break
        case 'switch_style':
          skipByStyle()
          break
        case 'pause': {
          controllerRef.current?.pause()
          break
        }
        case 'play':
        case 'release': {
          controllerRef.current?.play().catch(() => {})
          break
        }
        case 'emergency_stop':
          stopMixPlayback()
          break
      }
    } catch (e: any) {
      setCmdMsg(`✗ ${e.message}`)
    }
  }

  const playSfx = (id: DjLiveSfxId) => {
    try {
      playDjLiveSfx(id)
      setSfxError('')
    } catch (e: any) {
      setSfxError(String(e?.message ?? e))
    }
  }

  // ---------- Online mix playback (MixSessionController + MixAudioEngine) ----------

  const stopMixPlayback = () => {
    controllerRef.current?.stop()
    mixLoopingRef.current = false
    setMixLooping(false)
    MixAudioEngine.getInstance().clearLoop()
  }

  // Loop the last N seconds using MixAudioEngine's native loop points.
  const loopLastSecondsOnActive = (seconds: number = 30) => {
    const engine = MixAudioEngine.getInstance()
    const deck = engine.getActiveDeck()
    const pos = engine.getPosition(deck)
    if (pos === 0 && mixSnapshot?.state !== 'playing' && mixSnapshot?.state !== 'transitioning') {
      setMixError('当前没有正在播放的混音')
      return
    }
    const start = Math.max(0, pos - seconds)
    const end = Math.max(start + 0.5, pos)
    engine.setLoopPoints(start, end)
    const loopState = engine.getLoopState()
    if (!loopState.active) engine.toggleLoop()
    mixLoopingRef.current = true
    setMixLooping(true)
  }

  const loopOffOnActive = () => {
    MixAudioEngine.getInstance().clearLoop()
    mixLoopingRef.current = false
    setMixLooping(false)
  }

  // Skip to next: execute the planned transition immediately via MixSessionController.
  const skipMixToNext = () => {
    const ctrl = controllerRef.current
    if (!ctrl || (mixSnapshot?.state !== 'playing' && mixSnapshot?.state !== 'transitioning')) {
      setMixError('当前没有正在播放的混音')
      return
    }
    loopOffOnActive()
    const mappedStrategy = (strategy.toLowerCase() as ControllerMixStrategy)
    void ctrl.next(true, mappedStrategy)
  }

  // Skip to next track whose energy is higher/lower than current — uses MixSessionController.setEnergyPreference()
  // which causes resolveNextIndex() to filter the remaining playlist by track.energy.
  const skipByEnergy = (direction: EnergyPreference) => {
    const ctrl = controllerRef.current
    if (!ctrl || (mixSnapshot?.state !== 'playing' && mixSnapshot?.state !== 'transitioning')) {
      setMixError('当前没有正在播放的混音')
      return
    }
    loopOffOnActive()
    ctrl.setEnergyPreference(direction)
    const mappedStrategy = (strategy.toLowerCase() as ControllerMixStrategy)
    void ctrl.next(true, mappedStrategy).then(() => {
      // Reset preference so future auto-transitions follow plan order again.
      window.setTimeout(() => ctrl.setEnergyPreference('none'), 1500)
    })
  }

  // Skip by style: pick a harmonically-matching unplayed track and transition to it,
  // WITHOUT resetting the current playback or mutating plan order.
  const skipByStyle = () => {
    const ctrl = controllerRef.current
    if (!ctrl || (mixSnapshot?.state !== 'playing' && mixSnapshot?.state !== 'transitioning')) {
      setMixError('当前没有正在播放的混音')
      return
    }
    loopOffOnActive()
    const mappedStrategy = (strategy.toLowerCase() as ControllerMixStrategy)
    void ctrl.skipToStyleMatch(mappedStrategy)
  }

  const playMixPlan = async () => {
    setMixError('')
    const plan = planResult as DjMixPlanResult | null
    if (!plan?.playlist || plan.playlist.length < 2) { setMixError('请先生成 Mix Plan'); return }
    const ctrl = getController()
    ctrl.loadPlan(plan)
    setMixPlaying(true)
    try {
      await ctrl.play()
    } catch (e: any) {
      setMixError(e.message)
      setMixPlaying(false)
    }
  }

  // ---------- Voice recognition handlers (toggle: 点击开始 → 再点结束) ----------
  const startListening = () => {
    setVoiceError('')
    const SR = getSR()
    if (!SR) {
      setVoiceError('当前浏览器不支持语音识别（请使用 Chrome / Edge）')
      return
    }
    // Web Speech API requires a secure context (HTTPS or localhost) for mic access.
    if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      setVoiceError('麦克风权限被禁（HTTP 不安全上下文）。请使用 HTTPS 或 localhost 访问本页。')
      return
    }
    try {
      const sr = new SR()
      sr.lang = 'zh-CN'
      sr.interimResults = true
      sr.continuous = true   // 持续录音，由用户再次点击按钮停止
      let lastSent = ''
      sr.onresult = (ev: any) => {
        let interim = ''
        let finalText = ''
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i]
          if (r.isFinal) finalText += r[0].transcript
          else interim += r[0].transcript
        }
        setTranscript(finalText || interim)
        if (finalText && finalText !== lastSent) {
          lastSent = finalText
          sendVoiceCmd(finalText.trim())
        }
      }
      sr.onerror = (ev: any) => {
        const err = ev.error || 'unknown'
        const hint = err === 'not-allowed' ? '（请点击地址栏左侧锁形/i 图标授权麦克风；HTTP 站点可能被浏览器禁用麦克风）' : ''
        setVoiceError(`识别错误: ${err}${hint}`)
        setListening(false)
      }
      sr.onend = () => setListening(false)
      sr.start()
      srRef.current = sr
      setListening(true)
    } catch (e: any) {
      setVoiceError(e.message)
    }
  }
  const stopListening = () => {
    try { srRef.current?.stop() } catch {}
    try { srRef.current?.abort?.() } catch {}
    setListening(false)
  }

  return (
    <div className="street-sticker bg-surface-light p-4 sm:p-5 mt-4 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg sm:text-xl street-title">新功能集</h3>
        <span className="text-xs street-subtitle text-gray-500">
          8 mix · energy curve · loop 30s · style/energy switch · flourish · MC voice
        </span>
      </div>

      {/* ===== 1 + 2 : Mix plan with strategy + energy curve + style ===== */}
      <section className="space-y-3">
        <div className="text-sm street-subtitle">① Mix 策略 + 能量曲线 + 风格</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">风格</span>
            <select value={style} onChange={(e) => setStyle(e.target.value)} className="px-2 py-1">
              {STYLES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-gray-500">时长 (min)</span>
            <input type="number" min={1} max={60} value={duration}
                   onChange={(e) => setDuration(parseInt(e.target.value || '10', 10))} className="px-2 py-1" />
          </label>
          <label className="flex flex-col gap-1 col-span-2">
            <span className="text-gray-500">Manual Mix Strategy</span>
            <select value={strategy} onChange={(e) => setStrategy(e.target.value as MixStrategy)} className="px-2 py-1">
              {MIX_STRATEGIES.map((m) => (
                <option key={m.value} value={m.value}>{m.value} — {m.desc}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="space-y-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <span className="text-xs text-gray-500">能量曲线（按曲目槽位 1–10）</span>
            <div className="flex flex-wrap gap-1">
              {ENERGY_PRESETS.map((p) => (
                <button key={p.label} onClick={() => applyPreset(p.curve)} className="text-xs px-2 py-1">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-6 gap-1 sm:gap-2">
            {curve.map((v, i) => (
              <label key={i} className="flex flex-col items-center text-xs">
                <span className="text-gray-500">#{i + 1}</span>
                <input type="number" min={1} max={10} value={v}
                       onChange={(e) => updateCurveSlot(i, parseInt(e.target.value || '5', 10))}
                       className="w-full px-1 py-1 text-center" />
              </label>
            ))}
          </div>
          <p className="text-[10px] text-gray-500">所有值相同则不发送曲线（保留默认推荐排序）。</p>
        </div>

        <button onClick={generatePlan} disabled={planLoading} className="bg-primary text-white px-4 py-2 text-sm">
          {planLoading ? '生成中…' : '生成 Mix Plan（含 target_energy_curve）'}
        </button>
        <div className="text-[11px] text-gray-400">
          {pendingIds.length >= 2 ? (
            <>将使用上方“加入歌单”的 <span className="text-cyan-400">{pendingIds.length}</span> 首歌作为混音输入。
              <button
                className="ml-2 underline"
                onClick={() => { setPendingIds([]); try { window.localStorage.removeItem('harbeat_pending_library_ids') } catch {} }}
              >清除</button>
            </>
          ) : (
            <>未携带用户歌曲，将使用 dev 默认歌池。</>
          )}
        </div>
        {planError && <div className="text-xs text-red-400">{planError}</div>}
        {planResult && (
          <div className="text-xs bg-surface-lighter p-2 max-h-40 overflow-auto">
            <div className="font-bold mb-1">Strategy: {planResult.strategy}</div>
            <pre className="whitespace-pre-wrap">
              {JSON.stringify({ tracks: planResult.tracks?.length, mix_plan: planResult.mix_plan, ids: planResult.tracks?.map((t: any) => t.song_id) }, null, 2)}
            </pre>
          </div>
        )}
        {planResult?.playlist?.length >= 2 && (
          <div className="bg-surface-lighter p-2 space-y-2">
            <div className="text-sm street-subtitle">▶ 在线混音播放</div>
            <div className="flex flex-wrap gap-2 text-sm">
              {!mixPlaying ? (
                <button onClick={playMixPlan} className="bg-green-500 text-black px-4 py-2">
                  ▶ 开始在线混音
                </button>
              ) : (
                <button onClick={stopMixPlayback} className="bg-red-500 text-white px-4 py-2">
                  ■ 停止
                </button>
              )}
              <div className="text-xs text-gray-300 self-center">
                {mixPlaying ? (
                  <>正在播放 #{mixIndex + 1}/{planResult.playlist.length} · {mixCurrentTitle}</>
                ) : (
                  <>共 {planResult.playlist.length} 首，按 plan 顺序流式播放并交叉淡化</>
                )}
              </div>
            </div>
            {mixError && <div className="text-xs text-red-400">{mixError}</div>}
            <p className="text-[10px] text-gray-500">
              使用 <code>/api/dev/songs/&lt;library_song_id&gt;/stream</code> 流式拉取；如服务器没有源文件会跳过该首。
            </p>
          </div>
        )}
      </section>

      {/* ===== 3 : Loop last 30s ===== */}
      <section className="space-y-2">
        <div className="text-sm street-subtitle">③ 循环最后 30 秒 {mixLooping && <span className="text-amber-400">· LOOP ON</span>}</div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => loopLastSecondsOnActive(30)} className="bg-amber-500 text-black text-sm px-3 py-2">
            ▶ 循环最后 30s
          </button>
          <button onClick={loopOffOnActive} className="text-sm px-3 py-2 bg-surface-lighter">
            ■ 退出循环
          </button>
        </div>
        <p className="text-[10px] text-gray-500">
          直接作用于上方"在线混音"的当前曲目；同时也响应语音 intent <code>loop_last_30s / loop_off</code>。
        </p>
      </section>

      {/* ===== 4 : Energy / style switch ===== */}
      <section className="space-y-2">
        <div className="text-sm street-subtitle">④ 切歌方式</div>
        <div className="flex gap-2 flex-wrap text-sm">
          <button onClick={skipMixToNext} className="bg-cyan-500 text-black px-3 py-2">⏭ 下一首</button>
          <button onClick={() => skipByEnergy('higher')} className="bg-cyan-600 text-black px-3 py-2">能量 ↑ 切歌</button>
          <button onClick={() => skipByEnergy('lower')} className="bg-sky-500 text-black px-3 py-2">能量 ↓ 切歌</button>
          <button onClick={skipByStyle} className="bg-indigo-500 text-white px-3 py-2">按风格切歌</button>
        </div>
        <p className="text-[10px] text-gray-500">所有切歌按钮都会触发当前混音 deck 的提前 crossfade 进入下一首。</p>
      </section>

      {/* ===== 5 : DJ Live SFX ===== */}
      <section className="space-y-2">
        <div className="text-sm street-subtitle">⑤ DJ 现场音效（5 种高频操作音 · 客户端合成）</div>
        {sfxError && <div className="text-xs text-red-400">{sfxError}</div>}
        <div className="flex flex-wrap gap-2 text-xs">
          {DJ_LIVE_SFX.map((f) => (
            <button key={f.id} onClick={() => playSfx(f.id)} className="bg-fuchsia-500 text-black px-3 py-2"
                    title={f.hint}>
              {f.label}
            </button>
          ))}
        </div>
        <p className="text-[10px] text-gray-500">点按即响 · 零延迟合成 · 可连点叠加</p>
      </section>

      {/* ===== 6 : MC voice ===== */}
      <section className="space-y-2">
        <div className="text-sm street-subtitle">⑥ MC 语音控制</div>
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <button onClick={() => setVoiceEnabled((v) => !v)}
                  className={voiceEnabled ? 'bg-green-500 text-white px-3 py-2' : 'bg-gray-500 text-white px-3 py-2'}>
            {voiceEnabled ? '语音 ON' : '语音 OFF'}
          </button>
          <button onClick={listening ? stopListening : startListening} disabled={!voiceEnabled}
                  className={listening ? 'bg-red-500 text-white px-3 py-2' : 'px-3 py-2'}>
            {listening ? '⏹ 停止' : '🎤 录音'}
          </button>
          {transcript && <span className="text-xs text-gray-600">"{transcript}"</span>}
          {lastIntent && <span className="text-xs text-purple-500">intent: {lastIntent}</span>}
          {voiceError && <span className="text-xs text-red-400">{voiceError}</span>}
        </div>
        {cmdMsg && <div className="text-xs">{cmdMsg}</div>}
        <p className="text-[10px] text-gray-500">
          支持中文 / 英文。识别会自动发到 <code>/api/voice/command</code>，loop / next / emergency_stop / 切歌 / 加花 都可。
        </p>
      </section>
    </div>
  )
}
