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
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
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

  const handleViewChange = useCallback((view: NavView) => {
    setCurrentView(view)
    setSidebarOpen(false)
  }, [])

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
    <div className="h-screen flex flex-col bg-surface overflow-hidden street-theme p-1 sm:p-2 gap-1 sm:gap-2">
      {/* Header */}
      <header className="street-sticker min-h-12 sm:min-h-16 bg-surface-light px-2 sm:px-4 py-2 flex items-center justify-between gap-2 sm:gap-3 shrink-0">
        {/* Left: hamburger + logo */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          <button
            className="md:hidden w-8 h-8 flex items-center justify-center text-lg"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            ☰
          </button>
          <span className="text-xl sm:text-2xl">🎚️</span>
          <div className="hidden sm:block">
            <div className="text-2xl street-title leading-none">HarBeat</div>
            <div className="text-xs street-subtitle">street dance / dj platform</div>
          </div>
          <div className="sm:hidden">
            <div className="text-lg street-title leading-none">HarBeat</div>
          </div>
        </div>

        {/* Center: search (desktop) */}
        <div className="hidden sm:block flex-1 max-w-xl">
          <input
            type="text"
            placeholder="Search songs / artists"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full px-4 py-2 text-sm"
          />
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          {/* Mobile search toggle */}
          <button
            className="sm:hidden w-8 h-8 flex items-center justify-center text-sm"
            onClick={() => setMobileSearchOpen(!mobileSearchOpen)}
          >
            🔍
          </button>
          <button
            onClick={() => setShowPlaylistImport(true)}
            className="hidden sm:block bg-surface-lighter text-sm font-semibold px-3 py-2 rounded-md"
          >
            Import Playlist
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="bg-primary text-xs sm:text-sm font-bold px-2 sm:px-4 py-1.5 sm:py-2 rounded-md flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span className="hidden sm:inline">Upload</span>
          </button>
        </div>
      </header>

      {/* Mobile search bar */}
      {mobileSearchOpen && (
        <div className="sm:hidden px-1 shrink-0">
          <input
            type="text"
            placeholder="Search songs / artists"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full px-3 py-2 text-sm"
            autoFocus
          />
        </div>
      )}

      {/* Main content area */}
      <div className="flex flex-1 overflow-hidden gap-1 sm:gap-2 min-h-0">
        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/40 z-40 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar: drawer on mobile, static on desktop */}
        <div className={`
          fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-in-out
          md:relative md:inset-auto md:z-auto md:w-60 md:transform-none md:transition-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        `}>
          <Sidebar currentView={currentView} onViewChange={handleViewChange} onMobileAction={() => setSidebarOpen(false)} />
        </div>

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
