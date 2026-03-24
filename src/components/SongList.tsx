import React, { useMemo } from 'react'
import { Music, FileAudio, Plus, Check, ExternalLink, Globe, Download, Loader2, CheckCircle, LayoutGrid, LayoutList, BarChart3 } from 'lucide-react'
import { Song, DanceStyle } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration, formatFileSize } from '../utils/format'
import { SearchBar } from './SearchBar'

// 舞种标签配色
const DANCE_STYLE_COLORS: Record<string, string> = {
  hiphop: '#ef4444', jazz: '#f59e0b', breaking: '#3b82f6', popping: '#8b5cf6',
  locking: '#ec4899', waacking: '#14b8a6', house: '#06b6d4', krump: '#dc2626',
  funk: '#f97316', urban: '#a855f7', afro: '#22c55e', dancehall: '#eab308', other: '#64748b',
}

const DANCE_STYLE_LABELS: Record<string, string> = {
  hiphop: 'HipHop', jazz: 'Jazz', breaking: 'Breaking', popping: 'Popping',
  locking: 'Locking', waacking: 'Waacking', house: 'House', krump: 'Krump',
  funk: 'Funk', urban: 'Urban', afro: 'Afro', dancehall: 'Dancehall', other: '其他',
}

const ALL_STYLES: DanceStyle[] = [
  'hiphop', 'jazz', 'breaking', 'popping', 'locking', 'waacking',
  'house', 'krump', 'funk', 'urban', 'afro', 'dancehall', 'other',
]

