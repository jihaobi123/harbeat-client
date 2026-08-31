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
import DjControlPanel from '../components/DjControlPanel'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { EditorialIcon } from '../components/editorial/EditorialIcon'
import type { EditorialIconName } from '../components/editorial/EditorialIcon'

const MOBILE_NAV: Array<{
  id: NavView | 'annotation'
  label: string
  icon: EditorialIconName
}> = [
  { id: 'library', label: '音乐', icon: 'library' },
  { id: 'recommend', label: '发现', icon: 'discover' },
  { id: 'dj', label: 'DJ', icon: 'mixer' },
  { id: 'annotation', label: '标注', icon: 'tag' },
  { id: 'profile', label: '我的', icon: 'profile' },
]

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
      case 'dj':
        return <DjControlPanel />
      case 'profile':
        return <ProfilePanel />
      case 'library':
      default:
        return (
          <div className="editorial-library-layout">
            <SongList />
            <SongDetail />
          </div>
        )
    }
  }

  return (
    <div className="editorial-app street-theme">
      {/* Header */}
      <header className="editorial-topbar street-sticker">
        {/* Left: hamburger + logo */}
        <div className="editorial-brand shrink-0">
          <button
            className="md:hidden w-10 h-10 flex items-center justify-center"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? '关闭菜单' : '打开菜单'}
            aria-expanded={sidebarOpen}
          >
            <EditorialIcon name="menu" decorative />
          </button>
          <div className="editorial-brand__mark" aria-hidden="true">HB</div>
          <div>
            <div className="editorial-brand__title">HarBeat</div>
            <div className="editorial-brand__subtitle">street dance / dj platform</div>
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
        <div className="editorial-topbar__actions shrink-0">
          {/* Mobile search toggle */}
          <button
            className="sm:hidden w-10 h-10 flex items-center justify-center"
            onClick={() => setMobileSearchOpen(!mobileSearchOpen)}
            aria-label={mobileSearchOpen ? '关闭搜索' : '打开搜索'}
            aria-expanded={mobileSearchOpen}
          >
            <EditorialIcon name="search" decorative />
          </button>
          <button
            onClick={() => setShowPlaylistImport(true)}
            className="hidden sm:block bg-surface-lighter text-sm font-semibold px-3 py-2"
          >
            Import Playlist
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="is-primary bg-primary text-xs sm:text-sm font-bold px-3 sm:px-4 py-1.5 sm:py-2 flex items-center gap-2"
            aria-label="上传音乐"
          >
            <EditorialIcon name="upload" decorative />
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
      <div className="editorial-workspace">
        {/* Mobile sidebar overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/40 z-40 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar: drawer on mobile, static on desktop */}
        <div className={`editorial-sidebar-shell
          fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 ease-in-out
          md:relative md:inset-auto md:z-auto md:w-60 md:transform-none md:transition-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
        `}>
          <Sidebar currentView={currentView} onViewChange={handleViewChange} onMobileAction={() => setSidebarOpen(false)} />
        </div>

        <ErrorBoundary>
          <main className="editorial-main-content">
            {renderMainContent()}
          </main>
        </ErrorBoundary>
      </div>

      <AudioPlayer />

      <nav className="editorial-mobile-nav" aria-label="手机主导航">
        {MOBILE_NAV.map(item => {
          const active = item.id !== 'annotation' && currentView === item.id
          return (
            <button
              key={item.id}
              type="button"
              className={active ? 'is-active' : ''}
              aria-current={active ? 'page' : undefined}
              onClick={() => {
                if (item.id === 'annotation') {
                  window.location.assign('/annotate')
                } else {
                  handleViewChange(item.id)
                }
              }}
            >
              <EditorialIcon name={item.icon} decorative />
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}
      {showPlaylistImport && <PlaylistImportModal onClose={() => setShowPlaylistImport(false)} />}
    </div>
  )
}
