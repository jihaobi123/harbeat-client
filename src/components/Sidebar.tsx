import React, { useState } from 'react'
import {
  Clock,
  Globe,
  Library,
  ListMusic,
  LogOut,
  Music,
  Trash2,
  Upload,
  User,
} from 'lucide-react'

import { getAudioDuration } from '../utils/format'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import { PlaylistImportModal } from './PlaylistImportModal'

const navItems = [
  { id: 'my-library' as const, label: 'My Library', icon: Library },
  { id: 'platform' as const, label: 'Platform', icon: Globe },
  { id: 'recent' as const, label: 'Recent', icon: Clock },
]

export const Sidebar: React.FC = () => {
  const currentView = useMusicStore((state) => state.currentView)
  const setView = useMusicStore((state) => state.setView)
  const songsCount = useMusicStore((state) => state.songs.length)
  const playlists = useMusicStore((state) => state.playlists)
  const currentPlaylistId = useMusicStore((state) => state.currentPlaylistId)
  const viewPlaylist = useMusicStore((state) => state.viewPlaylist)
  const deletePlaylistAction = useMusicStore((state) => state.deletePlaylist)
  const user = useAuthStore((state) => state.user)
  const logout = useAuthStore((state) => state.logout)
  const [showPlaylistImport, setShowPlaylistImport] = useState(false)

  const handleImport = async () => {
    const files = await window.electronAPI.openAudioFiles()
    if (!files || files.length === 0) return

    const validFiles = files.filter((file) => !file.error)
    if (validFiles.length === 0) return

    const newSongs = useMusicStore.getState().addSongs(validFiles)

    for (const song of newSongs) {
      try {
        const url = await window.electronAPI.getAudioUrl(song.sourcePath)
        const duration = await getAudioDuration(url)
        useMusicStore.getState().updateSong(song.id, {
          duration,
          importStatus: 'ready',
        })
      } catch {
        useMusicStore.getState().updateSong(song.id, {
          importStatus: 'error',
        })
      }
    }
  }

  return (
    <div className="w-56 bg-surface border-r border-border flex flex-col h-full flex-shrink-0">
      <div className="px-5 py-4 border-b border-border">
        <h1 className="text-lg font-bold text-white flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <span className="text-primary text-base">H</span>
          </div>
          Harbeat
        </h1>
        <p className="text-[11px] text-slate-500 mt-1 ml-[42px]">Unified workspace</p>
      </div>

      <nav className="flex-1 py-3 overflow-y-auto">
        <p className="px-5 text-[10px] font-semibold text-slate-600 uppercase tracking-wider mb-2">
          Navigation
        </p>

        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = currentView === item.id
          return (
            <button
              key={item.id}
              onClick={() => setView(item.id)}
              className={`w-full flex items-center gap-3 px-5 py-2.5 text-sm transition-all ${
                isActive
                  ? 'bg-primary/10 text-primary border-r-2 border-primary font-medium'
                  : 'text-slate-400 hover:bg-hover hover:text-slate-200 border-r-2 border-transparent'
              }`}
            >
              <Icon size={18} />
              <span>{item.label}</span>
              {item.id === 'my-library' && songsCount > 0 && (
                <span className="ml-auto text-[10px] bg-primary/20 text-primary px-1.5 py-0.5 rounded-full font-medium">
                  {songsCount}
                </span>
              )}
            </button>
          )
        })}

        {playlists.length > 0 && (
          <>
            <p className="px-5 text-[10px] font-semibold text-slate-600 uppercase tracking-wider mb-2 mt-4">
              Playlists
            </p>
            {playlists.map((playlist) => {
              const isActive = currentView === 'playlist' && currentPlaylistId === playlist.id
              return (
                <div
                  key={playlist.id}
                  className={`w-full flex items-center gap-2.5 px-5 py-2 text-sm transition-all group cursor-pointer ${
                    isActive
                      ? 'bg-primary/10 text-primary border-r-2 border-primary font-medium'
                      : 'text-slate-400 hover:bg-hover hover:text-slate-200 border-r-2 border-transparent'
                  }`}
                  onClick={() => viewPlaylist(playlist.id)}
                >
                  <Music size={16} className="flex-shrink-0" />
                  <span className="truncate flex-1">{playlist.name}</span>
                  <span className="text-[10px] text-slate-600 flex-shrink-0">
                    {playlist.songCount}
                  </span>
                  <button
                    onClick={(event) => {
                      event.stopPropagation()
                      deletePlaylistAction(playlist.id)
                    }}
                    className="p-0.5 rounded text-slate-600 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-all flex-shrink-0"
                    title="Delete playlist"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              )
            })}
          </>
        )}
      </nav>

      <div className="p-4 border-t border-border space-y-2">
        <button
          onClick={handleImport}
          className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white py-2.5 px-4 rounded-lg text-sm font-medium transition-all active:scale-[0.97]"
        >
          <Upload size={16} />
          Import Audio
        </button>
        {user && (
          <button
            onClick={() => setShowPlaylistImport(true)}
            className="w-full flex items-center justify-center gap-2 bg-surface-dark hover:bg-hover border border-border text-slate-300 py-2.5 px-4 rounded-lg text-sm font-medium transition-all active:scale-[0.97]"
          >
            <ListMusic size={16} />
            Import Playlist
          </button>
        )}
        <p className="text-[10px] text-slate-600 text-center mt-2">
          Supports MP3 / FLAC / OGG / NCM / WAV
        </p>
      </div>

      {user && (
        <div className="px-4 py-3 border-t border-border flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
            <User size={14} className="text-primary" />
          </div>
          <span className="text-xs text-slate-300 truncate flex-1">
            {user.nickname || user.username}
          </span>
          <button
            onClick={logout}
            className="p-1.5 rounded-md text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all"
            title="Logout"
          >
            <LogOut size={14} />
          </button>
        </div>
      )}

      <PlaylistImportModal
        visible={showPlaylistImport}
        onClose={() => setShowPlaylistImport(false)}
      />
    </div>
  )
}
