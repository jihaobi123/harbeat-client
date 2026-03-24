import React, { useState, useMemo, useCallback } from 'react'
import {
  X, ListMusic, Check, Loader2, CheckCircle, AlertCircle,
  Music, Link2, Upload, Globe, Search, Tag, ChevronLeft,
} from 'lucide-react'
import { useMusicStore } from '../store/useMusicStore'
import { useAuthStore } from '../store/useAuthStore'
import type { Song, DanceStyle, ImportPlaylistResult } from '../types'
import type { ImportPlaylistRequest } from '../services/api'

// ===== 舞种标签选项 =====
const DANCE_STYLES: { value: DanceStyle; label: string; color: string }[] = [
  { value: 'hiphop', label: 'HipHop', color: '#ef4444' },
  { value: 'jazz', label: 'Jazz', color: '#f59e0b' },
  { value: 'breaking', label: 'Breaking', color: '#3b82f6' },
  { value: 'popping', label: 'Popping', color: '#8b5cf6' },
  { value: 'locking', label: 'Locking', color: '#ec4899' },
  { value: 'waacking', label: 'Waacking', color: '#14b8a6' },
  { value: 'house', label: 'House', color: '#06b6d4' },
  { value: 'krump', label: 'Krump', color: '#dc2626' },
  { value: 'funk', label: 'Funk', color: '#f97316' },
  { value: 'urban', label: 'Urban', color: '#a855f7' },
  { value: 'afro', label: 'Afro', color: '#22c55e' },
  { value: 'dancehall', label: 'Dancehall', color: '#eab308' },
  { value: 'other', label: '其他', color: '#64748b' },
]

// ===== 数据类型 =====
type SourceTab = 'link' | 'local' | 'platform'

interface ImportSongItem {
  key: string
  title: string
  artist: string
  album?: string
  duration: number
  bpm: number | null
  tags: DanceStyle[]
  source: 'thirdparty' | 'local' | 'platform'
  localSongId?: string
}

interface Props {
  visible: boolean
  onClose: () => void
}

