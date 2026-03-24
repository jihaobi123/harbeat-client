import React, { useMemo } from 'react'
import { Music, FileAudio, Plus, Check, ExternalLink, Globe, Download, Loader2, CheckCircle } from 'lucide-react'
import { Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration, formatFileSize } from '../utils/format'
import { SearchBar } from './SearchBar'

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

  const isPlatformView = currentView === 'platform'
  const isRecentView = currentView === 'recent'

  const displaySongs = useMemo(() => {
    const q = searchQuery.toLowerCase()
    const filterFn = (s: Song) =>
      !q || s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q)

    if (isPlatformView) {
      // Platform view uses server-side search, show all results
      return platformSongsData
    }
    if (isRecentView) {
      return [...songs]
        .filter(filterFn)
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, 20)
    }
    return songs.filter(filterFn)
  }, [songs, platformSongsData, searchQuery, isPlatformView, isRecentView])

  const title = isPlatformView ? '平台曲库' : isRecentView ? '最近导入' : '我的曲库'

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
          <span className="text-[11px] text-slate-500">
            {displaySongs.length} 首歌曲
          </span>
        </div>
        <SearchBar />
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
                : searchQuery && isPlatformView
                ? '没有找到匹配的歌曲'
                : isPlatformView
                ? '输入关键词搜索平台曲库'
                : searchQuery
                ? '没有找到匹配的歌曲'
                : '暂无歌曲，点击左下角导入'}
            </p>
            {isPlatformView && !searchQuery && (
              <p className="text-xs text-slate-600 mt-2">已导入的本地歌曲也会显示在这里</p>
            )}
          </div>
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
                    <Globe
                      size={18}
                      className={
                        selectedSongId === song.id
                          ? 'text-primary'
                          : 'text-indigo-400'
                      }
                    />
                  ) : (
                    <FileAudio
                      size={18}
                      className={
                        selectedSongId === song.id
                          ? 'text-primary'
                          : 'text-slate-500'
                      }
                    />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-100 truncate">
                    {song.title}
                  </p>
                  <p className="text-[11px] text-slate-500 truncate mt-0.5">
                    {song.artist}
                    {song.sourceType === 'local_file' && song.format && (
                      <> · {song.format.toUpperCase()}</>
                    )}
                    {song.fileSize > 0 && (
                      <> · {formatFileSize(song.fileSize)}</>
                    )}
                    {song.platformId && (
                      <span className="ml-1.5 text-indigo-400/70">· fangpi.net</span>
                    )}
                    {song.sourceType === 'local_file' && isPlatformView && (
                      <span className="ml-1.5 text-green-400/70">· 本地导入</span>
                    )}
                  </p>
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
                    <span className="text-[11px] text-slate-500 font-mono">
                      {formatDuration(song.duration)}
                    </span>
                  ) : null}

                  {/* External link for fangpi songs */}
                  {song.platformUrl && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        window.open(song.platformUrl, '_blank')
                      }}
                      className="p-1.5 rounded-md text-slate-500 hover:text-indigo-400 hover:bg-indigo-400/10 opacity-0 group-hover:opacity-100 transition-all"
                      title="在 fangpi.net 打开"
                    >
                      <ExternalLink size={14} />
                    </button>
                  )}

                  {/* Download button for fangpi songs */}
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
                        song.downloadStatus === 'downloaded'
                          ? '已下载到曲库'
                          : song.downloadStatus === 'downloading'
                          ? '下载中...'
                          : song.downloadStatus === 'error'
                          ? '下载失败，点击重试'
                          : '下载到曲库'
                      }
                    >
                      {song.downloadStatus === 'downloaded' ? (
                        <CheckCircle size={14} />
                      ) : song.downloadStatus === 'downloading' ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Download size={14} />
                      )}
                    </button>
                  )}

                  {isPlatformView && !song.platformId && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        addPlatformSongToLibrary(song.id)
                      }}
                      className={`p-1.5 rounded-md transition-all ${
                        isInMyLibrary(song)
                          ? 'text-green-400 bg-green-400/10'
                          : 'text-slate-500 hover:text-primary hover:bg-primary/10 opacity-0 group-hover:opacity-100'
                      }`}
                      title={
                        isInMyLibrary(song) ? '已加入曲库' : '加入我的曲库'
                      }
                    >
                      {isInMyLibrary(song) ? (
                        <Check size={14} />
                      ) : (
                        <Plus size={14} />
                      )}
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
