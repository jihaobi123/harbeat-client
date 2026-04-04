import { useRef, useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import * as api from '../api/client'
import { getProcessedStreamUrl } from '../api/client'
import type { PracticeTrack } from '../api/client'
import { DANCE_STYLES, DANCE_STYLE_LABELS, DANCE_STYLE_COLORS } from '../types'
import type { DanceStyle, QualityMode, StyleMixResult, DJMixResult, TransitionData } from '../types'
import SeamlessPlayer from './SeamlessPlayer'
import type { SeamlessTrack } from './SeamlessPlayer'

const MODES = [
  { value: 'freeplay', label: '自由练习', desc: '随心所欲，自由练舞' },
  { value: 'cypher', label: 'Cypher', desc: '围圈轮流展示' },
  { value: 'battle', label: 'Battle', desc: '对战模式' },
  { value: 'showcase', label: '表演', desc: '舞台展示' },
  { value: 'training', label: '训练', desc: '系统化训练' },
]

interface SessionEvent {
  type: string
  value?: string
  time: string
}

export default function SessionPanel() {
  const { user } = useAuthStore()
  const { playSong, songs } = useMusicStore()
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [mode, setMode] = useState('freeplay')
  const [events, setEvents] = useState<SessionEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [eventType, setEventType] = useState('')
  const [eventValue, setEventValue] = useState('')
  const [startTime, setStartTime] = useState<Date | null>(null)
  const [elapsed, setElapsed] = useState('')
  const [practiceList, setPracticeList] = useState<PracticeTrack[]>([])
  const [practiceLoading, setPracticeLoading] = useState(false)
  const [practiceDuration, setPracticeDuration] = useState(30)

  // Style mix state
  const [mixStyle, setMixStyle] = useState<DanceStyle>('hiphop')
  const [mixDuration, setMixDuration] = useState(30)
  const [mixQuality, setMixQuality] = useState<QualityMode>('balanced')
  const [mixLoading, setMixLoading] = useState(false)
  const [mixResult, setMixResult] = useState<StyleMixResult | null>(null)
  const [mixError, setMixError] = useState('')
  const [playingTrackId, setPlayingTrackId] = useState<string | null>(null)
  const mixAudioRef = useRef<HTMLAudioElement | null>(null)

  // Seamless player state
  const [seamlessActive, setSeamlessActive] = useState(false)
  const [seamlessTracks, setSeamlessTracks] = useState<SeamlessTrack[]>([])
  const [seamlessKey, setSeamlessKey] = useState(0)

  // DJ Auto-Mix state (DJ.studio Harmonize)
  const [djMode, setDjMode] = useState(false)
  const [djEnergyProfile, setDjEnergyProfile] = useState('journey')
  const [djHarmonicWeight, setDjHarmonicWeight] = useState('balanced')
  const [djTransitionStyle, setDjTransitionStyle] = useState('smooth')
  const [djOverlapBars, setDjOverlapBars] = useState(8)
  const [djResult, setDjResult] = useState<DJMixResult | null>(null)
  const [djLoading, setDjLoading] = useState(false)
  const [djError, setDjError] = useState('')

  const toggleMixPlay = (songId: string, filePath: string) => {
    if (playingTrackId === songId) {
      mixAudioRef.current?.pause()
      setPlayingTrackId(null)
      return
    }
    if (mixAudioRef.current) {
      mixAudioRef.current.pause()
    }
    const audio = new Audio(getProcessedStreamUrl(filePath))
    audio.onended = () => setPlayingTrackId(null)
    audio.onerror = () => setPlayingTrackId(null)
    audio.play()
    mixAudioRef.current = audio
    setPlayingTrackId(songId)
  }

  // Timer for elapsed time
  useState(() => {
    const interval = setInterval(() => {
      if (startTime) {
        const diff = Math.floor((Date.now() - startTime.getTime()) / 1000)
        const m = Math.floor(diff / 60)
        const s = diff % 60
        setElapsed(`${m}:${s.toString().padStart(2, '0')}`)
      }
    }, 1000)
    return () => clearInterval(interval)
  })

  const handleStart = async () => {
    if (!user) return
    setLoading(true)
    setError('')
    try {
      const res = await api.startSession(user.id, mode)
      setSessionId(res.session_id)
      setStartTime(new Date())
      setEvents([{ type: 'session_start', value: mode, time: new Date().toLocaleTimeString() }])
    } catch (e: any) {
      setError(e.message || '启动失败')
    } finally {
      setLoading(false)
    }
  }

  const handleLogEvent = async () => {
    if (!sessionId || !eventType.trim()) return
    try {
      await api.logSessionEvent(sessionId, eventType.trim(), eventValue.trim() || undefined)
      setEvents(prev => [...prev, { type: eventType.trim(), value: eventValue.trim() || undefined, time: new Date().toLocaleTimeString() }])
      setEventType('')
      setEventValue('')
    } catch (e: any) {
      setError(e.message || '记录失败')
    }
  }

  const handleEnd = async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      await api.endSession(sessionId)
      setEvents(prev => [...prev, { type: 'session_end', time: new Date().toLocaleTimeString() }])
      setSessionId(null)
      setStartTime(null)
      setElapsed('')
    } catch (e: any) {
      setError(e.message || '结束失败')
    } finally {
      setLoading(false)
    }
  }

  const quickEvents = ['切歌', '暂停', '调整BPM', '切换风格', '即兴solo', '互动']

  const handleGeneratePractice = async () => {
    if (!user) return
    setPracticeLoading(true)
    setError('')
    try {
      const res = await api.generatePracticeList(user.id, practiceDuration)
      setPracticeList(res.tracks)
    } catch (e: any) {
      setError(e.message || '生成失败')
    } finally {
      setPracticeLoading(false)
    }
  }

  const handlePlayPracticeTrack = (track: PracticeTrack) => {
    const song = songs.find(s => s.id === track.id)
    if (song) playSong(song)
  }

  const handleGenerateStyleMix = async () => {
    setMixLoading(true)
    setMixError('')
    setMixResult(null)
    try {
      const res = await api.generateStyleMix({
        style: mixStyle,
        duration_minutes: mixDuration,
        quality_mode: mixQuality,
      })
      setMixResult(res)
    } catch (e: any) {
      setMixError(e.message || '生成失败')
    } finally {
      setMixLoading(false)
    }
  }

  const handleStartSeamless = async () => {
    if (!user || !mixResult) return
    // Stop regular audio player
    useMusicStore.setState({ playingSong: null, isPlaying: false })
    // Stop single-track mix preview
    if (mixAudioRef.current) {
      mixAudioRef.current.pause()
      mixAudioRef.current = null
      setPlayingTrackId(null)
    }
    // Build track list from mix result
    const stracks: SeamlessTrack[] = mixResult.playlist
      .filter(t => !!mixResult.processed_files[t.song_id])
      .map(t => ({
        songId: t.song_id,
        title: t.title,
        artist: t.artist,
        filePath: mixResult.processed_files[t.song_id],
        stemFiles: mixResult.stem_files?.[t.song_id] || undefined,
      }))
    if (!stracks.length) {
      setMixError('没有可播放的处理文件')
      return
    }
    setSeamlessTracks(stracks)
    setSeamlessKey(k => k + 1)
    setSeamlessActive(true)
    // Auto-start session
    if (!sessionId) {
      setLoading(true)
      try {
        const res = await api.startSession(user.id, `seamless_${mixStyle}`)
        setSessionId(res.session_id)
        setStartTime(new Date())
        setEvents([{ type: 'session_start', value: `丝滑播放 ${DANCE_STYLE_LABELS[mixStyle]}`, time: new Date().toLocaleTimeString() }])
      } catch (e: any) {
        setError(e.message || '启动失败')
      } finally {
        setLoading(false)
      }
    }
  }

  const handleGenerateDJMix = async () => {
    setDjLoading(true)
    setDjError('')
    setDjResult(null)
    try {
      const res = await api.generateDJMix({
        style: mixStyle,
        duration_minutes: mixDuration,
        quality_mode: mixQuality,
        energy_profile: djEnergyProfile,
        harmonic_weight: djHarmonicWeight,
        overlap_bars: djOverlapBars,
        transition_style: djTransitionStyle,
      })
      setDjResult(res)
    } catch (e: any) {
      setDjError(e.message || 'DJ排歌失败')
    } finally {
      setDjLoading(false)
    }
  }

  const handleStartDJSeamless = async () => {
    if (!user || !djResult) return
    useMusicStore.setState({ playingSong: null, isPlaying: false })
    if (mixAudioRef.current) {
      mixAudioRef.current.pause()
      mixAudioRef.current = null
      setPlayingTrackId(null)
    }
    const stracks: SeamlessTrack[] = djResult.playlist
      .filter(t => !!djResult.processed_files[t.song_id])
      .map((t, i) => {
        const seg = djResult.segments?.[t.song_id]
        const transition = djResult.transitions.find(tr => tr.to_song_id === t.song_id)
        return {
          songId: t.song_id,
          title: t.title,
          artist: t.artist,
          filePath: djResult.processed_files[t.song_id],
          stemFiles: djResult.stem_files?.[t.song_id] || undefined,
          playStart: seg?.start_sec ?? undefined,
          playEnd: seg?.end_sec ?? undefined,
          transitionIn: transition?.automation ?? undefined,
          overlapSec: transition?.overlap_sec ?? undefined,
        }
      })
    if (!stracks.length) {
      setDjError('没有可播放的处理文件')
      return
    }
    setSeamlessTracks(stracks)
    setSeamlessKey(k => k + 1)
    setSeamlessActive(true)
    if (!sessionId) {
      setLoading(true)
      try {
        const res = await api.startSession(user.id, `dj_mix_${mixStyle}`)
        setSessionId(res.session_id)
        setStartTime(new Date())
        setEvents([{ type: 'session_start', value: `AI DJ ${DANCE_STYLE_LABELS[mixStyle]}`, time: new Date().toLocaleTimeString() }])
      } catch (e: any) {
        setError(e.message || '启动失败')
      } finally {
        setLoading(false)
      }
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      <div className="px-5 py-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-1">🎤 DJ 练舞会话</h2>
        <p className="text-xs text-gray-500">记录你的练舞过程和关键时刻</p>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* 智能练舞歌单生成 */}
        <div className="bg-surface-light rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">🎯 智能练舞歌单</h3>
          <p className="text-xs text-gray-500">基于 Camelot 和谐混音 + BPM 兼容算法，自动编排适合连续练习的歌单</p>
          <div className="flex items-center gap-3">
            <label className="text-xs text-gray-400">目标时长</label>
            <select
              value={practiceDuration}
              onChange={e => setPracticeDuration(Number(e.target.value))}
              className="bg-surface text-white border border-gray-600 rounded-lg px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
            >
              <option value={15}>15 分钟</option>
              <option value={30}>30 分钟</option>
              <option value={45}>45 分钟</option>
              <option value={60}>60 分钟</option>
              <option value={90}>90 分钟</option>
            </select>
            <button
              onClick={handleGeneratePractice}
              disabled={practiceLoading}
              className="bg-primary hover:bg-primary-dark disabled:opacity-50 text-white px-4 py-1.5 rounded-lg text-sm font-medium transition"
            >
              {practiceLoading ? '生成中...' : '生成歌单'}
            </button>
          </div>
          {practiceList.length > 0 && (
            <div className="space-y-1 mt-2">
              <div className="flex items-center gap-3 text-xs text-gray-500 px-2">
                <span className="w-6">#</span>
                <span className="flex-1">歌曲</span>
                <span className="w-16 text-right">BPM</span>
                <span className="w-12 text-right">Key</span>
                <span className="w-14 text-right">能量</span>
              </div>
              {practiceList.map((t, i) => (
                <div
                  key={t.id}
                  className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-surface-lighter cursor-pointer transition"
                  onClick={() => handlePlayPracticeTrack(t)}
                >
                  <span className="w-6 text-xs text-gray-500">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white truncate">{t.title}</div>
                    <div className="text-xs text-gray-500 truncate">{t.artist}</div>
                  </div>
                  <span className="w-16 text-xs text-gray-400 text-right">{t.bpm ? Math.round(t.bpm) : '-'}</span>
                  <span className="w-12 text-xs text-gray-400 text-right">{t.camelot_key || '-'}</span>
                  <span className="w-14 text-xs text-gray-400 text-right">
                    {t.energy != null ? (
                      <span className="inline-block w-full bg-gray-700 rounded-full h-1.5">
                        <span className="block bg-primary rounded-full h-1.5" style={{ width: `${Math.round(t.energy * 100)}%` }} />
                      </span>
                    ) : '-'}
                  </span>
                </div>
              ))}
              <div className="text-xs text-gray-500 pt-2">
                共 {practiceList.length} 首 · 预计 {Math.round(practiceList.reduce((s, t) => s + (t.duration || 180), 0) / 60)} 分钟
              </div>
            </div>
          )}
        </div>

        {/* 🔥 风格化街舞歌单生成 */}
        <div className="bg-surface-light rounded-xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">🔥 街舞风格歌单</h3>
          <p className="text-xs text-gray-500">
            从服务器曲库筛选匹配歌曲，自动处理为指定舞种的街舞成品，生成连续练舞歌单
          </p>

          <div className="space-y-3">
            {/* Style selection */}
            <div>
              <label className="text-[10px] text-gray-500 mb-1 block">目标舞种</label>
              <div className="flex flex-wrap gap-1">
                {DANCE_STYLES.filter(s => s !== 'other').map(style => (
                  <button
                    key={style}
                    onClick={() => setMixStyle(style)}
                    className="px-2 py-0.5 rounded-full text-[11px] font-medium transition"
                    style={{
                      background: mixStyle === style ? (DANCE_STYLE_COLORS[style] || '#64748b') + '33' : 'transparent',
                      color: mixStyle === style ? DANCE_STYLE_COLORS[style] || '#64748b' : '#6b7280',
                      border: `1px solid ${mixStyle === style ? DANCE_STYLE_COLORS[style] || '#64748b' : '#374151'}`,
                    }}
                  >
                    {DANCE_STYLE_LABELS[style]}
                  </button>
                ))}
              </div>
            </div>

            {/* Duration + Quality */}
            <div className="flex items-center gap-3">
              <div>
                <label className="text-[10px] text-gray-500 mb-1 block">目标时长</label>
                <select
                  value={mixDuration}
                  onChange={e => setMixDuration(Number(e.target.value))}
                  className="bg-surface text-white border border-gray-600 rounded-lg px-3 py-1.5 text-sm focus:border-primary focus:outline-none"
                >
                  <option value={15}>15 分钟</option>
                  <option value={30}>30 分钟</option>
                  <option value={45}>45 分钟</option>
                  <option value={60}>60 分钟</option>
                  <option value={90}>90 分钟</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] text-gray-500 mb-1 block">处理质量</label>
                <div className="flex gap-1">
                  {([
                    { v: 'fast' as QualityMode, l: '⚡快' },
                    { v: 'balanced' as QualityMode, l: '⚖️均衡' },
                    { v: 'hq' as QualityMode, l: '💎高' },
                  ]).map(opt => (
                    <button
                      key={opt.v}
                      onClick={() => setMixQuality(opt.v)}
                      className={`px-2 py-1 rounded-lg text-[11px] transition ${
                        mixQuality === opt.v
                          ? 'bg-primary/20 text-primary border border-primary'
                          : 'bg-surface text-gray-500 border border-gray-700'
                      }`}
                    >
                      {opt.l}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Generate button */}
            <button
              onClick={handleGenerateStyleMix}
              disabled={mixLoading}
              className="w-full py-2.5 rounded-lg text-sm font-semibold transition bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 disabled:opacity-50 text-white"
            >
              {mixLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  处理中（可能需要几分钟）...
                </span>
              ) : `🔥 生成 ${DANCE_STYLE_LABELS[mixStyle]} ${mixDuration}分钟歌单`}
            </button>
          </div>

          {/* Error */}
          {mixError && (
            <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-3 py-2 text-red-300 text-xs">{mixError}</div>
          )}

          {/* Results */}
          {mixResult && mixResult.playlist.length > 0 && (
            <div className="space-y-2 mt-2">
              <div className="flex items-center gap-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ background: DANCE_STYLE_COLORS[mixStyle] || '#64748b' }}
                />
                <h4 className="text-xs font-semibold text-white">
                  {DANCE_STYLE_LABELS[mixStyle]} 练舞歌单
                </h4>
                <span className="text-[10px] text-gray-500 ml-auto">
                  共 {mixResult.playlist.length} 首 · 约 {Math.round(mixResult.playlist.reduce((s, t) => s + (t.duration || 180), 0) / 60)} 分钟
                </span>
              </div>

              <div className="space-y-1">
                <div className="flex items-center gap-3 text-[10px] text-gray-500 px-2">
                  <span className="w-6">#</span>
                  <span className="flex-1">歌曲</span>
                  <span className="w-14 text-right">BPM</span>
                  <span className="w-14 text-right">状态</span>
                </div>
                {mixResult.playlist.map((track, i) => {
                  const hasFile = !!mixResult.processed_files[track.song_id]
                  const trackMeta = mixResult.meta[track.song_id]
                  return (
                    <div
                      key={track.song_id}
                      className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-surface-lighter transition"
                    >
                      <span className="w-6 text-xs text-gray-500">{i + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{track.title}</div>
                        <div className="text-[10px] text-gray-500 truncate">{track.artist}</div>
                      </div>
                      <span className="w-14 text-xs text-gray-400 text-right">
                        {track.bpm ? Math.round(track.bpm) : '-'}
                      </span>
                      <span className="w-14 text-right">
                        {hasFile ? (
                          <button
                            onClick={() => toggleMixPlay(String(track.song_id), mixResult.processed_files[track.song_id])}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium transition hover:scale-105"
                            style={{ background: DANCE_STYLE_COLORS[mixStyle] + '33', color: DANCE_STYLE_COLORS[mixStyle] }}
                          >
                            {playingTrackId === String(track.song_id) ? '⏸ 暂停' : '▶ 播放'}
                          </button>
                        ) : (
                          <span className="text-[10px] text-gray-500">—</span>
                        )}
                      </span>
                    </div>
                  )
                })}
              </div>

              {/* Model info */}
              {Object.keys(mixResult.meta).length > 0 && (
                <div className="mt-2 bg-surface rounded-lg p-3">
                  <div className="text-[10px] text-gray-500 mb-1">使用的处理模型</div>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(Object.values(mixResult.meta)[0] || {}).slice(0, 5).map(([k, v]) => (
                      <span key={k} className="text-[9px] bg-surface-lighter px-1.5 py-0.5 rounded text-gray-400">
                        {k}: {String(v).split(':')[0]}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 丝滑连续播放按钮 */}
              <button
                onClick={handleStartSeamless}
                disabled={mixLoading}
                className="w-full py-3 rounded-xl text-sm font-bold transition shadow-lg text-white hover:opacity-90 mt-2"
                style={{
                  background: `linear-gradient(135deg, ${DANCE_STYLE_COLORS[mixStyle] || '#8b5cf6'}, ${DANCE_STYLE_COLORS[mixStyle] || '#8b5cf6'}aa)`,
                }}
              >
                🎵 开始丝滑连续播放
              </button>
            </div>
          )}
        </div>

        {/* 🤖 AI DJ 自动排歌接歌 (DJ.studio Harmonize) */}
        <div className="bg-surface-light rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-white">🤖 AI DJ Harmonize</h3>
              <p className="text-xs text-gray-500 mt-0.5">
                全局最优排歌 (Camelot 调性轮 + BPM + 能量曲线) + 专业 EQ 过渡自动化
              </p>
            </div>
            <button
              onClick={() => setDjMode(!djMode)}
              className={`text-[10px] px-2 py-1 rounded-full transition ${
                djMode ? 'bg-amber-500/20 text-amber-400 border border-amber-500' : 'bg-surface text-gray-500 border border-gray-700'
              }`}
            >
              {djMode ? '收起设置' : '展开设置'}
            </button>
          </div>

          {djMode && (
            <div className="space-y-3">
              {/* Harmonic Weight */}
              <div>
                <label className="text-[10px] text-gray-500 mb-1 block">和声权重</label>
                <div className="flex flex-wrap gap-1">
                  {[
                    { v: 'bpm_first', l: '🎵 BPM优先', d: '节拍匹配为主' },
                    { v: 'key_first', l: '🎹 调性优先', d: 'Camelot和声为主' },
                    { v: 'balanced', l: '⚖️ 均衡', d: 'BPM+调性平衡' },
                  ].map(opt => (
                    <button
                      key={opt.v}
                      onClick={() => setDjHarmonicWeight(opt.v)}
                      className="px-2 py-1 rounded-lg text-[11px] transition"
                      style={{
                        background: djHarmonicWeight === opt.v ? '#3b82f633' : 'transparent',
                        color: djHarmonicWeight === opt.v ? '#3b82f6' : '#6b7280',
                        border: `1px solid ${djHarmonicWeight === opt.v ? '#3b82f6' : '#374151'}`,
                      }}
                      title={opt.d}
                    >
                      {opt.l}
                    </button>
                  ))}
                </div>
              </div>

              {/* Energy Profile */}
              <div>
                <label className="text-[10px] text-gray-500 mb-1 block">能量曲线</label>
                <div className="flex flex-wrap gap-1">
                  {[
                    { v: 'warmup', l: '🔥 暖场', d: '能量递增' },
                    { v: 'peak', l: '⚡ 爆发', d: '持续高能' },
                    { v: 'cooldown', l: '🌙 冷却', d: '能量递减' },
                    { v: 'journey', l: '🎢 旅程', d: '起承转合' },
                    { v: 'free', l: '🎲 自由', d: '不限制' },
                  ].map(opt => (
                    <button
                      key={opt.v}
                      onClick={() => setDjEnergyProfile(opt.v)}
                      className="px-2 py-1 rounded-lg text-[11px] transition"
                      style={{
                        background: djEnergyProfile === opt.v ? '#f59e0b33' : 'transparent',
                        color: djEnergyProfile === opt.v ? '#f59e0b' : '#6b7280',
                        border: `1px solid ${djEnergyProfile === opt.v ? '#f59e0b' : '#374151'}`,
                      }}
                      title={opt.d}
                    >
                      {opt.l}
                    </button>
                  ))}
                </div>
              </div>

              {/* Transition Style + Overlap */}
              <div className="flex items-center gap-3">
                <div>
                  <label className="text-[10px] text-gray-500 mb-1 block">过渡风格</label>
                  <div className="flex flex-wrap gap-1">
                    {[
                      { v: 'smooth', l: '🎚 EQ渐变' },
                      { v: 'power', l: '🔄 等功率' },
                      { v: 'bass_swap', l: '🎸 Bass交换' },
                      { v: 'echo_out', l: '🔊 回声尾' },
                      { v: 'filter', l: '🎛 滤波扫频' },
                      { v: 'cut', l: '✂️ 硬切' },
                      { v: 'slam', l: '💥 冲击' },
                    ].map(opt => (
                      <button
                        key={opt.v}
                        onClick={() => setDjTransitionStyle(opt.v)}
                        className={`px-2 py-1 rounded-lg text-[11px] transition ${
                          djTransitionStyle === opt.v
                            ? 'bg-amber-500/20 text-amber-400 border border-amber-500'
                            : 'bg-surface text-gray-500 border border-gray-700'
                        }`}
                      >
                        {opt.l}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-[10px] text-gray-500 mb-1 block">过渡重叠</label>
                  <select
                    value={djOverlapBars}
                    onChange={e => setDjOverlapBars(Number(e.target.value))}
                    className="bg-surface text-white border border-gray-600 rounded-lg px-3 py-1.5 text-sm focus:border-amber-500 focus:outline-none"
                  >
                    <option value={4}>4 小节</option>
                    <option value={8}>8 小节</option>
                    <option value={16}>16 小节</option>
                    <option value={32}>32 小节</option>
                  </select>
                </div>
              </div>

              {/* Generate DJ Mix */}
              <button
                onClick={handleGenerateDJMix}
                disabled={djLoading}
                className="w-full py-2.5 rounded-lg text-sm font-semibold transition bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 disabled:opacity-50 text-white"
              >
                {djLoading ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Harmonize 分析排歌中...
                  </span>
                ) : `🤖 Harmonize · ${DANCE_STYLE_LABELS[mixStyle]} · ${mixDuration}分钟`}
              </button>

              {djError && (
                <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-3 py-2 text-red-300 text-xs">{djError}</div>
              )}

              {/* DJ Mix Results */}
              {djResult && djResult.playlist.length > 0 && (
                <div className="space-y-3 mt-2">
                  {/* Stats header */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] bg-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full">
                      平均兼容度 {djResult.avg_score}%
                    </span>
                    <span className="text-[10px] bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded-full">
                      {djResult.harmonic_weight === 'bpm_first' ? 'BPM优先' : djResult.harmonic_weight === 'key_first' ? '调性优先' : '均衡'}
                    </span>
                    <span className="text-[10px] bg-surface text-gray-400 px-2 py-0.5 rounded-full">
                      能量: {djEnergyProfile}
                    </span>
                    <span className="text-[10px] bg-surface text-gray-400 px-2 py-0.5 rounded-full">
                      约 {Math.round(djResult.total_duration_sec / 60)} 分钟
                    </span>
                  </div>

                  {/* Track list with transition info */}
                  <div className="space-y-0.5">
                    {djResult.playlist.map((track, i) => {
                      const transition = djResult.transitions.find(t => t.to_song_id === track.song_id)
                      const hasFile = !!djResult.processed_files[track.song_id]
                      return (
                        <div key={track.song_id}>
                          {/* Transition indicator between songs */}
                          {transition && (
                            <div className="flex items-center gap-2 px-2 py-1">
                              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-amber-500/40 to-transparent" />
                              <div className="flex items-center gap-1 text-[9px]">
                                <span style={{ color: transition.score >= 70 ? '#22c55e' : transition.score >= 40 ? '#f59e0b' : '#ef4444' }}>
                                  {Math.round(transition.score)}%
                                </span>
                                <span className="text-gray-600">|</span>
                                <span className="text-gray-500">BPM:{Math.round(transition.bpm_score)}</span>
                                <span className="text-gray-500">Key:{Math.round(transition.key_score)}</span>
                                <span className="text-gray-500">E:{Math.round(transition.energy_score)}</span>
                                <span className="text-gray-600">|</span>
                                <span className="text-amber-500/60">{transition.mix_duration_bars}bar</span>
                              </div>
                              <div className="flex-1 h-px bg-gradient-to-r from-transparent via-amber-500/40 to-transparent" />
                            </div>
                          )}
                          {/* Song row */}
                          <div className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-surface-lighter transition">
                            <span className="w-5 text-xs text-gray-500 text-center">{i + 1}</span>
                            <div className="flex-1 min-w-0">
                              <div className="text-sm text-white truncate">{track.title}</div>
                              <div className="text-[10px] text-gray-500 truncate">{track.artist}</div>
                            </div>
                            <span className="text-[10px] text-gray-400">{track.bpm ? Math.round(track.bpm) : '-'}</span>
                            <span className="w-14 text-right">
                              {hasFile ? (
                                <button
                                  onClick={() => toggleMixPlay(String(track.song_id), djResult.processed_files[track.song_id])}
                                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium transition hover:scale-105"
                                  style={{ background: '#f59e0b33', color: '#f59e0b' }}
                                >
                                  {playingTrackId === String(track.song_id) ? '⏸' : '▶'}
                                </button>
                              ) : (
                                <span className="text-[10px] text-gray-500">—</span>
                              )}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Start DJ Seamless */}
                  <button
                    onClick={handleStartDJSeamless}
                    disabled={djLoading}
                    className="w-full py-3 rounded-xl text-sm font-bold transition shadow-lg text-white hover:opacity-90"
                    style={{ background: 'linear-gradient(135deg, #f59e0b, #ea580c)' }}
                  >
                    🤖 开始 Harmonize DJ 播放
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Seamless Player */}
        {seamlessActive && seamlessTracks.length > 0 && (
          <SeamlessPlayer
            key={seamlessKey}
            tracks={seamlessTracks}
            crossfadeSec={4}
            accentColor={DANCE_STYLE_COLORS[mixStyle] || '#8b5cf6'}
            onEnd={() => {
              setSeamlessActive(false)
              setEvents(prev => [...prev, { type: 'seamless_end', value: '全部播放完毕', time: new Date().toLocaleTimeString() }])
            }}
          />
        )}

        {!sessionId ? (
          /* Start session view */
          <div className="bg-surface-light rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-semibold text-white">选择会话模式</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {MODES.map(m => (
                <button
                  key={m.value}
                  onClick={() => setMode(m.value)}
                  className={`text-left px-4 py-3 rounded-lg transition border ${
                    mode === m.value
                      ? 'bg-primary/20 border-primary text-white'
                      : 'bg-surface border-gray-600 text-gray-400 hover:bg-surface-lighter'
                  }`}
                >
                  <div className="text-sm font-medium">{m.label}</div>
                  <div className="text-xs opacity-70 mt-0.5">{m.desc}</div>
                </button>
              ))}
            </div>

            <button
              onClick={handleStart}
              disabled={loading}
              className="w-full bg-primary hover:bg-primary-dark disabled:opacity-50 text-white py-3 rounded-lg text-sm font-semibold transition"
            >
              {loading ? '启动中...' : '🚀 开始会话'}
            </button>
          </div>
        ) : (
          /* Active session view */
          <>
            <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse" />
                  <span className="text-green-400 font-medium text-sm">会话进行中</span>
                </div>
                <div className="text-xs text-gray-400 mt-1">模式: {MODES.find(m => m.value === mode)?.label} · 已用时: {elapsed || '0:00'}</div>
              </div>
              <button
                onClick={handleEnd}
                disabled={loading}
                className="bg-red-500/20 hover:bg-red-500/30 text-red-400 px-4 py-2 rounded-lg text-sm font-medium transition"
              >
                结束会话
              </button>
            </div>

            {/* Quick event buttons */}
            <div className="bg-surface-light rounded-xl p-4 space-y-3">
              <h3 className="text-sm font-semibold text-white">快速记录</h3>
              <div className="flex flex-wrap gap-2">
                {quickEvents.map(evt => (
                  <button
                    key={evt}
                    onClick={() => { setEventType(evt); handleLogEvent() }}
                    className="bg-surface hover:bg-surface-lighter text-gray-300 border border-gray-600 px-3 py-1.5 rounded-lg text-xs transition"
                  >
                    {evt}
                  </button>
                ))}
              </div>

              <div className="flex gap-2 pt-2">
                <input
                  type="text"
                  placeholder="自定义事件类型"
                  value={eventType}
                  onChange={e => setEventType(e.target.value)}
                  className="flex-1 bg-surface rounded-lg px-3 py-1.5 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm"
                />
                <input
                  type="text"
                  placeholder="备注（可选）"
                  value={eventValue}
                  onChange={e => setEventValue(e.target.value)}
                  className="flex-1 bg-surface rounded-lg px-3 py-1.5 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm"
                />
                <button
                  onClick={handleLogEvent}
                  disabled={!eventType.trim()}
                  className="bg-primary hover:bg-primary-dark disabled:opacity-50 text-white px-4 py-1.5 rounded-lg text-sm transition"
                >
                  记录
                </button>
              </div>
            </div>

            {/* Event timeline */}
            <div className="bg-surface-light rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-3">事件时间线 ({events.length})</h3>
              <div className="space-y-2">
                {events.map((evt, idx) => (
                  <div key={idx} className="flex items-start gap-3">
                    <div className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 shrink-0" />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-white">{evt.type}</span>
                        <span className="text-xs text-gray-500">{evt.time}</span>
                      </div>
                      {evt.value && <div className="text-xs text-gray-400 mt-0.5">{evt.value}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {error && <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">{error}</div>}
      </div>
    </div>
  )
}