// ===== 主组件 =====
export const PlaylistImportModal: React.FC<Props> = ({ visible, onClose }) => {
  const user = useAuthStore((s) => s.user)
  const playlistImporting = useMusicStore((s) => s.playlistImporting)
  const playlistImportError = useMusicStore((s) => s.playlistImportError)
  const lastImportResult = useMusicStore((s) => s.lastImportResult)
  const importAndDownloadPlaylist = useMusicStore((s) => s.importAndDownloadPlaylist)
  const clearImportResult = useMusicStore((s) => s.clearImportResult)

  const [step, setStep] = useState<'source' | 'downloading' | 'tag'>('source')
  const [importedPlaylistId, setImportedPlaylistId] = useState<string | null>(null)
  const [downloadResult, setDownloadResult] = useState<{ success: string[]; failed: string[] } | null>(null)
  const [playlistName, setPlaylistName] = useState('')
  const [songItems, setSongItems] = useState<ImportSongItem[]>([])
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())

  const handleClose = () => {
    clearImportResult()
    setStep('source')
    setImportedPlaylistId(null)
    setPlaylistName('')
    setSongItems([])
    setSelectedKeys(new Set())
    onClose()
  }

  const addSongs = useCallback((newItems: ImportSongItem[]) => {
    setSongItems((prev) => {
      const existing = new Set(prev.map((s) => `${s.title}||${s.artist}`.toLowerCase()))
      const toAdd = newItems.filter(
        (s) => !existing.has(`${s.title}||${s.artist}`.toLowerCase())
      )
      return [...prev, ...toAdd]
    })
  }, [])

  const removeSong = (key: string) => {
    setSongItems((prev) => prev.filter((s) => s.key !== key))
    setSelectedKeys((prev) => { const n = new Set(prev); n.delete(key); return n })
  }

  const goBackToSource = () => setStep('source')

  // ===== 标签操作 =====
  const toggleSongTag = (key: string, style: DanceStyle) => {
    setSongItems((prev) =>
      prev.map((s) => {
        if (s.key !== key) return s
        const tags = s.tags.includes(style)
          ? s.tags.filter((t) => t !== style)
          : [...s.tags, style]
        return { ...s, tags }
      })
    )
  }

  const batchSetTag = (style: DanceStyle) => {
    if (selectedKeys.size === 0) return
    setSongItems((prev) =>
      prev.map((s) => {
        if (!selectedKeys.has(s.key)) return s
        if (s.tags.includes(style)) return s
        return { ...s, tags: [...s.tags, style] }
      })
    )
  }

  const batchRemoveTag = (style: DanceStyle) => {
    if (selectedKeys.size === 0) return
    setSongItems((prev) =>
      prev.map((s) => {
        if (!selectedKeys.has(s.key)) return s
        return { ...s, tags: s.tags.filter((t) => t !== style) }
      })
    )
  }

  const toggleSelect = (key: string) => {
    setSelectedKeys((prev) => {
      const n = new Set(prev)
      if (n.has(key)) n.delete(key); else n.add(key)
      return n
    })
  }
  const toggleSelectAll = () => {
    if (selectedKeys.size === songItems.length) {
      setSelectedKeys(new Set())
    } else {
      setSelectedKeys(new Set(songItems.map((s) => s.key)))
    }
  }


  // 新的导入逻辑：先自动下载，再标注标签
  const handleImport = async () => {
    if (!user || songItems.length === 0) return
    setStep('downloading')
    setDownloadResult(null)
    setImportedPlaylistId(null)
    const songList: ImportPlaylistRequest['songList'] = songItems.map((s) => ({
      title: s.title,
      artist: s.artist,
      duration: s.duration,
      bpm: s.bpm,
      tags: s.tags,
    }))
    const result = await importAndDownloadPlaylist(user.id, playlistName.trim(), songList)
    if (result) {
      setImportedPlaylistId(result.playlistId)
      setDownloadResult({ success: result.success, failed: result.failed })
      setStep('tag')
    } else {
      setDownloadResult(null)
      setStep('source')
    }
  }

  const handleSubmitTags = async () => {
    if (!importedPlaylistId) return
    for (let index = 0; index < songItems.length; index += 1) {
      const song = songItems[index]
      await window.electronAPI.updatePlaylistSongTags(
        importedPlaylistId,
        `${importedPlaylistId}-song-${index}`,
        song.tags,
      )
    }
    handleClose()
  }

  if (!visible) return null


  if (lastImportResult) {
    return <ImportResultView result={lastImportResult} onClose={handleClose} />
  }

  if (step === 'downloading') {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
        <div className="bg-surface rounded-xl shadow-2xl w-[420px] border border-border flex flex-col items-center px-8 py-10">
          <Loader2 size={36} className="animate-spin text-primary mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">正在自动匹配并下载歌曲</h3>
          <p className="text-sm text-slate-400 mb-2">系统会自动为每首歌搜索并下载最匹配的音频</p>
          <p className="text-xs text-slate-500">请稍候，完成后将进入标签标注</p>
        </div>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface rounded-xl shadow-2xl w-[720px] max-h-[85vh] flex flex-col border border-border">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2.5">
            {step === 'tag' && (
              <button onClick={goBackToSource} className="p-1 rounded-md text-slate-400 hover:text-white hover:bg-hover transition-all mr-1">
                <ChevronLeft size={18} />
              </button>
            )}
            <ListMusic size={20} className="text-primary" />
            <h2 className="text-base font-semibold text-white">
              {step === 'source' ? '导入歌单 — 添加歌曲' : '导入歌单 — 标注舞种'}
            </h2>
          </div>
          <button onClick={handleClose} className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-hover transition-all">
            <X size={18} />
          </button>
        </div>

        {step === 'source' ? (
          <SourceStep
            playlistName={playlistName}
            setPlaylistName={setPlaylistName}
            songItems={songItems}
            addSongs={addSongs}
            removeSong={removeSong}
            onImport={handleImport}
            importing={playlistImporting}
            error={playlistImportError}
          />
        ) : (
          <>
            <TagStep
              songItems={songItems}
              selectedKeys={selectedKeys}
              toggleSelect={toggleSelect}
              toggleSelectAll={toggleSelectAll}
              toggleSongTag={toggleSongTag}
              batchSetTag={batchSetTag}
              batchRemoveTag={batchRemoveTag}
              onImport={handleSubmitTags}
              importing={playlistImporting}
              error={playlistImportError}
            />
            {/* 下载失败提示 */}
            {downloadResult && downloadResult.failed.length > 0 && (
              <div className="px-6 py-3 mt-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-xs text-yellow-400">
                <div className="font-bold mb-1">以下歌曲暂未找到匹配音频：</div>
                <ul className="list-disc pl-5">
                  {downloadResult.failed.map((t) => <li key={t}>{t}</li>)}
                </ul>
                <div className="mt-1 text-slate-500">你可以后续手动补充或更换关键词重试</div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ========================================
// 来源 Badge
// ========================================
const SourceBadge: React.FC<{ source: ImportSongItem['source'] }> = ({ source }) => {
  const config = {
    thirdparty: { label: '歌单', color: 'text-cyan-400 bg-cyan-400/10' },
    local: { label: '本地', color: 'text-green-400 bg-green-400/10' },
    platform: { label: '平台', color: 'text-indigo-400 bg-indigo-400/10' },
  }[source]
  return (
    <span className={`text-[9px] px-1.5 py-0.5 rounded ${config.color} flex-shrink-0`}>
      {config.label}
    </span>
  )
}

// ========================================
// Step 1: 选择来源 + 添加歌曲
// ========================================
const SourceStep: React.FC<{
  playlistName: string
  setPlaylistName: (v: string) => void
  songItems: ImportSongItem[]
  addSongs: (items: ImportSongItem[]) => void
  removeSong: (key: string) => void
  onImport: () => void
  importing: boolean
  error: string | null
}> = ({ playlistName, setPlaylistName, songItems, addSongs, removeSong, onImport, importing, error }) => {
  const [activeTab, setActiveTab] = useState<SourceTab>('link')

  return (
    <>
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {/* 歌单名称 */}
        <div>
          <label className="block text-xs text-slate-400 mb-1.5">歌单名称</label>
          <input
            type="text"
            value={playlistName}
            onChange={(e) => setPlaylistName(e.target.value)}
            placeholder="例如：Breaking 练习曲"
            className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
          />
        </div>

        {/* 来源 Tab */}
        <div>
          <label className="block text-xs text-slate-400 mb-2">添加歌曲来源</label>
          <div className="flex gap-1 bg-surface-dark rounded-lg p-1">
            {([
              { id: 'link' as const, label: '歌单链接', icon: Link2 },
              { id: 'local' as const, label: '本地曲库', icon: Upload },
              { id: 'platform' as const, label: '平台搜索', icon: Globe },
            ]).map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 text-xs rounded-md transition-all ${
                    activeTab === tab.id
                      ? 'bg-primary/20 text-primary font-medium'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-hover'
                  }`}
                >
                  <Icon size={14} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Tab 内容 */}
        {activeTab === 'link' && <LinkSource addSongs={addSongs} />}
        {activeTab === 'local' && <LocalSource addSongs={addSongs} />}
        {activeTab === 'platform' && <PlatformSource addSongs={addSongs} />}

        {/* 已添加歌曲列表 */}
        {songItems.length > 0 && (
          <div>
            <label className="block text-xs text-slate-400 mb-2">
              已添加 {songItems.length} 首歌曲
            </label>
            <div className="max-h-[200px] overflow-y-auto border border-border rounded-lg divide-y divide-border/40">
              {songItems.map((item) => (
                <div key={item.key} className="flex items-center gap-3 px-3 py-2">
                  <SourceBadge source={item.source} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-200 truncate">{item.title}</p>
                    <p className="text-[11px] text-slate-500 truncate">{item.artist}</p>
                  </div>
                  {item.tags.length > 0 && (
                    <div className="flex gap-1">
                      {item.tags.map((t) => {
                        const style = DANCE_STYLES.find((d) => d.value === t)
                        return (
                          <span key={t} className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ backgroundColor: `${style?.color}20`, color: style?.color }}>
                            {style?.label}
                          </span>
                        )
                      })}
                    </div>
                  )}
                  <button onClick={() => removeSong(item.key)} className="p-1 text-slate-600 hover:text-red-400 transition-colors">
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <AlertCircle size={16} className="text-red-400 flex-shrink-0" />
            <p className="text-xs text-red-400">{error}</p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border flex items-center justify-between">
        <p className="text-[11px] text-slate-500">导入后将立即自动搜索、下载并分析可匹配歌曲</p>
        <button
          onClick={onImport}
          disabled={importing || songItems.length === 0 || !playlistName.trim()}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium transition-all"
        >
          {importing ? (
            <><Loader2 size={14} className="animate-spin" />导入并下载中...</>
          ) : (
            <><ListMusic size={14} />开始导入并自动下载</>
          )}
        </button>
      </div>
    </>
  )
}

// ========================================
// 来源 1: 歌单链接（网易云 / QQ音乐）
// ========================================
const LinkSource: React.FC<{ addSongs: (items: ImportSongItem[]) => void }> = ({ addSongs }) => {
  const [linkText, setLinkText] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState('')
  const [parsedInfo, setParsedInfo] = useState('')

  const handleParse = async () => {
    if (!linkText.trim()) return
    setParsing(true)
    setParseError('')
    setParsedInfo('')

    try {
      const result = await window.electronAPI.parsePlaylistUrl(linkText.trim())
      if (result.error) {
        setParseError(result.error)
        return
      }
      if (!result.playlist || result.playlist.tracks.length === 0) {
        setParseError('未找到歌曲，请检查链接是否正确')
        return
      }

      const tracks = result.playlist.tracks
      const items: ImportSongItem[] = tracks.map((t, i) => ({
        key: `link-${Date.now()}-${i}`,
        title: t.title,
        artist: t.artist,
        album: t.album,
        duration: t.duration,
        bpm: null,
        tags: [],
        source: 'thirdparty' as const,
      }))

      addSongs(items)
      setParsedInfo(`${result.playlist.platform === 'netease' ? '网易云' : 'QQ音乐'} "${result.playlist.name}" — ${tracks.length} 首`)
      setLinkText('')
    } catch (e) {
      setParseError(String(e))
    } finally {
      setParsing(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input
          type="text"
          value={linkText}
          onChange={(e) => setLinkText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleParse()}
          placeholder="粘贴网易云音乐或QQ音乐歌单分享链接..."
          className="flex-1 bg-surface-dark border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
        />
        <button
          onClick={handleParse}
          disabled={parsing || !linkText.trim()}
          className="flex items-center gap-1.5 bg-cyan-600 hover:bg-cyan-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all"
        >
          {parsing ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
          {parsing ? '解析中...' : '解析'}
        </button>
      </div>
      <p className="text-[10px] text-slate-600">
        支持：网易云音乐、QQ音乐歌单链接。可直接粘贴分享文字，如：分享歌单: xxx https://music.163.com/m/playlist?id=xxx
      </p>
      {parseError && (
        <div className="flex items-center gap-2 p-2.5 bg-red-500/10 border border-red-500/20 rounded-lg">
          <AlertCircle size={14} className="text-red-400 flex-shrink-0" />
          <p className="text-xs text-red-400">{parseError}</p>
        </div>
      )}
      {parsedInfo && (
        <div className="flex items-center gap-2 p-2.5 bg-green-500/10 border border-green-500/20 rounded-lg">
          <CheckCircle size={14} className="text-green-400 flex-shrink-0" />
          <p className="text-xs text-green-400">已添加：{parsedInfo}</p>
        </div>
      )}
    </div>
  )
}

// ========================================
// 来源 2: 本地曲库
// ========================================
const LocalSource: React.FC<{ addSongs: (items: ImportSongItem[]) => void }> = ({ addSongs }) => {
  const songs = useMusicStore((s) => s.songs)
  const [localSelected, setLocalSelected] = useState<Set<string>>(new Set())

  const readySongs = useMemo(
    () => songs.filter((s) => s.importStatus === 'ready'),
    [songs]
  )

  const toggleLocal = (id: string) => {
    setLocalSelected((prev) => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  const toggleLocalAll = () => {
    if (localSelected.size === readySongs.length) {
      setLocalSelected(new Set())
    } else {
      setLocalSelected(new Set(readySongs.map((s) => s.id)))
    }
  }

  const handleAddLocal = () => {
    const items: ImportSongItem[] = readySongs
      .filter((s) => localSelected.has(s.id))
      .map((s) => ({
        key: `local-${s.id}`,
        title: s.title,
        artist: s.artist,
        duration: s.duration,
        bpm: s.bpm,
        tags: [],
        source: 'local' as const,
        localSongId: s.id,
      }))
    addSongs(items)
    setLocalSelected(new Set())
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">我的曲库 ({readySongs.length} 首)</span>
        <div className="flex gap-2">
          <button onClick={toggleLocalAll} className="text-xs text-primary hover:text-primary-hover">
            {localSelected.size === readySongs.length ? '取消全选' : '全选'}
          </button>
          {localSelected.size > 0 && (
            <button
              onClick={handleAddLocal}
              className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded hover:bg-primary/30 transition-colors"
            >
              添加 {localSelected.size} 首
            </button>
          )}
        </div>
      </div>
      {readySongs.length === 0 ? (
        <div className="flex flex-col items-center py-6 text-slate-500">
          <Music size={24} className="mb-2 opacity-30" />
          <p className="text-xs">曲库暂无歌曲，请先导入音频文件</p>
        </div>
      ) : (
        <div className="max-h-[200px] overflow-y-auto border border-border rounded-lg divide-y divide-border/40">
          {readySongs.map((song) => (
            <button
              key={song.id}
              onClick={() => toggleLocal(song.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-all ${
                localSelected.has(song.id) ? 'bg-primary/5' : 'hover:bg-hover'
              }`}
            >
              <div className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-all ${
                localSelected.has(song.id) ? 'bg-primary border-primary' : 'border-slate-600'
              }`}>
                {localSelected.has(song.id) && <Check size={10} className="text-white" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-200 truncate">{song.title}</p>
                <p className="text-[11px] text-slate-500 truncate">{song.artist}</p>
              </div>
              {song.bpm && (
                <span className="text-[9px] bg-green-500/10 text-green-400 px-1.5 py-0.5 rounded">
                  {Math.round(song.bpm)} BPM
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ========================================
// 来源 3: 平台搜索
// ========================================
const PlatformSource: React.FC<{ addSongs: (items: ImportSongItem[]) => void }> = ({ addSongs }) => {
  const [query, setQuery] = useState('')
  const [searching, setSearching] = useState(false)
  const [results, setResults] = useState<Array<{ id: string; title: string; artist: string; url: string }>>([])
  const [searchError, setSearchError] = useState('')

  const handleSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    setSearchError('')
    try {
      const result = await window.electronAPI.searchPlatform(query.trim())
      if (result.error) setSearchError(result.error)
      setResults(result.songs || [])
    } catch (e) {
      setSearchError(String(e))
    } finally {
      setSearching(false)
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
      source: 'platform' as const,
    }])
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="搜索 fangpi.net 曲库..."
          className="flex-1 bg-surface-dark border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
        />
        <button
          onClick={handleSearch}
          disabled={searching || !query.trim()}
          className="flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm font-medium transition-all"
        >
          {searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
          搜索
        </button>
      </div>
      {searchError && <p className="text-xs text-red-400">{searchError}</p>}
      {results.length > 0 && (
        <div className="max-h-[200px] overflow-y-auto border border-border rounded-lg divide-y divide-border/40">
          {results.map((song) => (
            <div key={song.id} className="flex items-center gap-2.5 px-3 py-2 hover:bg-hover transition-all">
              <Globe size={14} className="text-indigo-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-200 truncate">{song.title}</p>
                <p className="text-[11px] text-slate-500 truncate">{song.artist}</p>
              </div>
              <button
                onClick={() => addPlatformSong(song)}
                className="text-xs bg-indigo-500/20 text-indigo-400 px-2 py-1 rounded hover:bg-indigo-500/30 transition-colors flex-shrink-0"
              >
                + 添加
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ========================================
// Step 2: 标注舞种标签
// ========================================
const TagStep: React.FC<{
  songItems: ImportSongItem[]
  selectedKeys: Set<string>
  toggleSelect: (key: string) => void
  toggleSelectAll: () => void
  toggleSongTag: (key: string, style: DanceStyle) => void
  batchSetTag: (style: DanceStyle) => void
  batchRemoveTag: (style: DanceStyle) => void
  onImport: () => void
  importing: boolean
  error: string | null
}> = ({
  songItems, selectedKeys, toggleSelect, toggleSelectAll,
  toggleSongTag, batchSetTag, batchRemoveTag, onImport, importing, error,
}) => {
  const untaggedCount = songItems.filter((s) => s.tags.length === 0).length

  return (
    <>
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* 批量标签操作栏 */}
        <div className="px-5 py-3 border-b border-border bg-surface-dark/50">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <button onClick={toggleSelectAll} className="text-xs text-primary hover:text-primary-hover">
                {selectedKeys.size === songItems.length ? '取消全选' : '全选'}
              </button>
              <span className="text-[11px] text-slate-500">已选 {selectedKeys.size}/{songItems.length}</span>
            </div>
            {untaggedCount > 0 && (
              <span className="text-[11px] text-yellow-400">{untaggedCount} 首未标注</span>
            )}
          </div>
          {selectedKeys.size > 0 && (
            <div>
              <p className="text-[10px] text-slate-500 mb-1.5">批量为选中歌曲打标签（左键添加 / 右键移除）：</p>
              <div className="flex flex-wrap gap-1.5">
                {DANCE_STYLES.map((style) => (
                  <button
                    key={style.value}
                    onClick={() => batchSetTag(style.value)}
                    onContextMenu={(e) => { e.preventDefault(); batchRemoveTag(style.value) }}
                    className="px-2 py-0.5 text-[11px] rounded-full border transition-all hover:opacity-80"
                    style={{ borderColor: `${style.color}40`, color: style.color, backgroundColor: `${style.color}10` }}
                  >
                    + {style.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 歌曲列表 + 每首歌的标签 */}
        <div className="flex-1 overflow-y-auto">
          {songItems.map((item) => (
            <div
              key={item.key}
              className={`px-5 py-3 border-b border-border/40 transition-all ${
                selectedKeys.has(item.key) ? 'bg-primary/5' : 'hover:bg-hover/50'
              }`}
            >
              <div className="flex items-center gap-3">
                <button
                  onClick={() => toggleSelect(item.key)}
                  className={`w-5 h-5 rounded border flex items-center justify-center flex-shrink-0 transition-all ${
                    selectedKeys.has(item.key) ? 'bg-primary border-primary' : 'border-slate-600 hover:border-slate-400'
                  }`}
                >
                  {selectedKeys.has(item.key) && <Check size={12} className="text-white" />}
                </button>
                <SourceBadge source={item.source} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-200 truncate">{item.title}</p>
                  <p className="text-[11px] text-slate-500 truncate">{item.artist}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2 ml-8">
                {DANCE_STYLES.map((style) => {
                  const active = item.tags.includes(style.value)
                  return (
                    <button
                      key={style.value}
                      onClick={() => toggleSongTag(item.key, style.value)}
                      className={`px-2 py-0.5 text-[10px] rounded-full border transition-all ${
                        active
                          ? 'font-medium'
                          : 'bg-surface-dark border-border/60 text-slate-500 hover:text-slate-300 hover:border-slate-500'
                      }`}
                      style={active ? { backgroundColor: `${style.color}20`, borderColor: `${style.color}60`, color: style.color } : undefined}
                    >
                      {style.label}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border flex items-center justify-between">
        {error ? (
          <div className="flex items-center gap-1.5">
            <AlertCircle size={14} className="text-red-400" />
            <p className="text-xs text-red-400">{error}</p>
          </div>
        ) : (
          <p className="text-[11px] text-slate-500">
            点击歌曲下方标签标注舞种，支持多选歌曲后批量标注
          </p>
        )}
        <button
          onClick={onImport}
          disabled={importing || songItems.length === 0}
          className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-40 disabled:cursor-not-allowed text-white px-5 py-2 rounded-lg text-sm font-medium transition-all"
        >
          {importing ? (
            <><Loader2 size={15} className="animate-spin" />保存中...</>
          ) : (
            <><Tag size={15} />保存标签 ({songItems.length} 首)</>
          )}
        </button>
      </div>
    </>
  )
}

// ========================================
// 导入结果
// ========================================
const ImportResultView: React.FC<{ result: ImportPlaylistResult; onClose: () => void }> = ({
  result,
  onClose,
}) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
    <div className="bg-surface rounded-xl shadow-2xl w-[420px] border border-border">
      <div className="flex flex-col items-center px-6 py-8">
        <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mb-4">
          <CheckCircle size={32} className="text-green-400" />
        </div>
        <h3 className="text-lg font-semibold text-white mb-2">歌单导入成功</h3>
        <div className="w-full space-y-3 mt-4 p-4 bg-surface-dark rounded-lg">
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">歌单 ID</span>
            <span className="text-white font-mono text-xs">{result.playlistId}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">成功导入</span>
            <span className="text-green-400 font-medium">{result.importCount} 首</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">待分析（缺少标签）</span>
            <span className={`font-medium ${result.pendingAnalysisCount > 0 ? 'text-yellow-400' : 'text-slate-500'}`}>
              {result.pendingAnalysisCount} 首
            </span>
          </div>
        </div>
        {result.pendingAnalysisCount > 0 && (
          <p className="text-xs text-slate-500 mt-3 text-center">
            待分析歌曲将自动进入分析队列，完成后会自动关联舞种标签
          </p>
        )}
        <button
          onClick={onClose}
          className="mt-6 bg-primary hover:bg-primary-hover text-white px-8 py-2.5 rounded-lg text-sm font-medium transition-all"
        >
          完成
        </button>
      </div>
    </div>
  </div>
)
