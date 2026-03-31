import { useState, useCallback, useRef } from 'react'
import * as api from '../api/client'
import { useMusicStore } from '../store/useMusicStore'

interface FangpiSong {
  id: string
  title: string
  artist: string
  url: string
}

export default function PlatformSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<FangpiSong[]>([])
  const [searching, setSearching] = useState(false)
  const [downloading, setDownloading] = useState<Set<string>>(new Set())
  const [downloaded, setDownloaded] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')
  const loadSongs = useMusicStore((s) => s.loadSongs)
  const timerRef = useRef<ReturnType<typeof setTimeout>>()

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([])
      return
    }
    setSearching(true)
    setError('')
    try {
      const res = await api.searchFangpi(q.trim())
      setResults(res.songs || [])
    } catch (e: any) {
      setError(e.message || '搜索失败')
      setResults([])
    } finally {
      setSearching(false)
    }
  }, [])

  const handleQueryChange = (value: string) => {
    setQuery(value)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => doSearch(value), 500)
  }

  const handleDownload = async (song: FangpiSong) => {
    setDownloading((prev) => new Set(prev).add(song.id))
    try {
      await api.downloadFangpi(song.id, song.title, song.artist)
      setDownloaded((prev) => new Set(prev).add(song.id))
      loadSongs()
    } catch (e: any) {
      setError(`下载失败: ${e.message || song.title}`)
    } finally {
      setDownloading((prev) => {
        const next = new Set(prev)
        next.delete(song.id)
        return next
      })
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="p-5 border-b border-gray-700">
        <h2 className="text-lg font-bold text-white mb-1">🌐 在线搜索</h2>
        <p className="text-xs text-gray-500 mb-3">搜索 fangpi.net 音乐资源，下载到本地音乐库</p>
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            placeholder="输入歌曲名、艺术家..."
            className="w-full bg-surface rounded-lg px-4 py-2.5 text-sm text-white border border-gray-600 focus:border-primary focus:outline-none pr-10"
            autoFocus
          />
          {searching && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>
        {error && <p className="text-xs text-red-400 mt-2">{error}</p>}
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-3">
        {results.length === 0 && !searching && query.trim() && (
          <div className="text-center text-gray-500 py-12 text-sm">未找到相关歌曲</div>
        )}
        {results.length === 0 && !query.trim() && (
          <div className="text-center text-gray-500 py-12">
            <div className="text-4xl mb-3">🔍</div>
            <p className="text-sm">输入关键词开始搜索</p>
          </div>
        )}
        <div className="space-y-1">
          {results.map((song) => {
            const isDownloading = downloading.has(song.id)
            const isDownloaded = downloaded.has(song.id)
            return (
              <div
                key={song.id}
                className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-surface-lighter transition group"
              >
                <div className="w-8 h-8 bg-surface rounded-lg flex items-center justify-center text-sm shrink-0">🎵</div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-white truncate">{song.title}</p>
                  <p className="text-xs text-gray-500 truncate">{song.artist}</p>
                </div>
                <button
                  onClick={() => handleDownload(song)}
                  disabled={isDownloading || isDownloaded}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition shrink-0 ${
                    isDownloaded
                      ? 'bg-green-500/20 text-green-400'
                      : isDownloading
                      ? 'bg-surface text-gray-400'
                      : 'bg-primary/20 text-primary hover:bg-primary/30 opacity-0 group-hover:opacity-100'
                  }`}
                >
                  {isDownloaded ? '✓ 已下载' : isDownloading ? '下载中...' : '⬇ 下载'}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
