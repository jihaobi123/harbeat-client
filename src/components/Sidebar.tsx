import React, { useState } from 'react'
import { Library, Globe, Clock, Upload, ListMusic, LogOut, User, ChevronRight, Trash2, Music } from 'lucide-react'
import { useMusicStore } from '../store/useMusicStore'
import { useAuthStore } from '../store/useAuthStore'
import { getAudioDuration } from '../utils/format'
import { PlaylistImportModal } from './PlaylistImportModal'

const navItems = [
  { id: 'my-library' as const, label: '我的曲库', icon: Library },
  { id: 'platform' as const, label: '平台曲库', icon: Globe },
  { id: 'recent' as const, label: '最近导入', icon: Clock },
]

export const Sidebar: React.FC = () => {
  const currentView = useMusicStore((s) => s.currentView)
  const setView = useMusicStore((s) => s.setView)
  const songsCount = useMusicStore((s) => s.songs.length)
  const playlists = useMusicStore((s) => s.playlists)
  const currentPlaylistId = useMusicStore((s) => s.currentPlaylistId)
  const viewPlaylist = useMusicStore((s) => s.viewPlaylist)
  const deletePlaylistAction = useMusicStore((s) => s.deletePlaylist)
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const [showPlaylistImport, setShowPlaylistImport] = useState(false)

  const handleImport = async () => {
    const files = await window.electronAPI.openAudioFiles()
    if (!files || files.length === 0) return

    // Filter out files that failed to decrypt
    const validFiles = files.filter((f) => !f.error)
    if (validFiles.length === 0) return

    const newSongs = useMusicStore.getState().addSongs(validFiles)

    // Get duration for each imported song via local HTTP server
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
      {/* Logo */}
      <div className="px-5 py-4 border-b border-border">
        <h1 className="text-lg font-bold text-white flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center">
            <span className="text-primary text-base">♪</span>
          </div>
          AudioLab
        </h1>
        <p className="text-[11px] text-slate-500 mt-1 ml-[42px]">音频曲库管理</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 overflow-y-auto">
        <p className="px-5 text-[10px] font-semibold text-slate-600 uppercase tracking-wider mb-2">
          导航
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

        {/* 歌单列表 */}
        {playlists.length > 0 && (
          <>
            <p className="px-5 text-[10px] font-semibold text-slate-600 uppercase tracking-wider mb-2 mt-4">
              我的歌单
            </p>
            {playlists.map((pl) => {
              const isActive = currentView === 'playlist' && currentPlaylistId === pl.id
              return (
                <div
                  key={pl.id}
                  className={`w-full flex items-center gap-2.5 px-5 py-2 text-sm transition-all group cursor-pointer ${
                    isActive
                      ? 'bg-primary/10 text-primary border-r-2 border-primary font-medium'
                      : 'text-slate-400 hover:bg-hover hover:text-slate-200 border-r-2 border-transparent'
                  }`}
                  onClick={() => viewPlaylist(pl.id)}
                >
                  <Music size={16} className="flex-shrink-0" />
                  <span className="truncate flex-1">{pl.name}</span>
                  <span className="text-[10px] text-slate-600 flex-shrink-0">
                    {pl.songCount}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      deletePlaylistAction(pl.id)
                    }}
                    className="p-0.5 rounded text-slate-600 hover:text-red-400 hover:bg-red-400/10 opacity-0 group-hover:opacity-100 transition-all flex-shrink-0"
                    title="删除歌单"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              )
            })}
          </>
        )}
      </nav>

      {/* Import Button */}
      <div className="p-4 border-t border-border space-y-2">
        <button
          onClick={handleImport}
          className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-white py-2.5 px-4 rounded-lg text-sm font-medium transition-all active:scale-[0.97]"
        >
          <Upload size={16} />
          导入音频
        </button>
        {user && (
          <button
            onClick={() => setShowPlaylistImport(true)}
            className="w-full flex items-center justify-center gap-2 bg-surface-dark hover:bg-hover border border-border text-slate-300 py-2.5 px-4 rounded-lg text-sm font-medium transition-all active:scale-[0.97]"
          >
            <ListMusic size={16} />
            导入歌单
          </button>
        )}
        <p className="text-[10px] text-slate-600 text-center mt-2">
          支持 MP3 / FLAC / OGG / NCM / WAV 等
        </p>
      </div>

      {/* User Info */}
      {user && (
        <div className="px-4 py-3 border-t border-border flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
            <User size={14} className="text-primary" />
          </div>
          <span className="text-xs text-slate-300 truncate flex-1">{user.nickname || user.username}</span>
          <button
            onClick={logout}
            className="p-1.5 rounded-md text-slate-500 hover:text-red-400 hover:bg-red-400/10 transition-all"
            title="退出登录"
          >
            <LogOut size={14} />
          </button>
        </div>
      )}

      {/* Playlist Import Modal */}
      <PlaylistImportModal
        visible={showPlaylistImport}
        onClose={() => setShowPlaylistImport(false)}
      />
    </div>
  )
}
