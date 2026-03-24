import React, { useEffect, useMemo } from 'react'
import { Music } from 'lucide-react'

import { ErrorBoundary } from './components/ErrorBoundary'
import { LoginPage } from './components/LoginPage'
import { Sidebar } from './components/Sidebar'
import { SongDetail } from './components/SongDetail'
import { SongList } from './components/SongList'
import { useAuthStore } from './store/useAuthStore'
import { useMusicStore } from './store/useMusicStore'

const App: React.FC = () => {
  const user = useAuthStore((state) => state.user)
  const loadUser = useAuthStore((state) => state.loadUser)
  const selectedSongId = useMusicStore((state) => state.selectedSongId)
  const songs = useMusicStore((state) => state.songs)
  const platformSongs = useMusicStore((state) => state.platformSongs)
  const currentPlaylistSongs = useMusicStore((state) => state.currentPlaylistSongs)
  const loadPlatformLibrary = useMusicStore((state) => state.loadPlatformLibrary)
  const platformLibraryLoaded = useMusicStore((state) => state.platformLibraryLoaded)
  const loadPlaylists = useMusicStore((state) => state.loadPlaylists)

  useEffect(() => {
    void loadUser()
  }, [loadUser])

  useEffect(() => {
    if (!platformLibraryLoaded) {
      void loadPlatformLibrary()
    }
  }, [loadPlatformLibrary, platformLibraryLoaded])

  useEffect(() => {
    if (user) {
      void loadPlaylists(user.id)
    }
  }, [loadPlaylists, user])

  const selectedSong = useMemo(
    () =>
      songs.find((song) => song.id === selectedSongId) ||
      platformSongs.find((song) => song.id === selectedSongId) ||
      currentPlaylistSongs.find((song) => song.id === selectedSongId),
    [currentPlaylistSongs, platformSongs, selectedSongId, songs]
  )

  if (!user) return <LoginPage />

  return (
    <div className="flex h-screen bg-background text-white overflow-hidden">
      <Sidebar />
      <div className="flex-1 border-r border-border min-w-[320px] max-w-[500px]">
        <SongList />
      </div>
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
            <p className="text-slate-500 text-sm">Select a song to inspect details.</p>
            <p className="text-slate-600 text-xs mt-1.5">Import local audio or open a playlist from the left side.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
