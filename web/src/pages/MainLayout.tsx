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
import PlatformSearch from '../components/PlatformSearch'
import RecommendPanel from '../components/RecommendPanel'
import SessionPanel from '../components/SessionPanel'
import ProfilePanel from '../components/ProfilePanel'
import { ErrorBoundary } from '../components/ErrorBoundary'

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
      case 'platform':
        return <PlatformSearch />
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
    <div className="h-screen flex flex-col bg-surface overflow-hidden street-theme p-2 gap-2">
      <header className="street-sticker min-h-16 bg-surface-light px-4 py-2 flex items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🎚️</span>
          <div>
            <div className="text-2xl street-title leading-none">HarBeat</div>
            <div className="text-xs street-subtitle">street dance / dj platform</div>
          </div>
        </div>

        <div className="flex-1 max-w-xl">
          <input
            type="text"
            placeholder="Search songs / artists"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full px-4 py-2 text-sm"
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowPlaylistImport(true)}
            className="bg-surface-lighter text-sm font-semibold px-3 py-2 rounded-md"
          >
            Import Playlist
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="bg-primary text-sm font-bold px-4 py-2 rounded-md flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Upload
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden gap-2 min-h-0">
        <Sidebar currentView={currentView} onViewChange={setCurrentView} />
        <ErrorBoundary>
          {renderMainContent()}
        </ErrorBoundary>
      </div>

      <AudioPlayer />

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
      {showPlaylistImport && <PlaylistImportModal onClose={() => setShowPlaylistImport(false)} />}
    </div>
  )
}
