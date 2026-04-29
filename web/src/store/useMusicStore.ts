import { create } from 'zustand'
import type { LibrarySong, Playlist, PlaylistDetail } from '../types'
import * as api from '../api/client'

interface MusicState {
  // Library
  songs: LibrarySong[]
  songsLoading: boolean
  selectedSong: LibrarySong | null
  searchQuery: string

  // Playlists
  playlists: Playlist[]
  playlistsLoading: boolean
  selectedPlaylist: PlaylistDetail | null

  // Player
  playingSong: LibrarySong | null
  isPlaying: boolean
  volume: number

  // Upload
  uploading: boolean

  // Actions
  loadSongs: () => Promise<void>
  searchSongs: (q: string) => Promise<void>
  setSearchQuery: (q: string) => void
  selectSong: (song: LibrarySong | null) => void
  uploadFile: (file: File, title?: string, artist?: string) => Promise<void>
  analyzeSong: (songId: string) => Promise<void>
  classifyDanceStyles: (songId: string, params?: Record<string, unknown>) => Promise<void>
  deleteSong: (songId: string) => Promise<void>
  playSong: (song: LibrarySong) => void
  togglePlay: () => void
  setVolume: (v: number) => void
  loadPlaylists: (userId: number) => Promise<void>
  selectPlaylist: (id: number) => Promise<void>
  clearSelectedPlaylist: () => void
  deletePlaylist: (id: number) => Promise<void>
  importPlaylistFromSongs: (userId: number, name: string, songs: { title: string; artist: string; duration?: number; bpm?: number; tags?: string[] }[]) => Promise<void>
  updateLibrarySongLocal: (songId: string, updates: Partial<LibrarySong>) => void
}

export const useMusicStore = create<MusicState>((set, get) => ({
  songs: [],
  songsLoading: false,
  selectedSong: null,
  searchQuery: '',
  playlists: [],
  playlistsLoading: false,
  selectedPlaylist: null,
  playingSong: null,
  isPlaying: false,
  volume: 0.8,
  uploading: false,

  loadSongs: async () => {
    set({ songsLoading: true })
    try {
      const res = await api.getLibrarySongs()
      set({ songs: res.songs, songsLoading: false })
    } catch {
      set({ songsLoading: false })
    }
  },

  searchSongs: async (q) => {
    set({ songsLoading: true })
    try {
      const res = await api.searchLibrarySongs(q)
      set({ songs: res.songs, songsLoading: false })
    } catch {
      set({ songsLoading: false })
    }
  },

  setSearchQuery: (q) => set({ searchQuery: q }),

  selectSong: (song) => set({ selectedSong: song }),

  uploadFile: async (file, title, artist) => {
    set({ uploading: true })
    try {
      await api.uploadSong(file, title, artist)
      set({ uploading: false })
      get().loadSongs()
    } catch {
      set({ uploading: false })
    }
  },

  analyzeSong: async (songId) => {
    try {
      const updated = await api.analyzeSong(songId)
      set((state) => ({
        songs: state.songs.map((s) => (s.id === songId ? updated : s)),
        selectedSong: state.selectedSong?.id === songId ? updated : state.selectedSong,
      }))
    } catch { /* ignore */ }
  },

  classifyDanceStyles: async (songId, params = {}) => {
    try {
      const updated = await api.classifyDanceStyles(songId, { params })
      set((state) => ({
        songs: state.songs.map((s) => (s.id === songId ? updated : s)),
        selectedSong: state.selectedSong?.id === songId ? updated : state.selectedSong,
      }))
    } catch { /* ignore */ }
  },

  deleteSong: async (songId) => {
    try {
      await api.deleteSong(songId)
      set((state) => ({
        songs: state.songs.filter((s) => s.id !== songId),
        selectedSong: state.selectedSong?.id === songId ? null : state.selectedSong,
        playingSong: state.playingSong?.id === songId ? null : state.playingSong,
      }))
    } catch { /* ignore */ }
  },

  playSong: (song) => set({ playingSong: song, isPlaying: true }),
  togglePlay: () => set((s) => ({ isPlaying: !s.isPlaying })),
  setVolume: (v) => set({ volume: v }),

  loadPlaylists: async (userId) => {
    set({ playlistsLoading: true })
    try {
      const res = await api.getPlaylists(userId)
      set({ playlists: res.playlists, playlistsLoading: false })
    } catch {
      set({ playlistsLoading: false })
    }
  },

  selectPlaylist: async (id) => {
    try {
      const detail = await api.getPlaylistDetail(id)
      set({ selectedPlaylist: detail })
    } catch { /* ignore */ }
  },

  clearSelectedPlaylist: () => set({ selectedPlaylist: null }),

  deletePlaylist: async (id) => {
    try {
      await api.deletePlaylist(id)
      set((s) => ({
        playlists: s.playlists.filter((p) => p.id !== id),
        selectedPlaylist: s.selectedPlaylist?.id === id ? null : s.selectedPlaylist,
      }))
    } catch { /* ignore */ }
  },

  importPlaylistFromSongs: async (userId, name, songs) => {
    const res = await api.importPlaylist({
      user_id: userId,
      playlist_name: name,
      source_type: 'manual',
      songs,
    })
    // Refresh playlists
    try {
      const plRes = await api.getPlaylists(userId)
      set({ playlists: plRes.playlists })
    } catch { /* ignore */ }
  },

  updateLibrarySongLocal: (songId, updates) => {
    set((state) => ({
      songs: state.songs.map((s) => (s.id === songId ? { ...s, ...updates } : s)),
      selectedSong: state.selectedSong?.id === songId ? { ...state.selectedSong, ...updates } : state.selectedSong,
    }))
  },
}))
