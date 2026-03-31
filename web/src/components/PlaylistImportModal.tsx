import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import { DANCE_STYLES, DANCE_STYLE_LABELS, DANCE_STYLE_COLORS } from '../types'
import type { DanceStyle } from '../types'
import * as api from '../api/client'

interface Props {
  onClose: () => void
}

interface SongItem {
  key: string
  title: string
  artist: string
  duration: number
  bpm: number | null
  tags: DanceStyle[]
}

type SourceTab = 'link' | 'local' | 'platform'

export default function PlaylistImportModal({ onClose }: Props) {
  const { user } = useAuthStore()
  const { songs, importPlaylistFromSongs, loadSongs } = useMusicStore()
  const [tab, setTab] = useState<SourceTab>('link')
  const [playlistName, setPlaylistName] = useState('')
  const [stage, setStage] = useState<'source' | 'downloading' | 'tag'>('source')
  const [songItems, setSongItems] = useState<SongItem[]>([])
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')

  // Link tab
  const [linkText, setLinkText] = useState('')

  // Local tab
  const [searchQ, setSearchQ] = useState('')
  const [selectedSongIds, setSelectedSongIds] = useState<Set<string>>(new Set())

  // Platform tab (fangpi.net)
  const [platformQuery, setPlatformQuery] = useState('')
  const [platformResults, setPlatformResults] = useState<{ id: string; title: string; artist: string; url: string }[]>([])

  // Download results
  const [downloadResult, setDownloadResult] = useState<{ success: string[]; failed: string[] } | null>(null)

  const filteredSongs = searchQ.trim()
    ? songs.filter(s => s.title.toLowerCase().includes(searchQ.toLowerCase()) || s.artist.toLowerCase().includes(searchQ.toLowerCase()))
    : songs

  const addSongs = (items: SongItem[]) => {
    setSongItems(prev => {
      const seen = new Set(prev.map(s => `${s.title}||${s.artist}`.toLowerCase()))
      const additions = items.filter(s => !seen.has(`${s.title}||${s.artist}`.toLowerCase()))
      return [...prev, ...additions]
    })
  }

  const removeSong = (key: string) => {
    setSongItems(prev => prev.filter(s => s.key !== key))
  }

  // ── Link tab: parse NetEase / QQ Music playlist URL ──
  const handleParseLink = async () => {
    if (!linkText.trim()) return
    setBusy(true)
    setStatusMessage('')
    try {
      const result = await api.parsePlaylistUrl(linkText.trim())
      if (result.tracks.length === 0) throw new Error('歌单为空或解析失败')
      if (!playlistName.trim()) setPlaylistName(result.name)
      addSongs(result.tracks.map((t, i) => ({
        key: `link-${Date.now()}-${i}`,
        title: t.title,
        artist: t.artist,
        duration: t.duration,
        bpm: null,
        tags: [],
      })))
      setStatusMessage(`✅ 已添加 ${result.tracks.length} 首歌曲（${result.platform === 'netease' ? '网易云音乐' : 'QQ音乐'}）`)
      setLinkText('')
    } catch (e: any) {
      setStatusMessage(`❌ ${e.message || '解析失败'}`)
    } finally {
      setBusy(false)
    }
  }

  // ── Local tab: add from library ──
  const toggleSong = (id: string) => {
    setSelectedSongIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const addSelectedLocal = () => {
    const selected = songs.filter(s => selectedSongIds.has(s.id))
    addSongs(selected.map(s => ({
      key: `local-${s.id}`,
      title: s.title,
      artist: s.artist,
      duration: s.duration,
      bpm: s.bpm,
      tags: [],
    })))
    setSelectedSongIds(new Set())
    setStatusMessage(`✅ 已添加 ${selected.length} 首`)
  }

  // ── Platform tab: search fangpi.net ──
  const handlePlatformSearch = async () => {
    if (!platformQuery.trim()) return
    setBusy(true)
    setStatusMessage('')
    try {
      const result = await api.searchFangpi(platformQuery.trim())
      setPlatformResults(result.songs)
      if (result.songs.length === 0) setStatusMessage('未找到结果')
    } catch (e: any) {
      setStatusMessage(`❌ ${e.message || '搜索失败'}`)
    } finally {
      setBusy(false)
    }
  }

  const addPlatformSong = (song: { id: string; title: string; artist: string }) => {
    addSongs([{
      key: `platform-${song.id}`,
      title: song.title,
      artist: song.artist,
      duration: 0,
      bpm: null,
      tags: [],
    }])
  }

  // ── Download from fangpi.net and then tag ──
  const startImport = async () => {
    if (!user || songItems.length === 0 || !playlistName.trim()) return
    setStage('downloading')
    setError('')

    const success: string[] = []
    const failed: string[] = []

    // Step 1: Try to download songs that don't have local files
    for (const item of songItems) {
      try {
        // Search and download from fangpi.net
        const searchResult = await api.searchFangpi(`${item.title} ${item.artist}`)
        if (searchResult.songs.length > 0) {
          const best = searchResult.songs[0]
          await api.downloadFangpi(best.id, item.title, item.artist)
          success.push(`${item.title} - ${item.artist}`)
        } else {
          failed.push(`${item.title} - ${item.artist}`)
        }
      } catch {
        failed.push(`${item.title} - ${item.artist}`)
      }
    }

    setDownloadResult({ success, failed })
    loadSongs() // refresh library
    setStage('tag')
  }

  // ── Save playlist with tags ──
  const handleSaveTags = async () => {
    if (!user) return
    setImporting(true)
    setError('')
    try {
      await importPlaylistFromSongs(
        user.id,
        playlistName.trim(),
        songItems.map(item => ({
          title: item.title,
          artist: item.artist,
          duration: item.duration,
          bpm: item.bpm ?? undefined,
          tags: item.tags,
        }))
      )
      onClose()
    } catch (e: any) {
      setError(e.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  // ── Quick import without downloading ──
  const handleQuickImport = async () => {
    if (!user) return
    setImporting(true)
    setError('')
    try {
      await importPlaylistFromSongs(
        user.id,
        playlistName.trim(),
        songItems.map(item => ({
          title: item.title,
          artist: item.artist,
          duration: item.duration,
          bpm: item.bpm ?? undefined,
          tags: item.tags,
        }))
      )
      onClose()
    } catch (e: any) {
      setError(e.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const toggleTag = (idx: number, tag: DanceStyle) => {
    setSongItems(prev => prev.map((item, i) => {
      if (i !== idx) return item
      const tags = item.tags.includes(tag) ? item.tags.filter(t => t !== tag) : [...item.tags, tag]
      return { ...item, tags }
    }))
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-surface-light rounded-2xl w-full max-w-[760px] mx-4 max-h-[85vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <span className="text-lg">📋</span>
            <h2 className="text-base font-semibold text-white">
              {stage === 'downloading' ? '下载歌曲中...' : stage === 'tag' ? '设置风格标签' : '导入歌单'}
            </h2>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-white text-xl transition">×</button>
        </div>

        {stage === 'downloading' ? (
          <div className="px-8 py-12 flex flex-col items-center">
            <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-white">正在从 fangpi.net 匹配下载歌曲...</p>
            <p className="text-xs text-gray-500 mt-2">下载完成后可以设置舞种标签</p>
          </div>
        ) : stage === 'tag' ? (
          <>
            {/* Tag assignment stage */}
            <div className="flex-1 overflow-y-auto px-5 py-3 min-h-0">
              {downloadResult && downloadResult.failed.length > 0 && (
                <div className="mb-3 px-4 py-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-xs text-yellow-400">
                  以下歌曲未找到音源: {downloadResult.failed.join(' / ')}
                </div>
              )}
              <p className="text-xs text-gray-500 mb-3">为歌单中的歌曲设置舞蹈风格标签（可选）</p>
              <div className="space-y-3">
                {songItems.map((item, idx) => (
                  <div key={item.key} className="bg-surface rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm text-white">{item.title}</span>
                      <span className="text-xs text-gray-500">- {item.artist}</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {DANCE_STYLES.map(style => (
                        <button
                          key={style}
                          onClick={() => toggleTag(idx, style)}
                          className="px-2 py-0.5 rounded text-xs transition"
                          style={{
                            backgroundColor: item.tags.includes(style) ? DANCE_STYLE_COLORS[style] + '30' : 'transparent',
                            color: item.tags.includes(style) ? DANCE_STYLE_COLORS[style] : '#6b7280',
                            border: `1px solid ${item.tags.includes(style) ? DANCE_STYLE_COLORS[style] : '#374151'}`,
                          }}
                        >
                          {DANCE_STYLE_LABELS[style]}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {error && <div className="px-5 text-sm text-red-400">{error}</div>}
            <div className="px-5 py-4 border-t border-gray-700 flex justify-between">
              <button onClick={() => setStage('source')} className="text-gray-400 hover:text-white text-sm transition">← 返回</button>
              <button
                onClick={handleSaveTags}
                disabled={importing}
                className="bg-primary hover:bg-primary-dark disabled:opacity-50 text-white px-5 py-2 rounded-lg text-sm transition"
              >
                {importing ? '保存中...' : `保存歌单 (${songItems.length} 首)`}
              </button>
            </div>
          </>
        ) : (
          <>
            {/* Source selection stage */}
            <div className="px-5 pt-4 space-y-4 overflow-y-auto flex-1 min-h-0">
              {/* Playlist name */}
              <div>
                <label className="block text-xs text-gray-400 mb-1.5">歌单名称</label>
                <input
                  type="text"
                  placeholder="例如: 练习用歌单"
                  value={playlistName}
                  onChange={e => setPlaylistName(e.target.value)}
                  className="w-full bg-surface rounded-lg px-4 py-2 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm"
                />
              </div>

              {/* Tabs: Link / Local / Platform */}
              <div className="flex gap-1 bg-surface rounded-lg p-1">
                <button onClick={() => setTab('link')} className={`flex-1 py-2 text-xs rounded-md transition ${tab === 'link' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-white'}`}>
                  🔗 歌单链接
                </button>
                <button onClick={() => setTab('local')} className={`flex-1 py-2 text-xs rounded-md transition ${tab === 'local' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-white'}`}>
                  📁 从本地库
                </button>
                <button onClick={() => setTab('platform')} className={`flex-1 py-2 text-xs rounded-md transition ${tab === 'platform' ? 'bg-primary/20 text-primary' : 'text-gray-400 hover:text-white'}`}>
                  🔍 搜索下载
                </button>
              </div>

              {/* Link tab */}
              {tab === 'link' && (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500">粘贴网易云音乐或QQ音乐歌单链接，自动解析歌曲列表</p>
                  <div className="flex gap-2">
                    <input
                      value={linkText}
                      onChange={e => setLinkText(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleParseLink()}
                      placeholder="粘贴歌单链接..."
                      className="flex-1 bg-surface rounded-lg px-3 py-2 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm"
                    />
                    <button
                      onClick={handleParseLink}
                      disabled={busy || !linkText.trim()}
                      className="bg-cyan-600 hover:bg-cyan-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm transition"
                    >
                      {busy ? '解析中...' : '解析'}
                    </button>
                  </div>
                  <p className="text-xs text-gray-600">
                    支持：music.163.com / y.qq.com / i.y.qq.com 歌单链接
                  </p>
                </div>
              )}

              {/* Local tab */}
              {tab === 'local' && (
                <div className="space-y-2">
                  <input
                    type="text"
                    placeholder="搜索本地歌曲..."
                    value={searchQ}
                    onChange={e => setSearchQ(e.target.value)}
                    className="w-full bg-surface rounded-lg px-3 py-1.5 text-white border border-gray-600 focus:border-primary focus:outline-none text-xs"
                  />
                  <div className="max-h-[200px] overflow-y-auto border border-gray-700 rounded-lg divide-y divide-gray-700/50">
                    {filteredSongs.map(s => (
                      <label key={s.id} className="flex items-center gap-3 px-3 py-2 hover:bg-surface-lighter cursor-pointer transition">
                        <input type="checkbox" checked={selectedSongIds.has(s.id)} onChange={() => toggleSong(s.id)} className="accent-primary" />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-white truncate">{s.title}</div>
                          <div className="text-xs text-gray-500 truncate">{s.artist}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                  {selectedSongIds.size > 0 && (
                    <button onClick={addSelectedLocal} className="bg-primary/20 text-primary px-3 py-1.5 rounded-lg text-xs hover:bg-primary/30 transition">
                      添加选中的 {selectedSongIds.size} 首
                    </button>
                  )}
                </div>
              )}

              {/* Platform tab: fangpi.net search */}
              {tab === 'platform' && (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500">搜索 fangpi.net 歌曲，歌曲会下载到本地音乐库</p>
                  <div className="flex gap-2">
                    <input
                      value={platformQuery}
                      onChange={e => setPlatformQuery(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handlePlatformSearch()}
                      placeholder="搜索歌曲名称或艺术家..."
                      className="flex-1 bg-surface rounded-lg px-3 py-2 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm"
                    />
                    <button
                      onClick={handlePlatformSearch}
                      disabled={busy || !platformQuery.trim()}
                      className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm transition"
                    >
                      {busy ? '搜索中...' : '搜索'}
                    </button>
                  </div>
                  <div className="max-h-[200px] overflow-y-auto border border-gray-700 rounded-lg divide-y divide-gray-700/50">
                    {platformResults.map(s => (
                      <button
                        key={s.id}
                        onClick={() => addPlatformSong(s)}
                        className="w-full text-left px-3 py-2 hover:bg-surface-lighter transition"
                      >
                        <p className="text-sm text-white truncate">{s.title}</p>
                        <p className="text-xs text-gray-500 truncate">{s.artist}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Status */}
              {statusMessage && (
                <div className="text-xs text-gray-300 bg-surface rounded-lg px-3 py-2">{statusMessage}</div>
              )}

              {/* Current song list */}
              {songItems.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1.5">歌单歌曲 ({songItems.length} 首)</p>
                  <div className="max-h-[200px] overflow-y-auto border border-gray-700 rounded-lg divide-y divide-gray-700/50">
                    {songItems.map(item => (
                      <div key={item.key} className="flex items-center gap-3 px-3 py-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-white truncate">{item.title}</p>
                          <p className="text-xs text-gray-500 truncate">{item.artist}</p>
                        </div>
                        <button onClick={() => removeSong(item.key)} className="p-1 text-gray-600 hover:text-red-400 transition">×</button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {error && <div className="px-5 text-sm text-red-400">{error}</div>}

            {/* Footer */}
            <div className="px-5 py-4 border-t border-gray-700 flex justify-between">
              <p className="text-xs text-gray-500 self-center">
                支持网易云/QQ音乐歌单链接、本地库、fangpi.net搜索
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    if (!playlistName.trim()) { setError('请输入歌单名称'); return }
                    if (songItems.length === 0) { setError('请至少添加一首歌曲'); return }
                    setError('')
                    setStage('tag')
                  }}
                  className="bg-surface hover:bg-surface-lighter text-gray-300 px-4 py-2 rounded-lg text-sm border border-gray-600 transition"
                >
                  直接设置标签
                </button>
                <button
                  onClick={() => {
                    if (!playlistName.trim()) { setError('请输入歌单名称'); return }
                    if (songItems.length === 0) { setError('请至少添加一首歌曲'); return }
                    setError('')
                    startImport()
                  }}
                  className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-lg text-sm transition"
                >
                  下载并导入
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
