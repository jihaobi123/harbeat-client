import { create } from 'zustand'

import type { AudioFileInfo, DanceStyle, ImportPlaylistResult, Playlist, Song } from '../types'
import {
  deletePlaylist as apiDeletePlaylist,
  getPlaylistDetail as apiGetPlaylistDetail,
  getPlaylists as apiGetPlaylists,
  importPlaylist as apiImportPlaylist,
  type ImportPlaylistRequest,
} from '../services/api'

type ViewType = 'my-library' | 'platform' | 'recent' | 'playlist'
type DisplayMode = 'list' | 'grid'

interface MusicStore {
  songs: Song[]
  platformSongs: Song[]
  selectedSongId: string | null
  currentView: ViewType
  searchQuery: string
  platformSearchLoading: boolean
  platformSearchError: string | null
  platformLibraryLoaded: boolean
  displayMode: DisplayMode
  tagFilter: DanceStyle | null
  playlists: Playlist[]
  currentPlaylistId: string | null
  currentPlaylistSongs: Song[]
  playlistImporting: boolean
  playlistImportError: string | null
  lastImportResult: ImportPlaylistResult | null
  addSongs: (files: AudioFileInfo[]) => Song[]
  removeSong: (id: string) => void
  selectSong: (id: string | null) => void
  setView: (view: ViewType) => void
  setSearchQuery: (query: string) => void
  updateSong: (id: string, updates: Partial<Song>) => void
  addPlatformSongToLibrary: (songId: string) => void
  searchPlatform: (query: string) => Promise<void>
  loadPlatformLibrary: () => Promise<void>
  downloadSong: (songId: string) => Promise<void>
  setDisplayMode: (mode: DisplayMode) => void
  setTagFilter: (tag: DanceStyle | null) => void
  importAndDownloadPlaylist: (
    userId: string,
    playlistName: string,
    songList: ImportPlaylistRequest['songList']
  ) => Promise<{ playlistId: string; success: string[]; failed: string[] } | null>
  importPlaylist: (
    userId: string,
    playlistName: string,
    songList: ImportPlaylistRequest['songList']
  ) => Promise<ImportPlaylistResult | null>
  loadPlaylists: (userId?: string) => Promise<void>
  viewPlaylist: (playlistId: string) => Promise<void>
  deletePlaylist: (playlistId: string) => Promise<void>
  clearImportResult: () => void
  fetchPlaylistSong: (songId: string) => Promise<void>
  fetchAllPlaylistSongs: (playlistId: string) => Promise<void>
}

let songIdCounter = 0
const generateId = () => `song-${Date.now()}-${++songIdCounter}`
const makeIdentity = (title: string, artist: string) => `${title}||${artist}`.toLowerCase()

const mapLibrarySong = (song: any): Song => ({
  id: String(song.id),
  title: song.title,
  artist: song.artist,
  duration: song.duration || 0,
  format: song.format || 'mp3',
  fileSize: song.fileSize || 0,
  sourceType: song.sourceType || 'internal_catalog',
  sourcePath: song.sourcePath || '',
  platformId: song.platformId,
  platformUrl: song.platformUrl,
  importStatus: 'ready',
  downloadStatus: song.sourcePath ? 'downloaded' : 'none',
  analysisStatus: song.bpm ? 'completed' : 'none',
  bpm: song.bpm || null,
  beatPoints: song.beatPoints || [],
  cuePoints: song.cuePoints || [],
  tags: (song.tags || []) as DanceStyle[],
  playlistId: song.playlistId ? String(song.playlistId) : undefined,
  createdAt: song.createdAt || Date.now(),
})

const syncSongToLibrary = async (song: Song) => {
  try {
    await window.electronAPI.addToPlatformLibrary({
      id: song.id,
      title: song.title,
      artist: song.artist,
      duration: song.duration,
      format: song.format,
      fileSize: song.fileSize,
      sourceType: song.sourceType,
      sourcePath: song.sourcePath,
      platformId: song.platformId,
      platformUrl: song.platformUrl,
      bpm: song.bpm,
      beatPoints: song.beatPoints,
      cuePoints: song.cuePoints,
      tags: song.tags,
      createdAt: song.createdAt,
    })
  } catch {}
}

