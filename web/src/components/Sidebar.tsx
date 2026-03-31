import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import * as api from '../api/client'

export type NavView = 'library' | 'platform' | 'recommend' | 'session' | 'profile'

interface Props {
  currentView: NavView
  onViewChange: (view: NavView) => void
}

const NAV_ITEMS: { id: NavView; icon: string; label: string }[] = [
  { id: 'library', icon: '🎵', label: '我的音乐库' },
  { id: 'platform', icon: '🌐', label: '在线搜索' },
  { id: 'recommend', icon: '🎯', label: '智能推荐' },
  { id: 'session', icon: '🎤', label: '练舞会话' },
  { id: 'profile', icon: '👤', label: '音乐画像' },
]

export default function Sidebar({ currentView, onViewChange }: Props) {
  const { user, doLogout } = useAuthStore()
  const { playlists, playlistsLoading, selectPlaylist, selectedPlaylist, clearSelectedPlaylist, deletePlaylist, loadSongs, loadPlaylists } = useMusicStore()
  const [creatingPlaylist, setCreatingPlaylist] = useState(false)
  const [newPlaylistName, setNewPlaylistName] = useState('')

  const handleCreatePlaylist = async () => {
    if (!newPlaylistName.trim()) return
    try {
      await api.createPlaylist(newPlaylistName.trim())
      if (user) loadPlaylists(user.id)
    } catch { /* ignore */ }
    setNewPlaylistName('')
    setCreatingPlaylist(false)
  }

  return (
    <div className="w-56 bg-surface-light border-r border-gray-700 flex flex-col shrink-0 overflow-hidden">
      {/* Navigation */}
      <nav className="p-3 space-y-1">
        {NAV_ITEMS.map(item => (
          <button
            key={item.id}
            onClick={() => {
              onViewChange(item.id)
              if (item.id === 'library') { clearSelectedPlaylist(); loadSongs() }
            }}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
              currentView === item.id && !selectedPlaylist ? 'bg-primary/20 text-primary' : 'text-gray-300 hover:bg-surface-lighter'
            }`}
          >
            {item.icon} {item.label}
          </button>
        ))}
      </nav>

      {/* Playlists */}
      <div className="flex-1 overflow-y-auto px-3 pb-3">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">歌单</h3>
          <button
            className="text-gray-500 hover:text-primary text-lg leading-none transition"
            onClick={() => setCreatingPlaylist(true)}
            title="新建歌单"
          >
            +
          </button>
        </div>
        {creatingPlaylist && (
          <div className="flex gap-1 mb-2">
            <input
              autoFocus
              className="flex-1 bg-surface-lighter text-white text-xs px-2 py-1 rounded border border-gray-600 focus:border-primary outline-none"
              placeholder="歌单名称"
              value={newPlaylistName}
              onChange={(e) => setNewPlaylistName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreatePlaylist()
                if (e.key === 'Escape') setCreatingPlaylist(false)
              }}
            />
            <button className="text-xs text-primary hover:text-white transition" onClick={handleCreatePlaylist}>✓</button>
            <button className="text-xs text-gray-500 hover:text-white transition" onClick={() => setCreatingPlaylist(false)}>✕</button>
          </div>
        )}
        {playlistsLoading ? (
          <div className="text-xs text-gray-500 px-3">加载中...</div>
        ) : playlists.length === 0 ? (
          <div className="text-xs text-gray-500 px-3">暂无歌单</div>
        ) : (
          <div className="space-y-0.5">
            {playlists.map((pl) => (
              <div
                key={pl.id}
                className={`group flex items-center justify-between px-3 py-1.5 rounded-lg cursor-pointer text-sm transition ${
                  selectedPlaylist?.id === pl.id ? 'bg-primary/20 text-primary' : 'text-gray-300 hover:bg-surface-lighter'
                }`}
                onClick={() => { onViewChange('library'); selectPlaylist(pl.id) }}
              >
                <span className="truncate flex-1">{pl.playlist_name}</span>
                <span className="text-xs text-gray-500 ml-1">{pl.song_count}</span>
                <button
                  className="opacity-0 group-hover:opacity-100 ml-1 text-gray-500 hover:text-red-400 transition"
                  onClick={(e) => { e.stopPropagation(); deletePlaylist(pl.id) }}
                  title="删除歌单"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* User info */}
      <div className="p-3 border-t border-gray-700">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-primary/30 flex items-center justify-center text-sm">
            {user?.username?.[0]?.toUpperCase() || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm text-white truncate">{user?.username}</div>
            <div className="text-xs text-gray-500">{user?.dance_style}</div>
          </div>
          <button
            onClick={doLogout}
            className="text-gray-500 hover:text-red-400 text-xs transition"
            title="退出登录"
          >
            退出
          </button>
        </div>
      </div>
    </div>
  )
}
