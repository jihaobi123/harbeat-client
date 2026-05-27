// @ts-nocheck
import { useState, useRef } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import * as api from '../api/client'
import type { VibeSearchSongItem, VibeSearchResult } from '../types'

const MOOD_PRESETS = [
  { label: '🔥 Battle 炸场', query: 'battle炸场 高能量 hard hitting beats' },
  { label: '🌊 Chill Vibes', query: '放松 chill groovy 轻松氛围' },
  { label: '💃 Waacking 华丽', query: 'waacking disco funk 华丽 dramatic' },
  { label: '🎭 Popping 机械', query: 'popping funk electronic 机械感 robot' },
  { label: '🌙 夜晚慢歌', query: '深夜 慢歌 r&b smooth 抒情' },
  { label: '⚡ House 律动', query: 'house dance 律动 groovy bounce' },
]

export default function VibeSearch() {
  const { user } = useAuthStore()
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<VibeSearchResult | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playingId, setPlayingId] = useState<string | null>(null)

  const handleSearch = async (searchQuery?: string) => {
    const q = searchQuery || query
    if (!q.trim()) return
    setLoading(true)
    setError('')
    stopAudio()
    try {
      const res = await api.vibeSearch(q, user?.id)
      setResult(res)
    } catch (e: any) {
      setError(e.message || 'Vibe 搜索失败')
    } finally {
      setLoading(false)
    }
  }

  const stopAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    setPlayingId(null)
  }

  const togglePreview = (song: VibeSearchSongItem) => {
    if (!song.preview_url) return
    const id = song.spotify_id || song.title
    if (playingId === id) {
      stopAudio()
      return
    }
    stopAudio()
    const audio = new Audio(song.preview_url)
    audio.volume = 0.5
    audio.onended = () => setPlayingId(null)
    audio.play()
    audioRef.current = audio
    setPlayingId(id)
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      {/* Search bar */}
      <div className="px-5 py-4 border-b border-gray-700 space-y-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="描述你想要的音乐氛围... 例如: 深夜popping cypher 低沉有力"
            className="flex-1 bg-surface border border-gray-600 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-primary"
          />
          <button
            onClick={() => handleSearch()}
            disabled={loading || !query.trim()}
            className="bg-primary hover:bg-primary/80 text-white px-4 py-2 rounded-lg text-sm transition disabled:opacity-50 shrink-0"
          >
            {loading ? '搜索中...' : '🔍 搜索'}
          </button>
        </div>
        {/* Mood presets */}
        <div className="flex flex-wrap gap-2">
          {MOOD_PRESETS.map(p => (
            <button
              key={p.label}
              onClick={() => { setQuery(p.query); handleSearch(p.query) }}
              className="text-xs px-3 py-1.5 rounded-full bg-surface border border-gray-600 text-gray-300 hover:border-primary hover:text-primary transition"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {error && (
          <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="text-gray-500 text-sm">正在用 CLAP + Spotify 搜索音乐...</div>
          </div>
        )}

        {result && !loading && (
          <>
            {/* Vibe interpretation */}
            <div className="bg-surface-light rounded-xl p-4 space-y-2">
              <div className="text-sm text-gray-400">
                <span className="text-white font-medium">🎭 Vibe 解读:</span>{' '}
                {result.vibe_description}
              </div>
              {result.genres.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-gray-500">风格:</span>
                  {result.genres.map(g => (
                    <span key={g} className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary">
                      {g}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Song list */}
            {result.songs.length === 0 ? (
              <div className="text-center py-10 text-gray-500 text-sm">
                没有找到匹配的音乐，试试换个描述？
              </div>
            ) : (
              <div className="grid gap-3">
                {result.songs.map((song, i) => {
                  const id = song.spotify_id || song.title
                  const isPlaying = playingId === id
                  return (
                    <div
                      key={id + i}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-surface-light hover:bg-surface-lighter transition group"
                    >
                      {/* Album art or source badge */}
                      {song.album_art ? (
                        <img
                          src={song.album_art}
                          alt=""
                          className="w-10 h-10 rounded object-cover shrink-0"
                        />
                      ) : (
                        <div className={`w-10 h-10 rounded flex items-center justify-center shrink-0 ${
                          song.source === 'local' ? 'bg-primary/20 text-primary' : 'bg-surface text-gray-600'
                        }`}>
                          {song.source === 'local' ? '🎧' : '🎵'}
                        </div>
                      )}

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{song.title}</div>
                        <div className="text-xs text-gray-500 truncate">
                          {song.artist}
                          {song.style && <span className="ml-2 text-gray-600">· {song.style}</span>}
                        </div>
                      </div>

                      {/* Match percentage */}
                      <div className={`text-xs font-medium shrink-0 ${
                        song.match_percentage >= 70 ? 'text-green-400' :
                        song.match_percentage >= 40 ? 'text-yellow-400' : 'text-gray-500'
                      }`}>
                        {song.match_percentage}%
                      </div>

                      {/* Source badge */}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded shrink-0 ${
                        song.source === 'local'
                          ? 'bg-primary/20 text-primary'
                          : 'bg-green-500/20 text-green-400'
                      }`}>
                        {song.source === 'local' ? '曲库' : 'Spotify'}
                      </span>

                      {/* Preview button */}
                      {song.preview_url && (
                        <button
                          onClick={() => togglePreview(song)}
                          className="text-xs px-2 py-1 rounded-full bg-surface border border-gray-600 text-gray-400 hover:text-white transition shrink-0"
                        >
                          {isPlaying ? '⏸ 暂停' : '▶ 试听'}
                        </button>
                      )}

                      {/* Spotify link */}
                      {song.spotify_url && (
                        <a
                          href={song.spotify_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-green-400 hover:text-green-300 shrink-0"
                        >
                          ↗
                        </a>
                      )}

                      {/* In library badge */}
                      {song.in_library && song.source === 'local' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 shrink-0">
                          已入库
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}

        {!result && !loading && !error && (
          <div className="flex flex-col items-center justify-center py-20 text-gray-500">
            <span className="text-4xl mb-3">🎭</span>
            <p className="text-sm">用自然语言描述你想要的音乐氛围</p>
            <p className="text-xs mt-1 text-gray-600">或者点击上方的预设标签快速搜索</p>
          </div>
        )}
      </div>
    </div>
  )
}