export const useMusicStore = create<MusicStore>((set, get) => ({
  songs: [],
  platformSongs: [],
  selectedSongId: null,
  currentView: 'my-library',
  searchQuery: '',
  platformSearchLoading: false,
  platformSearchError: null,
  platformLibraryLoaded: false,
  displayMode: 'list',
  tagFilter: null,
  playlists: [],
  currentPlaylistId: null,
  currentPlaylistSongs: [],
  playlistImporting: false,
  playlistImportError: null,
  lastImportResult: null,

  addSongs: (files) => {
    const newSongs = files.map((file) => ({
      id: generateId(),
      title: file.name,
      artist: file.artist || 'Unknown Artist',
      duration: 0,
      format: file.format,
      fileSize: file.size,
      sourceType: 'local_file' as const,
      sourcePath: file.path,
      importStatus: 'importing' as const,
      analysisStatus: 'none' as const,
      bpm: null,
      beatPoints: [],
      cuePoints: [],
      tags: [],
      createdAt: Date.now(),
    }))
    set((state) => ({ songs: [...state.songs, ...newSongs] }))
    newSongs.forEach((song) => { void syncSongToLibrary(song) })
    return newSongs
  },

  removeSong: (id) => {
    set((state) => ({
      songs: state.songs.filter((song) => song.id !== id),
      selectedSongId: state.selectedSongId === id ? null : state.selectedSongId,
    }))
  },

  selectSong: (id) => set({ selectedSongId: id }),
  setView: (view) => set({ currentView: view, searchQuery: '', currentPlaylistId: null, currentPlaylistSongs: [], tagFilter: null }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setDisplayMode: (mode) => set({ displayMode: mode }),
  setTagFilter: (tag) => set({ tagFilter: tag }),

  updateSong: (id, updates) => {
    set((state) => ({
      songs: state.songs.map((song) => song.id === id ? { ...song, ...updates } : song),
      platformSongs: state.platformSongs.map((song) => song.id === id ? { ...song, ...updates } : song),
      currentPlaylistSongs: state.currentPlaylistSongs.map((song) => song.id === id ? { ...song, ...updates } : song),
    }))
    const song = get().songs.find((item) => item.id === id)
    if (song) void syncSongToLibrary(song)
  },

  addPlatformSongToLibrary: (songId) => {
    const platformSong = get().platformSongs.find((song) => song.id === songId)
    if (!platformSong) return
    set((state) => {
      const exists = state.songs.some((song) => makeIdentity(song.title, song.artist) === makeIdentity(platformSong.title, platformSong.artist))
      if (exists) return state
      return {
        songs: [...state.songs, { ...platformSong, id: generateId(), createdAt: Date.now() }],
      }
    })
  },

  loadPlatformLibrary: async () => {
    try {
      const result = await window.electronAPI.getPlatformLibrary()
      const librarySongs = (result.songs || []).map(mapLibrarySong)
      set((state) => {
        const merged = [...state.songs]
        const seen = new Set(merged.map((song) => song.id))
        for (const song of librarySongs) {
          if (!song.sourcePath || seen.has(song.id)) continue
          merged.push(song)
        }
        return {
          songs: merged,
          platformLibraryLoaded: true,
          platformSongs: state.currentView === 'platform' && !state.searchQuery ? librarySongs : state.platformSongs,
        }
      })
    } catch (error) {
      console.error('[loadPlatformLibrary]', error)
    }
  },

  searchPlatform: async (query) => {
    if (!query.trim()) {
      const result = await window.electronAPI.getPlatformLibrary().catch(() => ({ songs: [] }))
      const librarySongs = (result.songs || []).map(mapLibrarySong)
      const merged = [...get().songs]
      for (const song of librarySongs) {
        if (!merged.some((item) => makeIdentity(item.title, item.artist) === makeIdentity(song.title, song.artist))) {
          merged.push(song)
        }
      }
      set({ platformSongs: merged, platformSearchLoading: false, platformSearchError: null })
      return
    }

    set({ platformSearchLoading: true, platformSearchError: null })
    try {
      const searchResult = await window.electronAPI.searchPlatform(query)
      const platformSongs = (searchResult.songs || []).map((song) => ({
        id: `fangpi-${song.id}`,
        title: song.title,
        artist: song.artist,
        duration: 0,
        format: 'mp3',
        fileSize: 0,
        sourceType: 'internal_catalog' as const,
        sourcePath: '',
        platformId: song.id,
        platformUrl: song.url,
        importStatus: 'ready' as const,
        downloadStatus: 'none' as const,
        analysisStatus: 'none' as const,
        bpm: null,
        beatPoints: [],
        cuePoints: [],
        tags: [],
        createdAt: Date.now(),
      }))
      set({ platformSongs, platformSearchLoading: false, platformSearchError: null })
    } catch (error) {
      set({ platformSearchLoading: false, platformSearchError: String(error) })
    }
  },

  downloadSong: async (songId) => {
    const song = get().platformSongs.find((item) => item.id === songId)
    if (!song || !song.platformId) return
    set((state) => ({
      platformSongs: state.platformSongs.map((item) => item.id === songId ? { ...item, downloadStatus: 'downloading' } : item),
    }))
    try {
      const result = await window.electronAPI.downloadFromPlatform(song.platformId, song.title, song.artist)
      if (result.error || !result.song) throw new Error(result.error || 'download failed')
      const updatedSong: Song = {
        ...song,
        sourcePath: result.song.sourcePath,
        fileSize: result.song.fileSize || 0,
        downloadStatus: 'downloaded',
        importStatus: 'ready',
      }
      set((state) => {
        const songs = state.songs.some((item) => item.platformId === song.platformId)
          ? state.songs.map((item) => item.platformId === song.platformId ? { ...item, ...updatedSong } : item)
          : [...state.songs, updatedSong]
        return {
          songs,
          platformSongs: state.platformSongs.map((item) => item.id === songId ? updatedSong : item),
        }
      })
      void syncSongToLibrary(updatedSong)
    } catch (error) {
      console.error('[downloadSong]', error)
      set((state) => ({
        platformSongs: state.platformSongs.map((item) => item.id === songId ? { ...item, downloadStatus: 'error' } : item),
      }))
    }
  },

  importAndDownloadPlaylist: async (userId, playlistName, songList) => {
    set({ playlistImporting: true, playlistImportError: null, lastImportResult: null })
    try {
      if (songList.length === 0) {
        set({ playlistImporting: false, playlistImportError: 'no songs to import' })
        return null
      }
      const importResponse = await apiImportPlaylist({ userId, playlistName, songList })
      const playlistId = importResponse.data?.playlistId
      if (!playlistId) throw new Error(importResponse.message || 'playlist import failed')
      const detailResponse = await apiGetPlaylistDetail(playlistId)
      const detailSongs = detailResponse.data?.songs || []
      const newSongs = detailSongs.map((song) => ({
        id: song.songId,
        title: song.title,
        artist: song.artist,
        duration: song.duration,
        format: 'mp3',
        fileSize: 0,
        sourceType: 'internal_catalog' as const,
        sourcePath: '',
        importStatus: 'ready' as const,
        downloadStatus: 'none' as const,
        analysisStatus: song.bpm ? 'completed' as const : 'none' as const,
        bpm: song.bpm,
        beatPoints: [],
        cuePoints: [],
        tags: song.tags as DanceStyle[],
        playlistId,
        createdAt: Date.now(),
      }))
      set((state) => ({ songs: [...state.songs, ...newSongs.filter((song) => !state.songs.some((item) => item.id === song.id))] }))
      const success: string[] = []
      const failed: string[] = []
      for (const song of detailSongs) {
        try {
          await get().fetchPlaylistSong(song.songId)
          const current = get().songs.find((item) => item.id === song.songId)
          if (current?.sourcePath) success.push(`${song.title} - ${song.artist}`)
          else failed.push(`${song.title} - ${song.artist}`)
        } catch {
          failed.push(`${song.title} - ${song.artist}`)
        }
      }
      await get().loadPlaylists(userId)
      set({ playlistImporting: false })
      return { playlistId, success, failed }
    } catch (error) {
      set({ playlistImporting: false, playlistImportError: String(error) })
      return null
    }
  },

  importPlaylist: async (userId, playlistName, songList) => {
    set({ playlistImporting: true, playlistImportError: null, lastImportResult: null })
    try {
      if (songList.length === 0) {
        set({ playlistImporting: false, playlistImportError: 'no songs to import' })
        return null
      }
      const response = await apiImportPlaylist({ userId, playlistName, songList })
      if (!response.data) throw new Error(response.message || 'playlist import failed')
      set({ playlistImporting: false, lastImportResult: response.data })
      await get().loadPlaylists(userId)
      return response.data
    } catch (error) {
      set({ playlistImporting: false, playlistImportError: String(error) })
      return null
    }
  },

  loadPlaylists: async (userId) => {
    if (!userId) {
      set({ playlists: [] })
      return
    }
    try {
      const response = await apiGetPlaylists(userId)
      set({ playlists: response.data || [] })
    } catch (error) {
      console.error('[loadPlaylists]', error)
    }
  },

  viewPlaylist: async (playlistId) => {
    try {
      const [playlistResponse, libraryResponse] = await Promise.all([
        apiGetPlaylistDetail(playlistId),
        window.electronAPI.getPlatformLibrary().catch(() => ({ songs: [] })),
      ])
      const detail = playlistResponse.data
      if (!detail) return
      const librarySongs = (libraryResponse.songs || []).map(mapLibrarySong)
      const byIdentity = new Map(librarySongs.map((song) => [makeIdentity(song.title, song.artist), song]))
      const currentPlaylistSongs = detail.songs.map((song) => {
        const local = byIdentity.get(makeIdentity(song.title, song.artist))
        return {
          id: song.songId,
          title: song.title,
          artist: song.artist,
          duration: local?.duration || song.duration || 0,
          format: local?.format || 'mp3',
          fileSize: local?.fileSize || 0,
          sourceType: 'internal_catalog' as const,
          sourcePath: local?.sourcePath || '',
          platformId: local?.platformId,
          platformUrl: local?.platformUrl,
          importStatus: 'ready' as const,
          downloadStatus: local?.sourcePath ? 'downloaded' as const : 'none' as const,
          analysisStatus: (local?.bpm || song.bpm) ? 'completed' as const : 'none' as const,
          bpm: local?.bpm || song.bpm || null,
          beatPoints: local?.beatPoints || [],
          cuePoints: local?.cuePoints || [],
          tags: ((song.tags?.length ? song.tags : local?.tags || []) as DanceStyle[]),
          playlistId,
          createdAt: local?.createdAt || Date.now(),
        }
      })
      set({ currentView: 'playlist', currentPlaylistId: playlistId, currentPlaylistSongs, searchQuery: '', tagFilter: null })
      set((state) => ({ songs: [...state.songs, ...currentPlaylistSongs.filter((song) => !state.songs.some((item) => item.id === song.id))] }))
      void get().fetchAllPlaylistSongs(playlistId)
    } catch (error) {
      console.error('[viewPlaylist]', error)
    }
  },

  deletePlaylist: async (playlistId) => {
    try {
      await apiDeletePlaylist(playlistId)
      set((state) => ({
        playlists: state.playlists.filter((playlist) => playlist.id !== playlistId),
        songs: state.songs.filter((song) => song.playlistId !== playlistId),
        currentPlaylistId: state.currentPlaylistId === playlistId ? null : state.currentPlaylistId,
        currentPlaylistSongs: state.currentPlaylistId === playlistId ? [] : state.currentPlaylistSongs,
        currentView: state.currentPlaylistId === playlistId ? 'my-library' : state.currentView,
      }))
    } catch (error) {
      console.error('[deletePlaylist]', error)
    }
  },

  clearImportResult: () => set({ lastImportResult: null, playlistImportError: null }),

  fetchPlaylistSong: async (songId) => {
    const state = get()
    const song = state.songs.find((item) => item.id === songId) || state.currentPlaylistSongs.find((item) => item.id === songId)
    if (!song || song.sourcePath) return

    const updateSong = (updates: Partial<Song>) => {
      get().updateSong(songId, updates)
    }

    updateSong({ downloadStatus: 'downloading' })
    try {
      const result = await window.electronAPI.fetchPlaylistSong(songId, song.playlistId || '', song.title, song.artist)
      if (result.error) throw new Error(result.error)
      updateSong({
        sourcePath: result.filePath || '',
        fileSize: result.fileSize || 0,
        platformId: result.platformId,
        platformUrl: result.platformUrl,
        downloadStatus: 'downloaded',
      })
      if (result.filePath) {
        updateSong({ analysisStatus: 'analyzing' })
        try {
          const analysis = await window.electronAPI.analyzeAudio(result.filePath, song.duration)
          if (analysis.error) throw new Error(analysis.error)
          updateSong({
            analysisStatus: 'completed',
            bpm: analysis.bpm ?? null,
            beatPoints: analysis.beatPoints ?? [],
            cuePoints: (analysis.cuePoints ?? []).map((cue, index) => ({ id: `cue-${songId}-${index}`, ...cue })),
          })
        } catch {
          updateSong({ analysisStatus: 'error' })
        }
      }
      const updated = get().songs.find((item) => item.id === songId)
      if (updated) void syncSongToLibrary(updated)
    } catch (error) {
      console.error('[fetchPlaylistSong]', error)
      updateSong({ downloadStatus: 'error' })
    }
  },

  fetchAllPlaylistSongs: async (playlistId) => {
    const songs = get().songs.filter((song) => song.playlistId === playlistId && !song.sourcePath && song.downloadStatus !== 'downloading')
    for (const song of songs) {
      await get().fetchPlaylistSong(song.id)
    }
  },
}))
