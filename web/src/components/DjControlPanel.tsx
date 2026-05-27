import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from '../api/client'
import type { DjStyle, DjScoredSong, DjSequenceEntry, DjTransitionRule, DjFxItem } from '../api/client'
import { useMusicStore } from '../store/useMusicStore'

type Tab = 'pick' | 'sequence' | 'transitions' | 'cut' | 'fx'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'pick', label: '舞种推荐', icon: '🎯' },
  { id: 'sequence', label: '能量编排', icon: '📈' },
  { id: 'transitions', label: '混音规则', icon: '🎚️' },
  { id: 'cut', label: '现场切歌', icon: '✂️' },
  { id: 'fx', label: 'DJ 加花', icon: '🔊' },
]

export default function DjControlPanel() {
  const [tab, setTab] = useState<Tab>('pick')

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-surface-light street-sticker md:rounded-[10px] p-3 sm:p-4">
      <div className="flex items-center gap-2 sm:gap-3 mb-3 flex-wrap">
        <span className="text-2xl">🎛️</span>
        <div className="street-title text-xl sm:text-2xl leading-none">DJ Control</div>
      </div>
      <div className="flex gap-2 mb-3 flex-wrap">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 text-xs sm:text-sm font-semibold rounded-md ${
              tab === t.id ? 'bg-primary text-black' : 'bg-surface-lighter'
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto pr-1">
        {tab === 'pick' && <PickByStyle />}
        {tab === 'sequence' && <SequenceByEnergy />}
        {tab === 'transitions' && <TransitionRules />}
        {tab === 'cut' && <CutStrategies />}
        {tab === 'fx' && <FxPad />}
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Tab: 舞种推荐
// --------------------------------------------------------------------------- //
function PickByStyle() {
  const [styles, setStyles] = useState<DjStyle[]>([])
  const [style, setStyle] = useState<string>('')
  const [minutes, setMinutes] = useState(5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{
    achieved_duration_sec: number
    songs: DjScoredSong[]
  } | null>(null)

  useEffect(() => {
    api.djListStyles().then(d => {
      setStyles(d.styles)
      if (d.styles.length && !style) setStyle(d.styles[0].key)
    }).catch(e => setError(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function run() {
    setLoading(true); setError(null); setResult(null)
    try {
      const data = await api.djPickByStyle(style, minutes * 60)
      setResult({ achieved_duration_sec: data.achieved_duration_sec, songs: data.songs })
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs street-subtitle">
        基于已分析特征（BPM、Beat、Downbeat、能量、Phrase 长度）评分，并按 BPM 桶分散，避免雷同。
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <div className="text-xs street-subtitle mb-1">舞种</div>
          <select value={style} onChange={e => setStyle(e.target.value)} className="px-2 py-1.5 text-sm bg-surface-lighter rounded-md">
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
            className="w-24 px-2 py-1.5 text-sm bg-surface-lighter rounded-md" />
        </div>
        <button onClick={run} disabled={loading || !style}
          className="bg-primary text-black px-4 py-1.5 text-sm font-bold rounded-md disabled:opacity-50">
          {loading ? '推荐中...' : '生成歌单'}
        </button>
      </div>
      {error && <div className="text-xs text-red-400">错误：{error}</div>}
      {result && (
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="text-xs street-subtitle mb-2">
            命中 {result.songs.length} 首 · 累计 {fmt(result.achieved_duration_sec)}
          </div>
          <table className="w-full text-xs sm:text-sm">
            <thead>
              <tr className="text-left street-subtitle">
                <th className="py-1">#</th><th>歌曲</th><th>BPM</th>
                <th className="hidden sm:table-cell">能量</th>
                <th>评分</th>
              </tr>
            </thead>
            <tbody>
              {result.songs.map((s, i) => (
                <tr key={s.song_id} className="border-t border-white/5">
                  <td className="py-1">{i + 1}</td>
                  <td className="py-1">
                    <div className="font-semibold truncate">{s.title}</div>
                    <div className="text-[10px] street-subtitle truncate">{s.artist}</div>
                  </td>
                  <td className="py-1">{s.bpm?.toFixed(1) ?? '-'}</td>
                  <td className="py-1 hidden sm:table-cell">{s.energy?.toFixed(2) ?? '-'}</td>
                  <td className="py-1">{(s.score * 100).toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Tab: 能量编排
// --------------------------------------------------------------------------- //
function SequenceByEnergy() {
  const { songs, loadSongs } = useMusicStore()
  const [presets, setPresets] = useState<string[]>([])
  const [preset, setPreset] = useState('warmup_to_peak')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sequence, setSequence] = useState<DjSequenceEntry[]>([])

  useEffect(() => {
    if (!songs.length) loadSongs()
    api.djListSequencePresets().then(d => {
      setPresets(d.presets)
      if (d.presets.length) setPreset(d.presets[0])
    }).catch(e => setError(String(e)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const songsById = useMemo(() => Object.fromEntries(songs.map(s => [s.id, s])), [songs])

  function toggle(id: string) {
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  async function run() {
    if (selectedIds.length < 2) { setError('至少选 2 首'); return }
    setLoading(true); setError(null); setSequence([])
    try {
      const data = await api.djSequence(selectedIds, preset)
      setSequence(data.sequence)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs street-subtitle">
        按预设能量曲线（暖场上升 / 波浪 / 起伏 / 对垒）给入选歌曲排序，能量按街舞 DJ 配方计算（kick_punch / snare_crack / groove_tightness / low_mid_density / vocal_urgency / tempo）。
      </div>
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <div className="text-xs street-subtitle mb-1">能量曲线</div>
          <select value={preset} onChange={e => setPreset(e.target.value)} className="px-2 py-1.5 text-sm bg-surface-lighter rounded-md">
            {presets.map(p => <option key={p} value={p}>{labelPreset(p)}</option>)}
          </select>
        </div>
        <button onClick={run} disabled={loading || selectedIds.length < 2}
          className="bg-primary text-black px-4 py-1.5 text-sm font-bold rounded-md disabled:opacity-50">
          {loading ? '排序中...' : `编排 (${selectedIds.length})`}
        </button>
        {selectedIds.length > 0 && (
          <button onClick={() => setSelectedIds([])} className="text-xs bg-surface-lighter px-3 py-1.5 rounded-md">清空选择</button>
        )}
      </div>
      {error && <div className="text-xs text-red-400">错误：{error}</div>}

      <div className="grid sm:grid-cols-2 gap-3">
        <div className="bg-surface-lighter rounded-md p-2">
          <div className="text-xs street-subtitle mb-1">从曲库选择</div>
          <div className="max-h-64 overflow-y-auto">
            {songs.map(s => (
              <label key={s.id} className="flex items-center gap-2 text-xs sm:text-sm py-1 border-t border-white/5">
                <input type="checkbox" checked={selectedIds.includes(s.id)} onChange={() => toggle(s.id)} />
                <span className="flex-1 truncate">{s.title} <span className="text-[10px] street-subtitle">{s.artist}</span></span>
                <span className="text-[10px] street-subtitle">{s.bpm ? s.bpm.toFixed(0) : '-'}</span>
              </label>
            ))}
            {songs.length === 0 && <div className="text-xs street-subtitle py-2">曲库为空</div>}
          </div>
        </div>
        <div className="bg-surface-lighter rounded-md p-2">
          <div className="text-xs street-subtitle mb-1">编排结果</div>
          {sequence.length === 0 && <div className="text-xs street-subtitle">未生成</div>}
          {sequence.map(entry => {
            const song = songsById[entry.song_id]
            const bar = Math.round(entry.actual_energy * 100)
            return (
              <div key={entry.song_id} className="py-1 border-t border-white/5">
                <div className="flex items-center justify-between text-xs">
                  <span className="truncate">#{entry.position + 1} {song?.title ?? entry.song_id}</span>
                  <span className="street-subtitle">tgt {(entry.target_energy * 100).toFixed(0)} / act {bar}</span>
                </div>
                <div className="h-1.5 bg-black/40 rounded mt-1 overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${bar}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function labelPreset(p: string) {
  return ({
    warmup_to_peak: '暖场上升 (Warm-up → Peak)',
    wave: '波浪 (Wave)',
    rise_fall: '起伏 (Rise & Fall)',
    battle: '对垒 (Battle)',
  } as Record<string, string>)[p] || p
}

// --------------------------------------------------------------------------- //
// Tab: 混音规则
// --------------------------------------------------------------------------- //
function TransitionRules() {
  const [rules, setRules] = useState<{ analyzed: DjTransitionRule[]; raw: DjTransitionRule[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.djListTransitionRules().then(setRules).catch(e => setError(String(e)))
  }, [])
  if (error) return <div className="text-xs text-red-400">错误：{error}</div>
  if (!rules) return <div className="text-xs street-subtitle">加载中...</div>
  return (
    <div className="space-y-4">
      <div className="text-xs street-subtitle">
        11 种「已分析过渡」需要两首歌都完成分析（BPM/Beat/Phrase），由后端依据相位与 Stems 自动生成衔接 spec；7 种「原生过渡」仅依赖时间线，不要求分析。
      </div>
      <div>
        <div className="text-sm font-bold mb-2">分析型过渡（{rules.analyzed.length}）</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {rules.analyzed.map(r => (
            <div key={r.key} className="bg-surface-lighter rounded-md px-3 py-2 text-xs sm:text-sm">
              <div className="font-semibold">{r.label_zh}</div>
              <div className="text-[10px] street-subtitle">{r.key}</div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="text-sm font-bold mb-2">原生过渡（{rules.raw.length}）</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {rules.raw.map(r => (
            <div key={r.key} className="bg-surface-lighter rounded-md px-3 py-2 text-xs sm:text-sm">
              <div className="font-semibold">{r.label_zh}</div>
              <div className="text-[10px] street-subtitle">{r.key}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Tab: 现场切歌
// --------------------------------------------------------------------------- //
function CutStrategies() {
  return (
    <div className="space-y-3 text-xs sm:text-sm">
      <div className="street-subtitle">三种现场切歌策略（由后端 <code>/api/dj/cut/plan</code> 计算）：</div>
      <div className="grid sm:grid-cols-3 gap-2">
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="font-bold mb-1">快切 fast_cut</div>
          <div className="text-[11px] street-subtitle">5 秒内寻找下一个 downbeat → beat → 1 小节边界，硬切到队列下一首。</div>
        </div>
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="font-bold mb-1">升能量切 energy_up_cut</div>
          <div className="text-[11px] street-subtitle">从 pool 中挑选能量明显高于当前 next 的候选替换，随后执行快切。</div>
        </div>
        <div className="bg-surface-lighter rounded-md p-3">
          <div className="font-bold mb-1">降能量切 energy_down_cut</div>
          <div className="text-[11px] street-subtitle">相反方向，挑选明显更低的候选，用于让 cypher 喘口气。</div>
        </div>
      </div>
      <div className="text-[11px] street-subtitle">实时调用需要现场播放器把 current_song_id / cursor_sec / queue_song_ids 传给 <code>POST /api/dj/cut/plan</code>。</div>
    </div>
  )
}

// --------------------------------------------------------------------------- //
// Tab: DJ 加花
// --------------------------------------------------------------------------- //
function FxPad() {
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
  return (
    <div className="space-y-3">
      <div className="text-xs street-subtitle">
        所有 FX 由后端 numpy 实时合成 mono PCM WAV（无样本库依赖），点按试听。
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {items.map(fx => (
          <button key={fx.key} onClick={() => play(fx.key)}
            className="bg-surface-lighter hover:bg-primary hover:text-black active:bg-primary/80 rounded-md p-4 text-left transition-colors">
            <div className="text-2xl mb-1">{iconFor(fx.key)}</div>
            <div className="font-bold text-sm">{fx.label_zh}</div>
            <div className="text-[10px] street-subtitle">{fx.key} · {fx.default_duration.toFixed(2)}s</div>
          </button>
        ))}
      </div>
    </div>
  )
}

function iconFor(key: string) {
  return ({
    scratch_chirp: '🎚️', air_horn: '📯', snare_crack: '🥁',
    kick_roll: '🦶', rewind_zip: '⏪', cymbal_swell: '💥', vinyl_stop: '🛑',
  } as Record<string, string>)[key] || '🔊'
}

function fmt(sec: number) {
  const m = Math.floor(sec / 60), s = Math.round(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
