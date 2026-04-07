import { useState, useCallback, useRef } from 'react'
import * as api from '../api/client'
import { useMusicStore } from '../store/useMusicStore'
import { DANCE_STYLES, DANCE_STYLE_LABELS, DANCE_STYLE_COLORS } from '../types'
import type { DanceStyle } from '../types'

interface FangpiSong {
  id: string
  title: string
  artist: string
  url: string
  free?: boolean
  source?: string
  duration?: number
}

const ENERGY_OPTIONS = [
  { value: 'low', label: '🔋 低能量' },
  { value: 'medium', label: '⚡ 中能量' },
  { value: 'high', label: '🔥 高能量' },
]

const SCENE_OPTIONS = [
  { value: 'freeplay', label: '🎧 自由练习' },
  { value: 'cypher', label: '🔄 Cypher' },
  { value: 'battle', label: '⚔️ Battle' },
  { value: 'showcase', label: '🎭 Showcase' },
  { value: 'training', label: '📚 训练' },
]

/* ─── Tag selection modal before download ─── */
function DownloadTagModal({ song, onConfirm, onCancel }: {
  song: FangpiSong
  onConfirm: (tags: DanceStyle[], energy: string[], scenes: string[]) => void
  onCancel: () => void
}) {
  const [styles, setStyles] = useState<DanceStyle[]>([])
  const [energy, setEnergy] = useState<string[]>([])
  const [scenes, setScenes] = useState<string[]>([])

  const toggleItem = <T extends string>(list: T[], item: T): T[] =>
    list.includes(item) ? list.filter(x => x !== item) : [...list, item]

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onCancel}>
      <div className="bg-surface-light rounded-2xl w-full max-w-md mx-4 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="px-5 py-4 border-b border-gray-700">
          <h3 className="text-base font-semibold text-white">🏷️ 设置歌曲标签</h3>
          <p className="text-xs text-gray-400 mt-1 truncate">{song.title} - {song.artist}</p>
        </div>

        <div className="p-5 space-y-4">
          {/* Dance styles */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">舞种风格（可多选）</label>
            <div className="flex flex-wrap gap-1.5">
              {DANCE_STYLES.map(style => (
                <button
                  key={style}
                  onClick={() => setStyles(prev => toggleItem(prev, style))}
                  className="px-2.5 py-1 rounded-full text-xs font-medium transition"
                  style={{
                    background: styles.includes(style) ? DANCE_STYLE_COLORS[style] + '33' : 'transparent',
                    color: styles.includes(style) ? DANCE_STYLE_COLORS[style] : '#9ca3af',
                    border: `1px solid ${styles.includes(style) ? DANCE_STYLE_COLORS[style] : '#4b5563'}`,
                  }}
                >
                  {DANCE_STYLE_LABELS[style]}
                </button>
              ))}
            </div>
          </div>

          {/* Energy */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">能量等级（可多选）</label>
            <div className="flex gap-2">
              {ENERGY_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setEnergy(prev => toggleItem(prev, opt.value))}
                  className={`px-3 py-1.5 rounded-lg text-xs transition ${
                    energy.includes(opt.value)
                      ? 'bg-primary/20 text-primary border border-primary'
                      : 'bg-surface text-gray-400 border border-gray-600 hover:border-gray-500'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Scene */}
          <div>
            <label className="text-xs text-gray-400 mb-2 block">适用场景（可多选）</label>
            <div className="flex flex-wrap gap-2">
              {SCENE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setScenes(prev => toggleItem(prev, opt.value))}
                  className={`px-3 py-1.5 rounded-lg text-xs transition ${
                    scenes.includes(opt.value)
                      ? 'bg-primary/20 text-primary border border-primary'
                      : 'bg-surface text-gray-400 border border-gray-600 hover:border-gray-500'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-gray-700 flex justify-between">
          <button onClick={onCancel} className="text-gray-400 hover:text-white text-sm transition">取消</button>
          <div className="flex gap-2">
            <button
              onClick={() => onConfirm([], [], [])}
              className="text-gray-400 hover:text-white text-xs px-3 py-2 rounded-lg border border-gray-600 transition"
              title="不打标签的歌曲属于所有分类，可被随机推荐"
            >跳过标签（属于全部分类）</button>
            <button
              onClick={() => onConfirm(styles, energy, scenes)}
              className="bg-primary hover:bg-primary-dark text-white text-sm px-5 py-2 rounded-lg transition"
            >确认下载</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function PlatformSearch() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<FangpiSong[]>([])
  const [searching, setSearching] = useState(false)
  const [downloading, setDownloading] = useState<Set<string>>(new Set())
  const [downloaded, setDownloaded] = useState<Set<string>>(new Set())
  const [error, setError] = useState('')
  const [tagModalSong, setTagModalSong] = useState<FangpiSong | null>(null)
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

  const handleDownload = async (song: FangpiSong, tags: DanceStyle[], energy: string[], scenes: string[]) => {
    setTagModalSong(null)
    setDownloading((prev) => new Set(prev).add(song.id))
    try {
      const tagData = (tags.length || energy.length || scenes.length)
        ? { tags, energy, scenes }
        : undefined
      await api.downloadFangpi(song.id, song.title, song.artist, tagData, song.source)
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
        <p className="text-xs text-gray-500 mb-3">搜索在线音乐资源，点击下载时可为歌曲设置标签</p>
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
                  <p className="text-sm text-white truncate">
                    {song.title}
                    {song.free === false && <span className="ml-1.5 text-[10px] text-yellow-500 bg-yellow-500/10 px-1.5 py-0.5 rounded">VIP</span>}
                  </p>
                  <p className="text-xs text-gray-500 truncate">
                    {song.artist}
                    {song.duration ? ` · ${Math.floor(song.duration / 60)}:${String(song.duration % 60).padStart(2, '0')}` : ''}
                  </p>
                </div>
                <button
                  onClick={() => setTagModalSong(song)}
                  disabled={isDownloading || isDownloaded}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition shrink-0 ${
                    isDownloaded
                      ? 'bg-green-500/20 text-green-400'
                      : isDownloading
                      ? 'bg-surface text-gray-400'
                      : 'bg-primary/20 text-primary hover:bg-primary/30 opacity-0 group-hover:opacity-100'
                  }`}
                >
                  {isDownloaded ? '✓ 已下载' : isDownloading ? '下载中...' : song.free === false ? '⬇ VIP' : '⬇ 下载'}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* Per-song tag modal */}
      {tagModalSong && (
        <DownloadTagModal
          song={tagModalSong}
          onConfirm={(tags, energy, scenes) => handleDownload(tagModalSong, tags, energy, scenes)}
          onCancel={() => setTagModalSong(null)}
        />
      )}
    </div>
  )
}
