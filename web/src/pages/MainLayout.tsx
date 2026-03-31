import { useEffect, useState, useCallback, useRef } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import Sidebar from '../components/Sidebar'
import type { NavView } from '../components/Sidebar'
import SongList from '../components/SongList'
import SongDetail from '../components/SongDetail'
import AudioPlayer from '../components/AudioPlayer'
import UploadModal from '../components/UploadModal'
import PlaylistImportModal from '../components/PlaylistImportModal'
import RecommendPanel from '../components/RecommendPanel'
import SessionPanel from '../components/SessionPanel'
import ProfilePanel from '../components/ProfilePanel'

export default function MainLayout() {
  const { user } = useAuthStore()
  const { loadSongs, loadPlaylists, searchSongs, setSearchQuery, searchQuery } = useMusicStore()
  const [showUpload, setShowUpload] = useState(false)
  const [showPlaylistImport, setShowPlaylistImport] = useState(false)
  const [currentView, setCurrentView] = useState<NavView>('library')
  const searchTimer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    loadSongs()
    if (user) loadPlaylists(user.id)
  }, [loadSongs, loadPlaylists, user])

  const handleSearch = useCallback((q: string) => {
    setSearchQuery(q)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      if (q.trim()) {
        searchSongs(q.trim())
      } else {
        loadSongs()
      }
    }, 400)
  }, [searchSongs, loadSongs, setSearchQuery])

  const renderMainContent = () => {
    switch (currentView) {
      case 'recommend':
        return <RecommendPanel />
      case 'session':
        return <SessionPanel />
      case 'profile':
        return <ProfilePanel />
      case 'library':
      default:
        return (
          <>
            <SongList />
            <SongDetail />
          </>
        )
    }
  }

  return (
    <div className="h-screen flex flex-col bg-surface overflow-hidden">
      {/* Top bar */}
      <header className="h-14 bg-surface-light border-b border-gray-700 flex items-center px-4 justify-between shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-xl">🎵</span>
          <span className="font-bold text-lg text-white">HarBeat</span>
        </div>
        <div className="flex-1 max-w-lg mx-8">
          <input
            type="text"
            placeholder="搜索歌曲、艺术家..."
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full bg-surface rounded-lg px-4 py-1.5 text-sm text-white border border-gray-600 focus:border-primary focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPlaylistImport(true)}
            className="bg-surface hover:bg-surface-lighter text-gray-300 text-sm font-medium px-3 py-1.5 rounded-lg border border-gray-600 transition flex items-center gap-1"
          >
            📋 导入歌单
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="bg-primary hover:bg-primary-dark text-white text-sm font-medium px-4 py-1.5 rounded-lg transition flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4"/>
            </svg>
            上传
          </button>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar currentView={currentView} onViewChange={setCurrentView} />
        {renderMainContent()}
      </div>

      {/* Bottom player */}
      <AudioPlayer />

      {/* Modals */}
      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
      {showPlaylistImport && <PlaylistImportModal onClose={() => setShowPlaylistImport(false)} />}
    </div>
  )
}
