import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import * as api from '../api/client'
import type { VibeSearchResult, VibeSearchSongItem } from '../types'

const MOOD_PRESETS = [
  { label: '🌧️ 雨夜漫步', query: '雨夜 忧郁 慵懒 漫步' },
  { label: '🔥 Battle 热血', query: '热血 嘻哈 高能 battle' },
  { label: '🌙 深夜放松', query: '放松 慵懒 jazz 深夜' },
  { label: '💃 派对 Groove', query: '派对 funk groove 街舞' },
  { label: '🎤 Old School 嘻哈', query: '老派 嘻哈 hip-hop boom bap' },
  { label: '🌆 霓虹都市', query: '霓虹 电子 迷幻 都市' },
  { label: '💜 Soul R&B', query: 'soul r&b 放松 复古' },
  { label: '⚡ Trap Bass', query: 'trap bass 808 高能' },
]

export default function VibeSearch() {
  const { user } = useAuthStore()
  const { loadSongs } = useMusicStore()
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<VibeSearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState<Set<number>>(new Set())
  const [added, setAdded] = useState<Set<number>>(new Set())
  const [indexing, setIndexing] = useState(false)
  const [clapIndexing, setClapIndexing] = useState(false)
  const [stats, setStats] = useState<{ count: number; text_count: number } | null>(null)

  const doSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await api.vibeSearch(searchQuery, user?.id)
      setResult(res)
      if (res.songs.length === 0) {
        setError('没有找到匹配的歌曲，试试其他描述？')
      }
    } catch (e: any) {
      setError(e.message || '搜索失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    doSearch(query)
  }

  const handlePreset = (presetQuery: string) => {
    setQuery(presetQuery)
    doSearch(presetQuery)
  }

  const handleAdd = async (song: VibeSearchSongItem) => {
    if (!user || song.in_library || adding.has(song.song_id) || added.has(song.song_id)) return
    setAdding(prev => new Set(prev).add(song.song_id))
    try {
      await api.addSongToLibrary(user.id, song.song_id)
      setAdded(prev => new Set(prev).add(song.song_id))
      setResult(prev =>
        prev
          ? {
              ...prev,
              songs: prev.songs.map(s =>
                s.song_id === song.song_id ? { ...s, in_library: true } : s,
              ),
            }
          : prev,
      )
      loadSongs()
    } catch (e: any) {
      setError(e.message || '加入曲库失败')
    } finally {
      setAdding(prev => {
        const next = new Set(prev)
        next.delete(song.song_id)
        return next
      })
    }
  }

  const handleReindex = async () => {
    setIndexing(true)
    try {
      await api.reindexVectorStore()
      await loadStats()
    } catch (e: any) {
      setError(e.message || '文本索引重建失败')
    } finally {
      setIndexing(false)
    }
  }

  const handleClapReindex = async () => {
    setClapIndexing(true)
    setError('')
    try {
      const res = await api.reindexClap()
      setError(`CLAP 重建完成: 成功 ${res.success} / 失败 ${res.failed} / 共 ${res.total}`)
      await loadStats()
    } catch (e: any) {
      setError(e.message || 'CLAP 重建失败')
    } finally {
      setClapIndexing(false)
    }
  }

  const loadStats = async () => {
    try {
      const res = await api.getVectorStoreStats()
      setStats({ count: res.count, text_count: res.text_count })
    } catch {
      // ignore
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <span className="text-lg">🎭</span>
            Vibe 语义搜索
          </h3>
          <p className="text-xs text-gray-500 mt-0.5 ml-7">
            用自然语言描述你想要的音乐氛围（CLAP 跨模态音频匹配）
          </p>
        </div>
        <div className="flex items-center gap-2">
          {stats !== null && (
            <span className="text-xs text-gray-500">
              🎵 CLAP {stats.count} 首 · 📝 文本 {stats.text_count} 首
            </span>
          )}
          {stats === null ? (
            <button
              onClick={loadStats}
              className="text-xs px-2.5 py-1 rounded-full bg-surface hover:bg-surface-lighter text-gray-400 border border-gray-600 transition"
            >
              📊 查看索引
            </button>
          ) : (
            <>
              <button
                onClick={handleReindex}
                disabled={indexing}
                className="text-xs px-2.5 py-1 rounded-full bg-surface hover:bg-surface-lighter text-gray-400 border border-gray-600 transition disabled:opacity-50"
              >
                {indexing ? '建中...' : '📝 文本索引'}
              </button>
              <button
                onClick={handleClapReindex}
                disabled={clapIndexing}
                className="text-xs px-2.5 py-1 rounded-full bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 transition disabled:opacity-50"
              >
                {clapIndexing ? '生成中(慢)...' : '🎵 CLAP 索引'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Search Bar */}
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="描述你想要的氛围... 例如：雨夜 慵懒 爵士"
          className="flex-1 bg-surface border border-gray-600 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-primary transition"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="bg-primary hover:bg-primary/80 text-white px-4 py-2 rounded-lg text-sm font-medium transition disabled:opacity-50"
        >
          {loading ? '搜索中...' : '搜索'}
        </button>
      </form>

      {/* Mood Presets */}
      <div className="flex flex-wrap gap-2">
        {MOOD_PRESETS.map(preset => (
          <button
            key={preset.query}
            onClick={() => handlePreset(preset.query)}
            className="text-xs px-3 py-1.5 rounded-full bg-surface-light hover:bg-surface-lighter text-gray-300 border border-gray-700 hover:border-gray-500 transition"
          >
            {preset.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {result && result.songs.length > 0 && (
        <div className="bg-surface-light rounded-xl overflow-hidden">
          <div className="px-4 pt-4 pb-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">✨</span>
              <h3 className="text-sm font-semibold text-white">
                搜索结果
              </h3>
              <span className="text-xs text-gray-500">· {result.songs.length} 首</span>
            </div>
            {result.genres.length > 0 && (
              <div className="flex gap-1.5 mt-1.5 ml-7">
                {result.genres.map(g => (
                  <span
                    key={g}
                    className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary"
                  >
                    {g}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="px-1 pb-2">
            {result.songs.map(song => {
              const isAdding = adding.has(song.song_id)
              const isAdded = added.has(song.song_id) || song.in_library
              return (
                <div
                  key={song.song_id}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-lighter transition group"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white truncate">{song.title}</div>
                    <div className="text-xs text-gray-500 truncate">{song.artist}</div>
                  </div>
                  {song.style && (
                    <span className="text-xs text-gray-500 shrink-0 hidden sm:inline">
                      {song.style}
                    </span>
                  )}
                  <span className="text-xs text-gray-600 shrink-0 tabular-nums">
                    {(1 - song.distance).toFixed(0)}%
                  </span>
                  {isAdded ? (
                    <span className="text-xs px-2.5 py-1 rounded-full bg-green-500/20 text-green-400 shrink-0">
                      已在曲库
                    </span>
                  ) : (
                    <button
                      onClick={() => handleAdd(song)}
                      disabled={isAdding}
                      className="text-xs px-2.5 py-1 rounded-full bg-primary/20 text-primary hover:bg-primary/30 transition shrink-0 opacity-0 group-hover:opacity-100 disabled:opacity-50"
                    >
                      {isAdding ? '添加中...' : '+ 加入曲库'}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500 text-sm">正在搜索...</div>
        </div>
      )}
    </div>
  )
}