export const SongList: React.FC = () => {
  const currentView = useMusicStore((s) => s.currentView)
  const selectedSongId = useMusicStore((s) => s.selectedSongId)
  const selectSong = useMusicStore((s) => s.selectSong)
  const songs = useMusicStore((s) => s.songs)
  const platformSongsData = useMusicStore((s) => s.platformSongs)
  const searchQuery = useMusicStore((s) => s.searchQuery)
  const addPlatformSongToLibrary = useMusicStore((s) => s.addPlatformSongToLibrary)
  const downloadSong = useMusicStore((s) => s.downloadSong)
  const platformSearchLoading = useMusicStore((s) => s.platformSearchLoading)
  const platformSearchError = useMusicStore((s) => s.platformSearchError)
  const displayMode = useMusicStore((s) => s.displayMode)
  const setDisplayMode = useMusicStore((s) => s.setDisplayMode)
  const tagFilter = useMusicStore((s) => s.tagFilter)
  const setTagFilter = useMusicStore((s) => s.setTagFilter)
  const currentPlaylistId = useMusicStore((s) => s.currentPlaylistId)
  const currentPlaylistSongs = useMusicStore((s) => s.currentPlaylistSongs)
  const playlists = useMusicStore((s) => s.playlists)

  const isPlatformView = currentView === 'platform'
  const isRecentView = currentView === 'recent'
  const isPlaylistView = currentView === 'playlist'

  const displaySongs = useMemo(() => {
    const q = searchQuery.toLowerCase()
    const filterFn = (s: Song) =>
      !q || s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q)

    const tagFilterFn = (s: Song) =>
      !tagFilter || (s.tags && s.tags.includes(tagFilter))

    if (isPlaylistView) {
      return currentPlaylistSongs.filter(filterFn).filter(tagFilterFn)
    }
    if (isPlatformView) {
      return platformSongsData
    }
    if (isRecentView) {
      return [...songs]
        .filter(filterFn)
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, 20)
    }
    return songs.filter(filterFn).filter(tagFilterFn)
  }, [songs, platformSongsData, searchQuery, isPlatformView, isRecentView, isPlaylistView, currentPlaylistSongs, tagFilter])

  const currentPlaylist = playlists.find((p) => p.id === currentPlaylistId)
  const title = isPlaylistView && currentPlaylist
    ? currentPlaylist.name
    : isPlatformView ? '平台曲库' : isRecentView ? '最近导入' : '我的曲库'

  const showTagFilter = currentView === 'my-library' || isPlaylistView
  const showDisplayToggle = currentView === 'my-library' || isPlaylistView

  const isInMyLibrary = (song: Song) => {
    return songs.some(
      (s) => s.title === song.title && s.sourceType === 'internal_catalog'
    )
  }

  return (
    <div className="flex-1 flex flex-col h-full min-w-0">
      {/* Header */}
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <div className="flex items-center gap-2">
            {showDisplayToggle && (
              <div className="flex bg-surface-dark rounded-md border border-border/50">
                <button
                  onClick={() => setDisplayMode('list')}
                  className={`p-1.5 rounded-l-md transition-all ${displayMode === 'list' ? 'bg-primary/20 text-primary' : 'text-slate-500 hover:text-slate-300'}`}
                  title="列表视图"
                >
                  <LayoutList size={14} />
                </button>
                <button
                  onClick={() => setDisplayMode('grid')}
                  className={`p-1.5 rounded-r-md transition-all ${displayMode === 'grid' ? 'bg-primary/20 text-primary' : 'text-slate-500 hover:text-slate-300'}`}
                  title="卡片视图"
                >
                  <LayoutGrid size={14} />
                </button>
              </div>
            )}
            <span className="text-[11px] text-slate-500">
              {displaySongs.length} 首歌曲
            </span>
          </div>
        </div>
        <SearchBar />

        {/* Tag Filter */}
        {showTagFilter && (
          <div className="flex flex-wrap gap-1.5 mt-2.5">
            <button
              onClick={() => setTagFilter(null)}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-all ${
                !tagFilter ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/50 text-slate-500 hover:text-slate-300'
              }`}
            >
              全部
            </button>
            {ALL_STYLES.map((style) => (
              <button
                key={style}
                onClick={() => setTagFilter(tagFilter === style ? null : style)}
                className={`text-[10px] px-2 py-0.5 rounded-full border transition-all ${
                  tagFilter === style
                    ? 'border-current bg-current/10'
                    : 'border-border/50 hover:border-current/30'
                }`}
                style={{ color: tagFilter === style ? DANCE_STYLE_COLORS[style] : undefined }}
              >
                {DANCE_STYLE_LABELS[style]}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Song List */}
      <div className="flex-1 overflow-y-auto">
        {platformSearchLoading && isPlatformView ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <div className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin mb-3" />
            <p className="text-sm">正在搜索平台曲库...</p>
          </div>
        ) : displaySongs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <Music size={48} className="mb-3 opacity-20" />
            <p className="text-sm">
              {platformSearchError
                ? `搜索出错: ${platformSearchError}`
                : tagFilter
                ? `没有 ${DANCE_STYLE_LABELS[tagFilter]} 标签的歌曲`
                : searchQuery && isPlatformView
                ? '没有找到匹配的歌曲'
                : isPlatformView
                ? '输入关键词搜索平台曲库'
                : isPlaylistView
                ? '歌单为空'
                : searchQuery
                ? '没有找到匹配的歌曲'
                : '暂无歌曲，点击左下角导入'}
            </p>
            {isPlatformView && !searchQuery && (
              <p className="text-xs text-slate-600 mt-2">已导入的本地歌曲也会显示在这里</p>
            )}
          </div>
        ) : displayMode === 'grid' && showDisplayToggle ? (
          <GridView
            songs={displaySongs}
            selectedSongId={selectedSongId}
            selectSong={selectSong}
          />
        ) : (
          <div className="divide-y divide-border/40">
            {displaySongs.map((song) => (
              <button
                key={song.id}
                onClick={() => selectSong(song.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-all group ${
                  selectedSongId === song.id
                    ? 'bg-primary/10 border-l-2 border-primary'
                    : 'hover:bg-hover border-l-2 border-transparent'
                }`}
              >
                {/* Icon */}
                <div
                  className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${
                    selectedSongId === song.id
                      ? 'bg-primary/20'
                      : song.platformId
                      ? 'bg-indigo-500/10'
                      : 'bg-surface-dark'
                  }`}
                >
                  {song.platformId ? (
                    <Globe size={18} className={selectedSongId === song.id ? 'text-primary' : 'text-indigo-400'} />
                  ) : (
                    <FileAudio size={18} className={selectedSongId === song.id ? 'text-primary' : 'text-slate-500'} />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-100 truncate">{song.title}</p>
                  <p className="text-[11px] text-slate-500 truncate mt-0.5">
                    {song.artist}
                    {song.sourceType === 'local_file' && song.format && <> · {song.format.toUpperCase()}</>}
                    {song.fileSize > 0 && <> · {formatFileSize(song.fileSize)}</>}
                    {song.bpm && <> · {song.bpm} BPM</>}
                    {song.platformId && <span className="ml-1.5 text-indigo-400/70">· fangpi.net</span>}
                    {song.sourceType === 'local_file' && isPlatformView && <span className="ml-1.5 text-green-400/70">· 本地导入</span>}
                  </p>
                  {/* Tags */}
                  {song.tags && song.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {song.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[9px] px-1.5 py-0 rounded"
                          style={{ color: DANCE_STYLE_COLORS[tag], backgroundColor: `${DANCE_STYLE_COLORS[tag]}15` }}
                        >
                          {DANCE_STYLE_LABELS[tag] || tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Right side */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {song.importStatus === 'importing' ? (
                    <span className="text-[11px] text-yellow-400 flex items-center gap-1">
                      <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
                      导入中
                    </span>
                  ) : song.importStatus === 'error' ? (
                    <span className="text-[11px] text-red-400">错误</span>
                  ) : song.duration > 0 ? (
                    <span className="text-[11px] text-slate-500 font-mono">{formatDuration(song.duration)}</span>
                  ) : null}

                  {song.platformUrl && (
                    <button
                      onClick={(e) => { e.stopPropagation(); window.open(song.platformUrl, '_blank') }}
                      className="p-1.5 rounded-md text-slate-500 hover:text-indigo-400 hover:bg-indigo-400/10 opacity-0 group-hover:opacity-100 transition-all"
                      title="在 fangpi.net 打开"
                    >
                      <ExternalLink size={14} />
                    </button>
                  )}

                  {isPlatformView && song.platformId && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        if (song.downloadStatus !== 'downloaded' && song.downloadStatus !== 'downloading') {
                          downloadSong(song.id)
                        }
                      }}
                      disabled={song.downloadStatus === 'downloading'}
                      className={`p-1.5 rounded-md transition-all ${
                        song.downloadStatus === 'downloaded'
                          ? 'text-green-400 bg-green-400/10'
                          : song.downloadStatus === 'downloading'
                          ? 'text-yellow-400 bg-yellow-400/10'
                          : song.downloadStatus === 'error'
                          ? 'text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100'
                          : 'text-slate-500 hover:text-primary hover:bg-primary/10 opacity-0 group-hover:opacity-100'
                      }`}
                      title={
                        song.downloadStatus === 'downloaded' ? '已下载到曲库'
                          : song.downloadStatus === 'downloading' ? '下载中...'
                          : song.downloadStatus === 'error' ? '下载失败，点击重试'
                          : '下载到曲库'
                      }
                    >
                      {song.downloadStatus === 'downloaded' ? <CheckCircle size={14} />
                        : song.downloadStatus === 'downloading' ? <Loader2 size={14} className="animate-spin" />
                        : <Download size={14} />}
                    </button>
                  )}

                  {isPlatformView && !song.platformId && (
                    <button
                      onClick={(e) => { e.stopPropagation(); addPlatformSongToLibrary(song.id) }}
                      className={`p-1.5 rounded-md transition-all ${
                        isInMyLibrary(song) ? 'text-green-400 bg-green-400/10'
                          : 'text-slate-500 hover:text-primary hover:bg-primary/10 opacity-0 group-hover:opacity-100'
                      }`}
                      title={isInMyLibrary(song) ? '已加入曲库' : '加入我的曲库'}
                    >
                      {isInMyLibrary(song) ? <Check size={14} /> : <Plus size={14} />}
                    </button>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ===== 卡片视图 =====
const GridView: React.FC<{
  songs: Song[]
  selectedSongId: string | null
  selectSong: (id: string | null) => void
}> = ({ songs, selectedSongId, selectSong }) => (
  <div className="grid grid-cols-2 gap-2.5 p-3">
    {songs.map((song) => (
      <button
        key={song.id}
        onClick={() => selectSong(song.id)}
        className={`text-left p-3 rounded-xl border transition-all group ${
          selectedSongId === song.id
            ? 'bg-primary/10 border-primary/30'
            : 'bg-surface-dark border-border/30 hover:bg-hover hover:border-border/60'
        }`}
      >
        {/* Cover placeholder */}
        <div className={`w-full aspect-square rounded-lg flex items-center justify-center mb-2.5 ${
          song.platformId ? 'bg-indigo-500/10' : 'bg-primary/5'
        }`}>
          {song.bpm ? (
            <div className="text-center">
              <BarChart3 size={24} className="text-primary/50 mx-auto mb-1" />
              <span className="text-lg font-bold text-white">{song.bpm}</span>
              <span className="text-[10px] text-slate-500 block">BPM</span>
            </div>
          ) : (
            <Music size={28} className="text-slate-600/50" />
          )}
        </div>

        <p className="text-xs font-medium text-slate-100 truncate">{song.title}</p>
        <p className="text-[10px] text-slate-500 truncate mt-0.5">{song.artist}</p>

        {song.tags && song.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {song.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="text-[8px] px-1 py-0 rounded"
                style={{ color: DANCE_STYLE_COLORS[tag], backgroundColor: `${DANCE_STYLE_COLORS[tag]}15` }}
              >
                {DANCE_STYLE_LABELS[tag] || tag}
              </span>
            ))}
            {song.tags.length > 3 && (
              <span className="text-[8px] text-slate-500">+{song.tags.length - 3}</span>
            )}
          </div>
        )}

        <div className="flex items-center gap-1.5 mt-1.5">
          {song.duration > 0 && (
            <span className="text-[10px] text-slate-500 font-mono">{formatDuration(song.duration)}</span>
          )}
          {song.analysisStatus === 'completed' && (
            <span className="text-[10px] text-green-400">✓ 已分析</span>
          )}
        </div>
      </button>
    ))}
  </div>
)
