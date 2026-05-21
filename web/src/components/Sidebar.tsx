import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import * as api from '../api/client'

export type NavView = 'library' | 'platform' | 'recommend' | 'session' | 'profile'

interface Props {
  currentView: NavView
  onViewChange: (view: NavView) => void
  onMobileAction?: () => void
}

const NAV_ITEMS: { id: NavView; icon: string; label: string }[] = [
  { id: 'library', icon: '🎵', label: 'Library' },
  { id: 'platform', icon: '🌐', label: 'Search' },
  { id: 'recommend', icon: '🔥', label: 'Discover' },
  { id: 'session', icon: '🎧', label: 'DJ Session' },
  { id: 'profile', icon: '👤', label: 'Profile' },
]

export default function Sidebar({ currentView, onViewChange, onMobileAction }: Props) {
  const { user, doLogout } = useAuthStore()
  const { playlists, playlistsLoading, selectPlaylist, selectedPlaylist, clearSelectedPlaylist, deletePlaylist, loadSongs, loadPlaylists } = useMusicStore()
  const [creatingPlaylist, setCreatingPlaylist] = useState(false)
  const [newPlaylistName, setNewPlaylistName] = useState('')

  const handleCreatePlaylist = async () => {
    if (!newPlaylistName.trim()) return
    try {
      await api.createPlaylist(newPlaylistName.trim())
      if (user) loadPlaylists(user.id)
    } catch {
      // ignore
    }
    setNewPlaylistName('')
    setCreatingPlaylist(false)
  }

  return (
    <div className="w-full h-full bg-surface-light flex flex-col overflow-hidden street-sticker md:rounded-[10px]">
      <nav className="p-3 space-y-2">
        {NAV_ITEMS.map(item => (
          <button
            key={item.id}
            onClick={() => {
              onViewChange(item.id)
              if (item.id === 'library') { clearSelectedPlaylist(); loadSongs() }
            }}
            className={`w-full text-left px-3 py-2 text-sm font-semibold rounded-md ${
              currentView === item.id && !selectedPlaylist ? 'bg-primary text-black' : 'bg-surface-lighter'
            }`}
          >
            {item.icon} {item.label}
          </button>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-3 pb-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs street-subtitle">PLAYLISTS</h3>
          <button
            className="text-base bg-surface-lighter rounded-md w-7 h-7"
            onClick={() => setCreatingPlaylist(true)}
            title="New playlist"
          >
            +
          </button>
        </div>
        {creatingPlaylist && (
          <div className="flex gap-1 mb-2">
            <input
              autoFocus
              className="flex-1 text-xs px-2 py-1"
              placeholder="Playlist name"
              value={newPlaylistName}
              onChange={(e) => setNewPlaylistName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreatePlaylist()
                if (e.key === 'Escape') setCreatingPlaylist(false)
              }}
            />
            <button className="text-xs px-2 bg-primary" onClick={handleCreatePlaylist}>OK</button>
            <button className="text-xs px-2 bg-surface-lighter" onClick={() => setCreatingPlaylist(false)}>X</button>
          </div>
        )}
        {playlistsLoading ? (
          <div className="text-xs px-3">Loading...</div>
        ) : playlists.length === 0 ? (
          <div className="text-xs px-3">No playlists</div>
        ) : (
          <div className="space-y-1">
            {playlists.map((pl) => (
              <div
                key={pl.id}
                className={`group flex items-center justify-between px-3 py-2 cursor-pointer text-sm rounded-md border-2 border-black ${
                  selectedPlaylist?.id === pl.id ? 'bg-primary' : 'bg-surface-lighter'
                }`}
                onClick={() => { onViewChange('library'); selectPlaylist(pl.id); onMobileAction?.() }}
              >
                <span className="truncate flex-1">{pl.playlist_name}</span>
                <span className="text-xs ml-1">{pl.song_count}</span>
                <button
                  className="opacity-0 group-hover:opacity-100 ml-1 text-xs bg-white"
                  onClick={(e) => { e.stopPropagation(); deletePlaylist(pl.id) }}
                  title="Delete playlist"
                >
                  X
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-3 border-t-2 border-black">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-md bg-primary flex items-center justify-center text-sm border-2 border-black">
            {user?.username?.[0]?.toUpperCase() || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm truncate font-semibold">{user?.username}</div>
            <div className="text-xs truncate">{user?.dance_style}</div>
          </div>
          <button
            onClick={doLogout}
            className="text-xs px-2 py-1 bg-surface-lighter"
            title="Logout"
          >
            Logout
          </button>
        </div>
      </div>
    </div>
  )
}
