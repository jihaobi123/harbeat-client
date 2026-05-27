import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from '../api/client'
import type {
  DjStyle, DjScoredSong, DjSequenceEntry, DjSequencePreset,
  DjTransitionRule, DjFxItem,
} from '../api/client'
import { useMusicStore } from '../store/useMusicStore'
import { useAuthStore } from '../store/useAuthStore'
import type { LibrarySong, Playlist } from '../types'

// =========================================================================== //
// 5-step DJ wizard:
//   1) 选歌  — 三种来源（导入歌单 / Vibe 关键词 / 舞种风格 + 时长）
//   2) 排歌  — 按街舞场景能量曲线排序
//   3) 混音  — 复用 7+11 现有混音方案
//   4) 切歌  — 三种现场切歌策略
//   5) 加花  — 街舞 DJ 现场音效
// =========================================================================== //

type StepId = 1 | 2 | 3 | 4 | 5

const STEPS: { id: StepId; label: string; icon: string }[] = [
  { id: 1, label: '选歌', icon: '🎯' },
  { id: 2, label: '排歌', icon: '📈' },
  { id: 3, label: '混音', icon: '🎚️' },
  { id: 4, label: '切歌', icon: '✂️' },
  { id: 5, label: '加花', icon: '🔊' },
]

export default function DjControlPanel() {
  const [step, setStep] = useState<StepId>(1)
  // Shared wizard state: songs picked → sequenced → ready for mix
  const [picked, setPicked] = useState<LibrarySong[]>([])
  const [sequence, setSequence] = useState<DjSequenceEntry[]>([])

  function next() { if (step < 5) setStep((step + 1) as StepId) }
  function prev() { if (step > 1) setStep((step - 1) as StepId) }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-surface-light street-sticker md:rounded-[10px] p-3 sm:p-4">
      <div className="flex items-center gap-2 sm:gap-3 mb-3 flex-wrap">
        <span className="text-2xl">🎛️</span>
        <div className="street-title text-xl sm:text-2xl leading-none">DJ Control · 5 步打歌单</div>
      </div>

      <Stepper step={step} onJump={setStep} pickedCount={picked.length} sequencedCount={sequence.length} />

      <div className="flex-1 overflow-y-auto pr-1 mt-3">
        {step === 1 && (
          <Step1Pick
            picked={picked}
            setPicked={setPicked}
            onSequenceInvalidate={() => setSequence([])}
          />
        )}
        {step === 2 && (
          <Step2Sequence
            picked={picked}
            sequence={sequence}
            setSequence={setSequence}
          />
        )}
        {step === 3 && <Step3Mix sequence={sequence} picked={picked} />}
        {step === 4 && <Step4Cut />}
        {step === 5 && <Step5Fx />}
      </div>

      <div className="flex items-center justify-between gap-3 mt-3 pt-3 border-t border-white/10">
        <button onClick={prev} disabled={step === 1}
          className="bg-surface-lighter px-4 py-1.5 text-sm font-semibold rounded-md disabled:opacity-40">
          ← 上一步
        </button>
        <div className="text-xs street-subtitle">
          已选 {picked.length} 首 · {sequence.length > 0 ? `已排序 ${sequence.length}` : '未排序'}
        </div>
        <button onClick={next} disabled={step === 5}
          className="bg-primary text-black px-4 py-1.5 text-sm font-bold rounded-md disabled:opacity-40">
          下一步 →
        </button>
      </div>
    </div>
  )
}

function Stepper({ step, onJump, pickedCount, sequencedCount }: {
  step: StepId; onJump: (s: StepId) => void; pickedCount: number; sequencedCount: number
}) {
  return (
    <div className="flex items-center gap-1 sm:gap-2 flex-wrap">
      {STEPS.map((s, i) => {
        const active = step === s.id
        const done = step > s.id
        // Disable jumping forward past completed gates
        const reachable = s.id === 1 || (s.id === 2 && pickedCount >= 2) || (s.id >= 3 && sequencedCount > 0) || done
        return (
          <div key={s.id} className="flex items-center">
            <button
              onClick={() => reachable && onJump(s.id)}
              disabled={!reachable}
              className={`px-3 py-1.5 rounded-md text-xs sm:text-sm font-semibold whitespace-nowrap transition-colors ${
                active ? 'bg-primary text-black' :
                done ? 'bg-primary/40 text-white' :
                reachable ? 'bg-surface-lighter hover:bg-surface' : 'bg-surface-lighter/40 opacity-50'
              }`}>
              {s.icon} 第{s.id}步 · {s.label}
            </button>
            {i < STEPS.length - 1 && <span className="px-1 text-white/30">›</span>}
          </div>
        )
      })}
    </div>
  )
}

