import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import * as api from '../api/client'
import type { VibeSearchResult } from '../types'

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
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<VibeSearchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h3 className="text-sm font-semibold text-white flex items-center gap-2">
          <span className="text-lg">🎭</span>
          Vibe 语义搜索
        </h3>
        <p className="text-xs text-gray-500 mt-0.5 ml-7">
          用自然语言描述你想要的音乐氛围，从 Spotify 海量曲库中发现新歌（CLAP 语义重排序）
        </p>
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
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5 ml-7">
              {result.genres.length > 0 && result.genres.map(g => (
                <span
                  key={g}
                  className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary"
                >
                  {g}
                </span>
              ))}
              {result.search_query && (
                <span className="text-xs text-gray-600 ml-1">
                  Spotify: {result.search_query}
                </span>
              )}
            </div>
          </div>
          <div className="px-1 pb-2">
            {result.songs.map((song, idx) => {
              const key = song.spotify_id || song.song_id || idx
              const matchPct = Math.round(Math.max(0, 1 - song.distance) * 100)
              return (
                <div
                  key={key}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-lighter transition group"
                >
                  {/* Album art */}
                  {song.album_art ? (
                    <img
                      src={song.album_art}
                      alt=""
                      className="w-10 h-10 rounded object-cover shrink-0"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded bg-surface flex items-center justify-center shrink-0">
                      <span className="text-gray-600 text-lg">🎵</span>
                    </div>
                  )}
                  {/* Title / Artist */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-white truncate">{song.title}</div>
                    <div className="text-xs text-gray-500 truncate">{song.artist}</div>
                  </div>
                  {/* Match % */}
                  <span className="text-xs text-gray-600 shrink-0 tabular-nums">
                    {matchPct}%
                  </span>
                  {/* Preview play */}
                  {song.preview_url && (
                    <button
                      onClick={() => {
                        const a = document.getElementById('vibe-preview') as HTMLAudioElement
                        if (a) {
                          if (a.src === song.preview_url && !a.paused) {
                            a.pause()
                          } else {
                            a.src = song.preview_url!
                            a.volume = 0.5
                            a.play().catch(() => {})
                          }
                        }
                      }}
                      className="text-xs px-2 py-1 rounded-full bg-green-500/20 hover:bg-green-500/30 text-green-400 transition shrink-0"
                    >
                      ▶ 试听
                    </button>
                  )}
                  {/* Spotify link */}
                  {song.spotify_url && (
                    <a
                      href={song.spotify_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs px-2 py-1 rounded-full bg-[#1DB954]/20 hover:bg-[#1DB954]/30 text-[#1DB954] transition shrink-0"
                    >
                      Spotify
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Hidden audio element for preview */}
      <audio id="vibe-preview" className="hidden" />

      {/* Loading state */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="text-gray-500 text-sm">正在搜索...</div>
        </div>
      )}
    </div>
  )
}
