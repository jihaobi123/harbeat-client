import { useEffect, useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import * as api from '../api/client'
import type { DiscoverSection, DiscoverSongItem } from '../types'
import VibeSearch from './VibeSearch'

type Tab = 'discover' | 'vibe'

export default function RecommendPanel() {
  const { user } = useAuthStore()
  const { loadSongs } = useMusicStore()
  const [tab, setTab] = useState<Tab>('discover')
  const [sections, setSections] = useState<DiscoverSection[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState<Set<number>>(new Set())
  const [added, setAdded] = useState<Set<number>>(new Set())

  const fetchDiscover = async () => {
    if (!user) return
    setLoading(true)
    setError('')
    try {
      const res = await api.discoverSongs(user.id)
      setSections(res.sections)
    } catch (e: any) {
      setError(e.message || '获取推荐失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDiscover()
  }, [user]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleAdd = async (song: DiscoverSongItem) => {
    if (!user || song.in_library || adding.has(song.song_id) || added.has(song.song_id)) return
    setAdding(prev => new Set(prev).add(song.song_id))
    try {
      await api.addSongToLibrary(user.id, song.song_id)
      setAdded(prev => new Set(prev).add(song.song_id))
      // Mark as in_library in all sections
      setSections(prev =>
        prev.map(sec => ({
          ...sec,
          songs: sec.songs.map(s =>
            s.song_id === song.song_id ? { ...s, in_library: true } : s,
          ),
        })),
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

  const renderSong = (song: DiscoverSongItem) => {
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
          <span className="text-xs text-gray-500 shrink-0 hidden sm:inline">{song.style}</span>
        )}
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
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      {/* Tab bar */}
      <div className="px-5 pt-4 pb-0 flex gap-2">
        <button
          onClick={() => setTab('discover')}
          className={`px-4 py-2 rounded-t-lg text-sm font-medium transition ${
            tab === 'discover'
              ? 'bg-surface-light text-white'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          📋 标签推荐
        </button>
        <button
          onClick={() => setTab('vibe')}
          className={`px-4 py-2 rounded-t-lg text-sm font-medium transition ${
            tab === 'vibe'
              ? 'bg-surface-light text-white'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          🎭 Vibe 搜索
        </button>
      </div>

      {tab === 'vibe' ? (
        <VibeSearch />
      ) : (
      <>
      <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white mb-1">🎯 发现音乐</h2>
          <p className="text-xs text-gray-500">自动推荐不同舞种、场景下适合的音乐</p>
        </div>
        <button
          onClick={fetchDiscover}
          disabled={loading}
          className="bg-surface hover:bg-surface-lighter text-gray-300 border border-gray-600 px-3 py-1.5 rounded-lg text-sm transition disabled:opacity-50"
        >
          {loading ? '刷新中...' : '🔄 换一批'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {error && (
          <div className="bg-red-500/20 border border-red-500/40 rounded-lg px-4 py-2 text-red-300 text-sm">
            {error}
          </div>
        )}

        {loading && sections.length === 0 && (
          <div className="flex items-center justify-center py-20">
            <div className="text-gray-500 text-sm">正在加载推荐...</div>
          </div>
        )}

        {!loading && sections.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-20 text-gray-500">
            <span className="text-4xl mb-3">🎵</span>
            <p className="text-sm">服务器上还没有歌曲</p>
            <p className="text-xs mt-1">去「在线搜索」下载一些歌曲吧</p>
          </div>
        )}

        {sections.map(section => (
          <div key={section.key} className="bg-surface-light rounded-xl overflow-hidden">
            <div className="px-4 pt-4 pb-2">
              <div className="flex items-center gap-2">
                <span className="text-lg">{section.icon}</span>
                <h3 className="text-sm font-semibold text-white">{section.title}</h3>
                <span className="text-xs text-gray-500">· {section.songs.length} 首</span>
              </div>
              <p className="text-xs text-gray-500 mt-0.5 ml-7">{section.description}</p>
            </div>
            <div className="px-1 pb-2">
              {section.songs.map(renderSong)}
            </div>
          </div>
        ))}
      </div>
      </>
      )}
    </div>
  )
}