// =========================================================================== //
// Step 1 — 选歌（三种来源）
// =========================================================================== //
type PickMode = 'import' | 'vibe' | 'style'

function Step1Pick({ picked, setPicked, onSequenceInvalidate }: {
  picked: LibrarySong[]
  setPicked: (s: LibrarySong[]) => void
  onSequenceInvalidate: () => void
}) {
  const [mode, setMode] = useState<PickMode>('style')
  const { songs, loadSongs } = useMusicStore()
  useEffect(() => { if (!songs.length) loadSongs() /* eslint-disable-line */ }, [])

  function add(items: LibrarySong[]) {
    const map = new Map(picked.map(s => [s.id, s]))
    items.forEach(s => map.set(s.id, s))
    setPicked(Array.from(map.values()))
    onSequenceInvalidate()
  }
  function remove(id: string) {
    setPicked(picked.filter(s => s.id !== id))
    onSequenceInvalidate()
  }
  function clear() { setPicked([]); onSequenceInvalidate() }

  return (
    <div className="space-y-3">
      <div className="text-xs street-subtitle leading-relaxed">
        把候选歌曲加入下方「已选池」。三种来源可叠加：导入用户歌单、Vibe 关键词、按舞种自动出歌（含目标时长）。
      </div>

      <div className="flex gap-2 flex-wrap">
        {([
          { id: 'import', label: '📥 导入歌单' },
          { id: 'vibe', label: '🔍 Vibe 关键词' },
          { id: 'style', label: '🎭 舞种 + 时长' },
        ] as { id: PickMode; label: string }[]).map(m => (
          <button key={m.id} onClick={() => setMode(m.id)}
            className={`px-3 py-1.5 text-xs sm:text-sm font-semibold rounded-md ${
              mode === m.id ? 'bg-primary text-black' : 'bg-surface-lighter'
            }`}>
            {m.label}
          </button>
        ))}
      </div>

      {mode === 'import' && <ImportSource library={songs} onAdd={add} />}
      {mode === 'vibe' && <VibeSource library={songs} onAdd={add} />}
      {mode === 'style' && <StyleSource library={songs} onAdd={add} />}

      <div className="bg-surface-lighter rounded-md p-3">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-bold">已选池（{picked.length}）</div>
          {picked.length > 0 && (
            <button onClick={clear} className="text-xs bg-surface px-2 py-1 rounded-md">清空</button>
          )}
        </div>
        {picked.length === 0 && <div className="text-xs street-subtitle">还没选歌</div>}
        <div className="max-h-56 overflow-y-auto">
          {picked.map((s, i) => (
            <div key={s.id} className="flex items-center justify-between py-1 border-t border-white/5 text-xs sm:text-sm">
              <div className="flex-1 truncate">
                <span className="street-subtitle mr-2">#{i + 1}</span>
                <span className="font-semibold">{s.title}</span>
                <span className="street-subtitle ml-2">{s.artist}</span>
              </div>
              <div className="street-subtitle text-[11px] mr-2">{s.bpm ? `${s.bpm.toFixed(0)} BPM` : '-'}</div>
              <button onClick={() => remove(s.id)} className="text-red-300 text-xs px-2">×</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ImportSource({ library, onAdd }: { library: LibrarySong[]; onAdd: (s: LibrarySong[]) => void }) {
  const user = useAuthStore(s => s.user)
  const { playlists, loadPlaylists } = useMusicStore()
  const [selectedPid, setSelectedPid] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => { if (user && playlists.length === 0) loadPlaylists(user.id) /* eslint-disable-line */ }, [user])

  async function importPlaylist() {
    if (!selectedPid) return
    setPending(true); setMsg(null)
    try {
      const detail = await api.getPlaylistDetail(selectedPid)
      // intersect with library by title+artist
      const libKey = new Map(library.map(s => [`${s.title}|${s.artist}`.toLowerCase(), s]))
      const matched: LibrarySong[] = []
      for (const ps of detail.songs) {
        const hit = libKey.get(`${ps.title}|${ps.artist}`.toLowerCase())
        if (hit) matched.push(hit)
      }
      onAdd(matched)
      setMsg(`从「${detail.playlist_name}」匹配 ${matched.length} / ${detail.songs.length} 首到曲库`)
    } catch (e) { setMsg(String(e)) }
    finally { setPending(false) }
  }

  return (
    <div className="bg-surface-lighter rounded-md p-3 space-y-2">
      <div className="text-xs street-subtitle">导入用户歌单，把命中曲库的歌加入「已选池」。</div>
      <div className="flex flex-wrap gap-2 items-end">
        <select value={selectedPid ?? ''} onChange={e => setSelectedPid(Number(e.target.value) || null)}
          className="px-2 py-1.5 text-sm bg-surface rounded-md min-w-[180px]">
          <option value="">— 选择歌单 —</option>
          {playlists.map((p: Playlist) => (
            <option key={p.id} value={p.id}>{p.playlist_name}（{p.song_count}）</option>
          ))}
        </select>
        <button onClick={importPlaylist} disabled={!selectedPid || pending}
          className="bg-primary text-black px-3 py-1.5 text-sm font-bold rounded-md disabled:opacity-50">
          {pending ? '导入中...' : '导入'}
        </button>
      </div>
      {msg && <div className="text-xs street-subtitle">{msg}</div>}
    </div>
  )
}

function VibeSource({ library, onAdd }: { library: LibrarySong[]; onAdd: (s: LibrarySong[]) => void }) {
  const [q, setQ] = useState('')
  const matched = useMemo(() => {
    if (!q.trim()) return []
    const kw = q.toLowerCase().split(/\s+/).filter(Boolean)
    return library.filter(s => {
      const hay = `${s.title} ${s.artist}`.toLowerCase()
      return kw.every(k => hay.includes(k))
    })
  }, [q, library])
  return (
    <div className="bg-surface-lighter rounded-md p-3 space-y-2">
      <div className="text-xs street-subtitle">在曲库中按关键词（标题 / 艺人 / 标签）做 Vibe 命中。多个关键词空格分隔，AND 匹配。</div>
      <div className="flex gap-2">
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="例如：boom bap dark"
          className="flex-1 px-2 py-1.5 text-sm bg-surface rounded-md" />
        <button onClick={() => onAdd(matched)} disabled={matched.length === 0}
          className="bg-primary text-black px-3 py-1.5 text-sm font-bold rounded-md disabled:opacity-50">
          加入 {matched.length} 首
        </button>
      </div>
      <div className="max-h-44 overflow-y-auto">
        {matched.slice(0, 50).map(s => (
          <div key={s.id} className="text-xs py-0.5 border-t border-white/5 truncate">
            {s.title} <span className="street-subtitle">— {s.artist}</span>
          </div>
        ))}
        {q && matched.length === 0 && <div className="text-xs street-subtitle py-1">无命中</div>}
      </div>
    </div>
  )
}

function StyleSource({ library, onAdd }: { library: LibrarySong[]; onAdd: (s: LibrarySong[]) => void }) {
  const [styles, setStyles] = useState<DjStyle[]>([])
  const [style, setStyle] = useState('')
  const [minutes, setMinutes] = useState(8)
  const [pending, setPending] = useState(false)
  const [picked, setPicked] = useState<DjScoredSong[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.djListStyles().then(d => {
      setStyles(d.styles)
      if (d.styles.length && !style) setStyle(d.styles[0].key)
    }).catch(e => setError(String(e)))
    // eslint-disable-next-line
  }, [])

  async function run() {
    setPending(true); setError(null); setPicked([])
    try {
      const r = await api.djPickByStyle(style, minutes * 60)
      setPicked(r.songs)
    } catch (e) { setError(String(e)) } finally { setPending(false) }
  }
  function commit() {
    const byId = new Map(library.map(s => [s.id, s]))
    onAdd(picked.map(p => byId.get(p.song_id)).filter(Boolean) as LibrarySong[])
  }

  return (
    <div className="bg-surface-lighter rounded-md p-3 space-y-2">
      <div className="text-xs street-subtitle">按舞种风格 + 目标时长自动出歌。后端按 BPM 段、能量、Phrase 匹配。</div>
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <div className="text-xs street-subtitle mb-1">舞种</div>
          <select value={style} onChange={e => setStyle(e.target.value)}
            className="px-2 py-1.5 text-sm bg-surface rounded-md">
            {styles.map(s => (
              <option key={s.key} value={s.key}>
                {s.label_zh}（{s.bpm_range[0]}–{s.bpm_range[1]} BPM）
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="text-xs street-subtitle mb-1">目标时长（分钟）</div>
          <input type="number" min={1} max={120} value={minutes}
            onChange={e => setMinutes(Math.max(1, Number(e.target.value) || 1))}
            className="w-24 px-2 py-1.5 text-sm bg-surface rounded-md" />
        </div>
        <button onClick={run} disabled={pending || !style}
          className="bg-primary text-black px-3 py-1.5 text-sm font-bold rounded-md disabled:opacity-50">
          {pending ? '生成中...' : '生成候选'}
        </button>
        {picked.length > 0 && (
          <button onClick={commit} className="bg-primary/70 text-black px-3 py-1.5 text-sm font-bold rounded-md">
            全部加入 ({picked.length})
          </button>
        )}
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="max-h-48 overflow-y-auto">
        {picked.map((s, i) => (
          <div key={s.song_id} className="flex items-center text-xs py-0.5 border-t border-white/5">
            <span className="street-subtitle w-6">#{i + 1}</span>
            <span className="flex-1 truncate">{s.title} <span className="street-subtitle">— {s.artist}</span></span>
            <span className="street-subtitle w-14 text-right">{s.bpm?.toFixed(0) ?? '-'} BPM</span>
            <span className="street-subtitle w-14 text-right">{(s.score * 100).toFixed(0)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// =========================================================================== //
// Step 2 — 排歌（街舞能量曲线）
// =========================================================================== //
function Step2Sequence({ picked, sequence, setSequence }: {
  picked: LibrarySong[]
  sequence: DjSequenceEntry[]
  setSequence: (s: DjSequenceEntry[]) => void
}) {
  const [presets, setPresets] = useState<DjSequencePreset[]>([])
  const [preset, setPreset] = useState('battle_4rounds')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.djListSequencePresets().then(d => {
      const meta = d.meta || d.presets.map(k => ({ key: k, label_zh: k, desc_zh: '', scene: 'generic' }))
      setPresets(meta)
    }).catch(e => setError(String(e)))
  }, [])

  async function run() {
    if (picked.length < 2) { setError('至少选 2 首才能排序'); return }
    setPending(true); setError(null)
    try {
      const r = await api.djSequence(picked.map(s => s.id), preset)
      setSequence(r.sequence)
    } catch (e) { setError(String(e)) } finally { setPending(false) }
  }

  const byId = useMemo(() => Object.fromEntries(picked.map(s => [s.id, s])), [picked])
  const current = presets.find(p => p.key === preset)

  return (
    <div className="space-y-3">
      <div className="text-xs street-subtitle leading-relaxed">
        能量值按街舞 DJ 配方实时计算（kick_punch · snare_crack · groove_tightness · low_mid_density · vocal_urgency · tempo），并按所选曲线贪心分配每一首歌的位置。
      </div>

      <div>
        <div className="text-xs street-subtitle mb-1">能量曲线（街舞场景预设）</div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {presets.map(p => {
            const active = p.key === preset
            return (
              <button key={p.key} onClick={() => setPreset(p.key)}
                className={`text-left p-2 rounded-md transition-colors ${active ? 'bg-primary text-black' : 'bg-surface-lighter hover:bg-surface'}`}>
                <div className="text-xs font-bold flex items-center gap-1">
                  {sceneIcon(p.scene)} {p.label_zh}
                </div>
                <div className={`text-[10px] mt-0.5 ${active ? 'opacity-80' : 'street-subtitle'}`}>{p.desc_zh}</div>
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button onClick={run} disabled={pending || picked.length < 2}
          className="bg-primary text-black px-4 py-1.5 text-sm font-bold rounded-md disabled:opacity-50">
          {pending ? '排序中...' : `按曲线排序 ${picked.length} 首`}
        </button>
        {current && (
          <span className="text-xs street-subtitle">当前：{current.label_zh}</span>
        )}
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}

      {sequence.length > 0 && (
        <div className="bg-surface-lighter rounded-md p-3 space-y-1">
          <div className="text-xs street-subtitle mb-1">排序结果 — 目标/实际能量对比</div>
          {sequence.map(entry => {
            const song = byId[entry.song_id]
            const act = Math.round(entry.actual_energy * 100)
            const tgt = Math.round(entry.target_energy * 100)
            return (
              <div key={entry.song_id} className="py-1 border-t border-white/5">
                <div className="flex items-center justify-between text-xs">
                  <span className="truncate">
                    <b>#{entry.position + 1}</b> {song?.title ?? entry.song_id}
                    {song && <span className="street-subtitle ml-2">{song.artist}</span>}
                  </span>
                  <span className="street-subtitle">tgt {tgt} · act {act}</span>
                </div>
                <div className="relative h-2 bg-black/40 rounded mt-1 overflow-hidden">
                  <div className="absolute inset-y-0 left-0 bg-primary" style={{ width: `${act}%` }} />
                  <div className="absolute inset-y-0 w-[2px] bg-white/80" style={{ left: `${tgt}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function sceneIcon(scene: string) {
  return ({
    battle: '🥊', cypher: '🌀', class: '🎓', showcase: '🎬', generic: '🎵',
  } as Record<string, string>)[scene] || '🎵'
}

// =========================================================================== //
// Step 3 — 混音（7+11 现有方案）
// =========================================================================== //
function Step3Mix({ sequence, picked }: { sequence: DjSequenceEntry[]; picked: LibrarySong[] }) {
  const [rules, setRules] = useState<{ analyzed: DjTransitionRule[]; raw: DjTransitionRule[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.djListTransitionRules().then(setRules).catch(e => setError(String(e)))
  }, [])
  const byId = useMemo(() => Object.fromEntries(picked.map(s => [s.id, s])), [picked])

  return (
    <div className="space-y-4">
      <div className="text-xs street-subtitle leading-relaxed">
        混音采用现有 <b>7 原生 + 11 分析型</b> 方案。分析型需两首歌都完成 BPM/Beat/Phrase 分析。下方为本歌单相邻两首的 BPM/Key 一致性提示，可作为选规则参考。
      </div>

      {sequence.length >= 2 && (
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="text-sm font-bold mb-2">本歌单相邻过渡（{sequence.length - 1} 段）</div>
          {sequence.slice(0, -1).map((cur, i) => {
            const nxt = sequence[i + 1]
            const a = byId[cur.song_id]
            const b = byId[nxt.song_id]
            const bpmDiff = (a?.bpm && b?.bpm) ? Math.abs(a.bpm - b.bpm) : null
            const tag = bpmDiff == null ? '—'
              : bpmDiff <= 3 ? '完美吻合' : bpmDiff <= 8 ? '可拉伸混' : bpmDiff <= 16 ? '建议加 FX 衔接' : '建议硬切 / Rewind'
            return (
              <div key={i} className="flex items-center justify-between text-xs py-1 border-t border-white/5">
                <div className="truncate flex-1">
                  <span className="street-subtitle">#{i + 1}→#{i + 2}</span>{' '}
                  <span className="font-semibold">{a?.title}</span>
                  <span className="street-subtitle"> → </span>
                  <span className="font-semibold">{b?.title}</span>
                </div>
                <div className="street-subtitle text-[11px] ml-2 whitespace-nowrap">
                  Δ{bpmDiff?.toFixed(1) ?? '?'} BPM · {tag}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {error && <div className="text-xs text-red-400">{error}</div>}
      {rules && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <div className="text-sm font-bold mb-2">分析型过渡（{rules.analyzed.length}）</div>
            <div className="grid grid-cols-2 gap-2">
              {rules.analyzed.map(r => (
                <div key={r.key} className="bg-surface-lighter rounded-md px-3 py-2 text-xs">
                  <div className="font-semibold">{r.label_zh}</div>
                  <div className="text-[10px] street-subtitle">{r.key}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="text-sm font-bold mb-2">原生过渡（{rules.raw.length}）</div>
            <div className="grid grid-cols-2 gap-2">
              {rules.raw.map(r => (
                <div key={r.key} className="bg-surface-lighter rounded-md px-3 py-2 text-xs">
                  <div className="font-semibold">{r.label_zh}</div>
                  <div className="text-[10px] street-subtitle">{r.key}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// =========================================================================== //
// Step 4 — 切歌
// =========================================================================== //
function Step4Cut() {
  return (
    <div className="space-y-3 text-xs sm:text-sm">
      <div className="street-subtitle leading-relaxed">
        三种现场切歌策略，对应 cypher / battle 现场不同情境，由 <code>POST /api/dj/cut/plan</code> 计算下一个 downbeat 边界并给出衔接 spec。
      </div>
      <div className="grid sm:grid-cols-3 gap-2">
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="font-bold mb-1">⚡ 快切 fast_cut</div>
          <div className="text-[11px] street-subtitle">5 秒内寻找下一个 downbeat → beat → 1 小节边界，硬切到队列下一首。适合 freeze 时刻。</div>
        </div>
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="font-bold mb-1">🔥 升能量切 energy_up_cut</div>
          <div className="text-[11px] street-subtitle">从 pool 中挑选能量明显高于队列下一首的候选并替换，随后快切。冲峰 / 喊大招用。</div>
        </div>
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="font-bold mb-1">❄️ 降能量切 energy_down_cut</div>
          <div className="text-[11px] street-subtitle">挑选明显更低的候选，让 cypher 喘口气，留白后再起。</div>
        </div>
      </div>
      <div className="text-[11px] street-subtitle">实时调用：把 current_song_id / cursor_sec / queue / pool 传给 <code>POST /api/dj/cut/plan</code>。</div>
    </div>
  )
}

// =========================================================================== //
// Step 5 — 加花（街舞 DJ FX）
// =========================================================================== //
function Step5Fx() {
  const [items, setItems] = useState<DjFxItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    api.djListFx().then(d => setItems(d.fx)).catch(e => setError(String(e)))
  }, [])

  function play(key: string) {
    const url = api.djFxAudioUrl(key)
    if (!audioRef.current) audioRef.current = new Audio()
    audioRef.current.src = url
    audioRef.current.play().catch(() => {})
  }

  if (error) return <div className="text-xs text-red-400">错误：{error}</div>

  // group by category
  const groups: Record<string, DjFxItem[]> = {}
  for (const it of items) {
    const g = it.category || 'accent'
    if (!groups[g]) groups[g] = []
    groups[g].push(it)
  }
  const order: { key: string; title: string }[] = [
    { key: 'hype', title: '🚨 喊场 / 起势' },
    { key: 'drop', title: '💥 Drop / Build' },
    { key: 'scratch', title: '🎚️ 搓碟 Scratch' },
    { key: 'drum', title: '🥁 鼓点 Stab' },
    { key: 'accent', title: '⚡ 单点强调' },
  ]

  return (
    <div className="space-y-4">
      <div className="text-xs street-subtitle leading-relaxed">
        街舞 DJ 现场常用音效。全部由后端 numpy 实时合成 mono PCM WAV，无样本库依赖。点按试听。
      </div>
      {order.filter(o => groups[o.key]?.length).map(grp => (
        <div key={grp.key}>
          <div className="text-sm font-bold mb-2">{grp.title}</div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {groups[grp.key].map(fx => (
              <button key={fx.key} onClick={() => play(fx.key)}
                className="bg-surface-lighter hover:bg-primary hover:text-black active:bg-primary/80 rounded-md p-3 text-left transition-colors">
                <div className="text-2xl mb-1">{iconFor(fx.key)}</div>
                <div className="font-bold text-sm">{fx.label_zh}</div>
                <div className="text-[10px] street-subtitle">{fx.key} · {fx.default_duration.toFixed(2)}s</div>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function iconFor(key: string) {
  return ({
    air_horn: '📯', air_horn_burst: '📯', siren: '🚨', reload_cock: '🔫', mc_hype: '🎤',
    scratch_chirp: '🎚️', scratch_transformer: '🤖', scratch_baby: '👶',
    snare_crack: '🥁', kick_roll: '🦶', beat_juggle_stutter: '🎛️',
    bass_drop: '💣', reverse_cymbal: '🌊', cymbal_swell: '💥', rewind_zip: '⏪',
    vinyl_stop: '🛑', laser_zap: '⚡',
  } as Record<string, string>)[key] || '🔊'
}
