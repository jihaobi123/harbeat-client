import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import * as api from '../api/client'
import type { PracticeTrack } from '../api/client'

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
