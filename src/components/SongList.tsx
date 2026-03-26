import React, { useMemo } from 'react'
import { CheckCircle, Download, FileAudio, Globe, LayoutGrid, LayoutList, Library, Loader2, Music, Plus } from 'lucide-react'

import type { DanceStyle, Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration, formatFileSize } from '../utils/format'
import { SearchBar } from './SearchBar'

const ALL_STYLES: DanceStyle[] = [
  'hiphop', 'jazz', 'breaking', 'popping', 'locking', 'waacking',
  'house', 'krump', 'funk', 'urban', 'afro', 'dancehall', 'other',
]

export const SongList: React.FC = () => {
  const currentView = useMusicStore((state) => state.currentView)
  const selectedSongId = useMusicStore((state) => state.selectedSongId)
  const selectSong = useMusicStore((state) => state.selectSong)
  const songs = useMusicStore((state) => state.songs)
  const platformSongs = useMusicStore((state) => state.platformSongs)
  const searchQuery = useMusicStore((state) => state.searchQuery)
  const addPlatformSongToLibrary = useMusicStore((state) => state.addPlatformSongToLibrary)
  const addPlaylistSongToLibrary = useMusicStore((state) => state.addPlaylistSongToLibrary)
  const downloadSong = useMusicStore((state) => state.downloadSong)
  const platformSearchLoading = useMusicStore((state) => state.platformSearchLoading)
  const platformSearchError = useMusicStore((state) => state.platformSearchError)
  const displayMode = useMusicStore((state) => state.displayMode)
  const setDisplayMode = useMusicStore((state) => state.setDisplayMode)
  const tagFilter = useMusicStore((state) => state.tagFilter)
  const setTagFilter = useMusicStore((state) => state.setTagFilter)
  const currentPlaylistId = useMusicStore((state) => state.currentPlaylistId)
  const currentPlaylistSongs = useMusicStore((state) => state.currentPlaylistSongs)
  const playlists = useMusicStore((state) => state.playlists)

  const isPlatformView = currentView === 'platform'
  const isRecentView = currentView === 'recent'
  const isPlaylistView = currentView === 'playlist'

  const displaySongs = useMemo(() => {
    const query = searchQuery.toLowerCase()
    const textFilter = (song: Song) =>
      !query || song.title.toLowerCase().includes(query) || song.artist.toLowerCase().includes(query)
    const danceFilter = (song: Song) => !tagFilter || song.tags.includes(tagFilter)

    if (isPlaylistView) return currentPlaylistSongs.filter(textFilter).filter(danceFilter)
    if (isPlatformView) return platformSongs
    if (isRecentView) return [...songs].filter(textFilter).sort((a, b) => b.createdAt - a.createdAt).slice(0, 20)
    return songs.filter(textFilter).filter(danceFilter)
  }, [currentPlaylistSongs, isPlatformView, isPlaylistView, isRecentView, platformSongs, searchQuery, songs, tagFilter])

  const currentPlaylist = playlists.find((playlist) => playlist.id === currentPlaylistId)
  const title = isPlaylistView && currentPlaylist
    ? currentPlaylist.name
    : isPlatformView
    ? 'Platform'
    : isRecentView
    ? 'Recent'
    : 'My Library'

  const emptyText = platformSearchError
    ? platformSearchError
    : isPlatformView
    ? 'Search the platform library or browse downloaded songs.'
    : isPlaylistView
    ? 'This playlist is empty.'
    : 'No songs available yet.'

  return (
    <div className="flex-1 flex flex-col h-full min-w-0">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-white">{title}</h2>
          <div className="flex items-center gap-2">
            {!isPlatformView && (
              <div className="flex bg-surface-dark rounded-md border border-border/50">
                <button
                  onClick={() => setDisplayMode('list')}
                  className={`p-1.5 rounded-l-md transition-all ${displayMode === 'list' ? 'bg-primary/20 text-primary' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  <LayoutList size={14} />
                </button>
                <button
                  onClick={() => setDisplayMode('grid')}
                  className={`p-1.5 rounded-r-md transition-all ${displayMode === 'grid' ? 'bg-primary/20 text-primary' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  <LayoutGrid size={14} />
                </button>
              </div>
            )}
            <span className="text-[11px] text-slate-500">{displaySongs.length} songs</span>
          </div>
        </div>
        <SearchBar />

        {!isPlatformView && (
          <div className="flex flex-wrap gap-1.5 mt-2.5">
            <button
              onClick={() => setTagFilter(null)}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-all ${
                !tagFilter ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/50 text-slate-500'
              }`}
            >
              All
            </button>
            {ALL_STYLES.map((style) => (
              <button
                key={style}
                onClick={() => setTagFilter(tagFilter === style ? null : style)}
                className={`text-[10px] px-2 py-0.5 rounded-full border transition-all ${
                  tagFilter === style ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/50 text-slate-500'
                }`}
              >
                {style}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {platformSearchLoading && isPlatformView ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <Loader2 size={28} className="animate-spin mb-3" />
            <p className="text-sm">Searching platform music...</p>
          </div>
        ) : displaySongs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-slate-500">
            <Music size={48} className="mb-3 opacity-20" />
            <p className="text-sm">{emptyText}</p>
          </div>
        ) : displayMode === 'grid' && !isPlatformView ? (
          <div className="grid grid-cols-2 gap-2.5 p-3">
            {displaySongs.map((song) => (
              <SongCard key={song.id} song={song} selected={selectedSongId === song.id} onClick={() => selectSong(song.id)} />
            ))}
          </div>
        ) : (
          <div className="divide-y divide-border/40">
            {displaySongs.map((song) => (
              <button
                key={song.id}
                onClick={() => selectSong(song.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-all group ${
                  selectedSongId === song.id ? 'bg-primary/10 border-l-2 border-primary' : 'hover:bg-hover border-l-2 border-transparent'
                }`}
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${song.platformId ? 'bg-indigo-500/10' : 'bg-surface-dark'}`}>
                  {song.platformId ? <Globe size={18} className="text-indigo-400" /> : <FileAudio size={18} className="text-slate-500" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-slate-100 truncate">{song.title}</p>
                  <p className="text-[11px] text-slate-500 truncate mt-0.5">
                    {song.artist}
                    {song.format && ` · ${song.format.toUpperCase()}`}
                    {song.fileSize > 0 && ` · ${formatFileSize(song.fileSize)}`}
                    {song.bpm && ` · ${song.bpm} BPM`}
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {song.duration > 0 && <span className="text-[11px] text-slate-500 font-mono">{formatDuration(song.duration)}</span>}
                  {isPlatformView && song.platformId && (
                    <button
                      onClick={(event) => {
                        event.stopPropagation()
                        void downloadSong(song.id)
                      }}
                      className="p-1.5 rounded-md text-slate-500 hover:text-primary hover:bg-primary/10 transition-all"
                    >
                      {song.downloadStatus === 'downloaded' ? <CheckCircle size={14} className="text-green-400" /> : <Download size={14} />}
                    </button>
                  )}
                  {isPlatformView && !song.platformId && (
                    <button
                      onClick={(event) => {
                        event.stopPropagation()
                        addPlatformSongToLibrary(song.id)
                      }}
                      className="p-1.5 rounded-md text-slate-500 hover:text-primary hover:bg-primary/10 transition-all"
                    >
                      <Plus size={14} />
                    </button>
                  )}
                  {isPlaylistView && song.playlistId === undefined && (
                    <span className="text-[10px] text-green-400">已入库</span>
                  )}
                  {isPlaylistView && song.playlistId !== undefined && (
                    <button
                      onClick={(event) => {
                        event.stopPropagation()
                        addPlaylistSongToLibrary(song.id)
                      }}
                      className="p-1.5 rounded-md text-slate-500 hover:text-green-400 hover:bg-green-500/10 transition-all"
                      title="添加到曲库"
                    >
                      <Library size={14} />
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

const SongCard: React.FC<{ song: Song; selected: boolean; onClick: () => void }> = ({ song, selected, onClick }) => (
  <button
    onClick={onClick}
    className={`p-3 rounded-xl border text-left transition-all ${selected ? 'border-primary bg-primary/10' : 'border-border bg-surface hover:bg-hover'}`}
  >
    <div className="flex items-center justify-between mb-2">
      {song.platformId ? <Globe size={18} className="text-indigo-400" /> : <FileAudio size={18} className="text-slate-500" />}
      {song.bpm && <span className="text-[10px] text-primary">{song.bpm} BPM</span>}
    </div>
    <p className="text-sm font-medium text-slate-100 truncate">{song.title}</p>
    <p className="text-[11px] text-slate-500 truncate mt-1">{song.artist}</p>
  </button>
)
