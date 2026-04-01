import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import * as api from '../api/client'
import type { RecommendedSong } from '../types'

const MODES = [
  { value: 'freeplay', label: '自由练习' },
  { value: 'cypher', label: 'Cypher' },
  { value: 'battle', label: 'Battle' },
  { value: 'showcase', label: '表演' },
  { value: 'training', label: '训练' },
]

const ENERGY_LEVELS = [
  { value: 'low', label: '低能量' },
  { value: 'medium', label: '中等' },
  { value: 'high', label: '高能量' },
]

const SOURCES = [
  { value: 'library', label: '我的曲库', desc: '从你已下载的歌曲中推荐' },
  { value: 'server', label: '服务器曲池', desc: '从所有用户的歌曲中推荐' },
]

export default function RecommendPanel() {
  const { user } = useAuthStore()
  const [mode, setMode] = useState('freeplay')
  const [targetEnergy, setTargetEnergy] = useState('')
  const [source, setSource] = useState('library')
  const [songs, setSongs] = useState<RecommendedSong[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [hasResult, setHasResult] = useState(false)

  const fetchRecommendations = async () => {
    if (!user) return
    setLoading(true)
    setError('')
    try {
      const res = await api.getRecommendations({
        user_id: user.id,
        mode,
        target_energy: targetEnergy || undefined,
        source,
      })
      setSongs(res.songs)
      setHasResult(true)
    } catch (e: any) {
      setError(e.message || '获取推荐失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      <div className="px-5 py-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold text-white mb-1">🎯 智能推荐</h2>
        <p className="text-xs text-gray-500">根据你的音乐品味和使用场景推荐歌曲</p>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Settings */}
        <div className="bg-surface-light rounded-xl p-4 space-y-4">
          {/* Source selector */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">推荐来源</label>
            <div className="flex gap-2">
              {SOURCES.map(s => (
                <button
                  key={s.value}
                  onClick={() => { setSource(s.value); setHasResult(false) }}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm transition text-left ${
                    source === s.value
                      ? 'bg-primary/20 text-primary border border-primary/50'
                      : 'bg-surface text-gray-400 hover:bg-surface-lighter border border-gray-600'
                  }`}
                >
                  <div className="font-medium">{s.label}</div>
                  <div className="text-xs opacity-70 mt-0.5">{s.desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">场景模式</label>
            <div className="flex flex-wrap gap-2">
              {MODES.map(m => (
                <button
                  key={m.value}
                  onClick={() => setMode(m.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition ${
                    mode === m.value ? 'bg-primary text-white' : 'bg-surface text-gray-400 hover:bg-surface-lighter border border-gray-600'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-2">目标能量（可选）</label>
            <div className="flex gap-2">
              {ENERGY_LEVELS.map(e => (
                <button
                  key={e.value}
                  onClick={() => setTargetEnergy(prev => prev === e.value ? '' : e.value)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition ${
                    targetEnergy === e.value ? 'bg-accent text-surface font-medium' : 'bg-surface text-gray-400 hover:bg-surface-lighter border border-gray-600'
                  }`}
                >
                  {e.label}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={fetchRecommendations}
            disabled={loading}
            className="bg-primary hover:bg-primary-dark disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm font-medium transition w-full"
          >
            {loading ? '正在生成推荐...' : '获取推荐'}
          </button>
        </div>

        {error && <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">{error}</div>}

        {/* Results */}
        {hasResult && (
          <div className="bg-surface-light rounded-xl p-4">
            <h3 className="text-sm font-semibold text-white mb-3">
              推荐结果 ({songs.length} 首)
              {source === 'server' && <span className="text-xs text-gray-500 ml-2">· 服务器曲池</span>}
            </h3>
            {songs.length === 0 ? (
              <p className="text-gray-500 text-sm">
                {source === 'library'
                  ? '暂无推荐结果，请先下载歌曲并添加标签'
                  : '暂无推荐结果，请先导入更多歌曲并生成用户画像'}
              </p>
            ) : (
              <div className="space-y-1">
                {songs.map((song, idx) => (
                  <div key={song.song_id} className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-lighter transition">
                    <span className="w-6 text-center text-xs text-gray-500 shrink-0">{idx + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{song.title}</div>
                      <div className="text-xs text-gray-500 truncate">{song.artist}</div>
                    </div>
                    {source === 'server' && (
                      <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${
                        song.in_library
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-yellow-500/20 text-yellow-400'
                      }`}>
                        {song.in_library ? '已有' : '未下载'}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
