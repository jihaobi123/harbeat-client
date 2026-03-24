import { create } from 'zustand'
import { Song, AudioFileInfo } from '../types'

type ViewType = 'my-library' | 'platform' | 'recent'

interface MusicStore {
  songs: Song[]
  platformSongs: Song[]
  selectedSongId: string | null
  currentView: ViewType
  searchQuery: string
  platformSearchLoading: boolean
  platformSearchError: string | null
  platformLibraryLoaded: boolean

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
}

let songIdCounter = 0
const generateId = () => `song-${Date.now()}-${++songIdCounter}`

export const useMusicStore = create<MusicStore>((set, get) => ({
  songs: [],
  platformSongs: [],
  selectedSongId: null,
  currentView: 'my-library',
  searchQuery: '',
  platformSearchLoading: false,
  platformSearchError: null,
  platformLibraryLoaded: false,

  addSongs: (files: AudioFileInfo[]) => {
    const newSongs: Song[] = files.map((file) => ({
      id: generateId(),
      title: file.name,
      artist: file.artist || '未知艺术家',
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
      createdAt: Date.now(),
    }))
    set((state) => ({ songs: [...state.songs, ...newSongs] }))

    // Also persist each new song to the platform library
    for (const song of newSongs) {
      window.electronAPI.addToPlatformLibrary({
        id: song.id,
        title: song.title,
        artist: song.artist,
        duration: song.duration,
        format: song.format,
        fileSize: song.fileSize,
        sourceType: song.sourceType,
        sourcePath: song.sourcePath,
        bpm: null,
        beatPoints: [],
        cuePoints: [],
        createdAt: song.createdAt,
      }).catch(() => {})
    }
    return newSongs
  },

  removeSong: (id: string) => {
    set((state) => ({
      songs: state.songs.filter((s) => s.id !== id),
      selectedSongId: state.selectedSongId === id ? null : state.selectedSongId,
    }))
  },

  selectSong: (id: string | null) => set({ selectedSongId: id }),

  setView: (view: ViewType) => set({ currentView: view, searchQuery: '' }),

  setSearchQuery: (query: string) => set({ searchQuery: query }),

  updateSong: (id: string, updates: Partial<Song>) => {
    set((state) => ({
      songs: state.songs.map((s) => (s.id === id ? { ...s, ...updates } : s)),
      platformSongs: state.platformSongs.map((s) =>
        s.id === id ? { ...s, ...updates } : s
      ),
    }))

    // Sync analysis results to persistent library
    if (updates.bpm !== undefined || updates.duration !== undefined) {
      const song = get().songs.find((s) => s.id === id)
      if (song) {
        window.electronAPI.addToPlatformLibrary({
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
          createdAt: song.createdAt,
        }).catch(() => {})
      }
    }
  },

  addPlatformSongToLibrary: (songId: string) => {
    const state = get()
    const platformSong = state.platformSongs.find((s) => s.id === songId)
    if (!platformSong) return
    if (
      state.songs.some(
        (s) => s.title === platformSong.title && s.sourceType === 'internal_catalog'
      )
    )
      return

    const newSong: Song = {
      ...platformSong,
      id: generateId(),
      createdAt: Date.now(),
    }
    set((state) => ({ songs: [...state.songs, newSong] }))
  },

  loadPlatformLibrary: async () => {
    try {
      const result = await window.electronAPI.getPlatformLibrary()
      const libSongs: Song[] = (result.songs || []).map((s: any) => ({
        id: s.id,
        title: s.title,
        artist: s.artist,
        duration: s.duration || 0,
        format: s.format || 'mp3',
        fileSize: s.fileSize || 0,
        sourceType: s.sourceType || 'internal_catalog',
        sourcePath: s.sourcePath || '',
        platformId: s.platformId,
        platformUrl: s.platformUrl,
        importStatus: 'ready' as const,
        downloadStatus: s.sourcePath ? 'downloaded' as const : 'none' as const,
        analysisStatus: s.bpm ? 'completed' as const : 'none' as const,
        bpm: s.bpm || null,
        beatPoints: s.beatPoints || [],
        cuePoints: s.cuePoints || [],
        createdAt: s.createdAt || Date.now(),
      }))

      // Add downloaded songs from persistent library to "my library"
      set((state) => {
        const newSongs = [...state.songs]
        for (const ls of libSongs) {
          if (!ls.sourcePath) continue // only songs with local files
          const exists = newSongs.some(
            (s) => s.id === ls.id || (s.platformId && s.platformId === ls.platformId)
          )
          if (!exists) newSongs.push(ls)
        }
        return { songs: newSongs, platformLibraryLoaded: true }
      })

      // If platform view and no search query, show the library
      const state = get()
      if (state.currentView === 'platform' && !state.searchQuery) {
        set({ platformSongs: libSongs })
      }
    } catch (e) {
      console.error('[loadPlatformLibrary]', e)
    }
  },

  downloadSong: async (songId: string) => {
    const state = get()
    const song = state.platformSongs.find((s) => s.id === songId)
    if (!song || !song.platformId) return

    // Mark as downloading
    set((state) => ({
      platformSongs: state.platformSongs.map((s) =>
        s.id === songId ? { ...s, downloadStatus: 'downloading' as const } : s
      ),
    }))

    try {
      const result = await window.electronAPI.downloadFromPlatform(
        song.platformId,
        song.title,
        song.artist,
      )

      if (result.error) throw new Error(result.error)
      if (!result.song) throw new Error('No song data returned')

      const downloaded = result.song

      const updatedSong: Song = {
        ...song,
        sourcePath: downloaded.sourcePath,
        fileSize: downloaded.fileSize,
        downloadStatus: 'downloaded' as const,
        importStatus: 'ready' as const,
      }

      set((state) => {
        // Update in platformSongs
        const newPlatformSongs = state.platformSongs.map((s) =>
          s.id === songId ? updatedSong : s
        )

        // Also add to songs (my library) if not already there
        const alreadyInSongs = state.songs.some(
          (s) => s.platformId === song.platformId || s.id === songId
        )
        const newSongs = alreadyInSongs
          ? state.songs.map((s) =>
              s.platformId === song.platformId || s.id === songId
                ? { ...s, sourcePath: downloaded.sourcePath, fileSize: downloaded.fileSize, downloadStatus: 'downloaded' as const }
                : s
            )
          : [...state.songs, updatedSong]

        return { platformSongs: newPlatformSongs, songs: newSongs }
      })
    } catch (e) {
      console.error('[downloadSong error]', e)
      set((state) => ({
        platformSongs: state.platformSongs.map((s) =>
          s.id === songId ? { ...s, downloadStatus: 'error' as const } : s
        ),
      }))
    }
  },

  searchPlatform: async (query: string) => {
    if (!query.trim()) {
      // Empty query: load from persistent library
      try {
        const result = await window.electronAPI.getPlatformLibrary()
        const libSongs: Song[] = (result.songs || []).map((s: any) => ({
          id: s.id,
          title: s.title,
          artist: s.artist,
          duration: s.duration || 0,
          format: s.format || 'mp3',
          fileSize: s.fileSize || 0,
          sourceType: s.sourceType || 'internal_catalog',
          sourcePath: s.sourcePath || '',
          platformId: s.platformId,
          platformUrl: s.platformUrl,
          importStatus: 'ready' as const,
          downloadStatus: s.sourcePath ? 'downloaded' as const : 'none' as const,
          analysisStatus: s.bpm ? 'completed' as const : 'none' as const,
          bpm: s.bpm || null,
          beatPoints: s.beatPoints || [],
          cuePoints: s.cuePoints || [],
          createdAt: s.createdAt || Date.now(),
        }))

        // Also merge local songs
        const state = get()
        const merged: Song[] = []
        const seen = new Set<string>()
        for (const s of state.songs) {
          const key = `${s.title}||${s.artist}`.toLowerCase()
          if (!seen.has(key)) { seen.add(key); merged.push({ ...s }) }
        }
        for (const s of libSongs) {
          const key = `${s.title}||${s.artist}`.toLowerCase()
          if (!seen.has(key)) { seen.add(key); merged.push(s) }
        }

        set({ platformSongs: merged, platformSearchLoading: false, platformSearchError: null })
      } catch (e) {
        set({ platformSongs: get().songs.map((s) => ({ ...s })), platformSearchLoading: false, platformSearchError: null })
      }
      return
    }

    set({ platformSearchLoading: true, platformSearchError: null })

    try {
      const result = await window.electronAPI.searchPlatform(query)
      const fangpiSongs: Song[] = (result.songs || []).map((s) => ({
        id: `fangpi-${s.id}`,
        title: s.title,
        artist: s.artist,
        duration: 0,
        format: 'mp3',
        fileSize: 0,
        sourceType: 'internal_catalog' as const,
        sourcePath: '',
        platformId: s.id,
        platformUrl: s.url,
        importStatus: 'ready' as const,
        downloadStatus: 'none' as const,
        analysisStatus: 'none' as const,
        bpm: null,
        beatPoints: [],
        cuePoints: [],
        createdAt: Date.now(),
      }))

      // Check which fangpi songs are already downloaded in the library
      let libSongs: Song[] = []
      try {
        const libResult = await window.electronAPI.getPlatformLibrary()
        libSongs = (libResult.songs || []).map((s: any) => ({
          id: s.id,
          title: s.title,
          artist: s.artist,
          duration: s.duration || 0,
          format: s.format || 'mp3',
          fileSize: s.fileSize || 0,
          sourceType: s.sourceType || 'internal_catalog',
          sourcePath: s.sourcePath || '',
          platformId: s.platformId,
          platformUrl: s.platformUrl,
          importStatus: 'ready' as const,
          downloadStatus: s.sourcePath ? 'downloaded' as const : 'none' as const,
          analysisStatus: s.bpm ? 'completed' as const : 'none' as const,
          bpm: s.bpm || null,
          beatPoints: s.beatPoints || [],
          cuePoints: s.cuePoints || [],
          createdAt: s.createdAt || Date.now(),
        }))
      } catch {}

      const libByPlatformId = new Map<string, Song>()
      for (const s of libSongs) {
        if (s.platformId) libByPlatformId.set(s.platformId, s)
      }

      set((state) => {
        const merged: Song[] = []
        const seen = new Set<string>()

        // Local songs matching query first
        for (const s of state.songs) {
          const q = query.toLowerCase()
          if (s.title.toLowerCase().includes(q) || s.artist.toLowerCase().includes(q)) {
            const key = `${s.title}||${s.artist}`.toLowerCase()
            if (!seen.has(key)) { seen.add(key); merged.push({ ...s }) }
          }
        }

        // Then fangpi results, replacing with downloaded version if available
        for (const s of fangpiSongs) {
          const key = `${s.title}||${s.artist}`.toLowerCase()
          if (!seen.has(key)) {
            seen.add(key)
            // Replace with library version if already downloaded
            const libVersion = s.platformId ? libByPlatformId.get(s.platformId) : undefined
            merged.push(libVersion ? { ...libVersion } : s)
          }
        }

        return {
          platformSongs: merged,
          platformSearchLoading: false,
          platformSearchError: result.error || null,
        }
      })
    } catch (e) {
      set({
        platformSearchLoading: false,
        platformSearchError: String(e),
      })
    }
  },
}))
