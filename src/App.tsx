import React, { useEffect, useMemo } from 'react'
import { Music } from 'lucide-react'
import { Sidebar } from './components/Sidebar'
import { SongList } from './components/SongList'
import { SongDetail } from './components/SongDetail'
import { ErrorBoundary } from './components/ErrorBoundary'
import { useMusicStore } from './store/useMusicStore'

const App: React.FC = () => {
  const selectedSongId = useMusicStore((s) => s.selectedSongId)
  const songs = useMusicStore((s) => s.songs)
  const platformSongs = useMusicStore((s) => s.platformSongs)
  const loadPlatformLibrary = useMusicStore((s) => s.loadPlatformLibrary)
  const platformLibraryLoaded = useMusicStore((s) => s.platformLibraryLoaded)

  // Load persistent library on startup
  useEffect(() => {
    if (!platformLibraryLoaded) {
      loadPlatformLibrary()
    }
  }, [platformLibraryLoaded, loadPlatformLibrary])

  const selectedSong = useMemo(
    () =>
      songs.find((s) => s.id === selectedSongId) ||
      platformSongs.find((s) => s.id === selectedSongId),
    [songs, platformSongs, selectedSongId]
  )

  return (
    <div className="flex h-screen bg-background text-white overflow-hidden">
      {/* Left: Sidebar Navigation */}
      <Sidebar />

      {/* Center: Song List / Search Results */}
      <div className="flex-1 border-r border-border min-w-[320px] max-w-[500px]">
        <SongList />
      </div>

      {/* Right: Song Detail + Waveform + Player + Analysis */}
      <div className="flex-1 min-w-[400px] bg-background">
        {selectedSong ? (
          <ErrorBoundary key={selectedSong.id}>
            <SongDetail song={selectedSong} />
          </ErrorBoundary>
        ) : (
          <div className="h-full flex flex-col items-center justify-center">
            <div className="w-20 h-20 rounded-2xl bg-surface flex items-center justify-center mb-5">
              <Music size={36} className="text-slate-600" />
            </div>
            <p className="text-slate-500 text-sm">选择一首歌曲查看详情</p>
            <p className="text-slate-600 text-xs mt-1.5">
              点击左侧列表中的歌曲，或先导入音频文件
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
