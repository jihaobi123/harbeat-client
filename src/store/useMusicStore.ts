import { create } from 'zustand'
import { Song, AudioFileInfo, Playlist, ImportPlaylistResult, DanceStyle } from '../types'
import { type ImportPlaylistRequest } from '../services/api'

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

  // 歌单相关
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

  // 显示相关
  setDisplayMode: (mode: DisplayMode) => void
  setTagFilter: (tag: DanceStyle | null) => void

  // 歌单管理
  importAndDownloadPlaylist: (
    userId: string,
    playlistName: string,
    songList: ImportPlaylistRequest['songList']
  ) => Promise<{ playlistId: string; success: string[]; failed: string[] } | null>
  importPlaylist: (userId: string, playlistName: string, songList: ImportPlaylistRequest['songList']) => Promise<ImportPlaylistResult | null>
  loadPlaylists: (userId?: string) => Promise<void>
  viewPlaylist: (playlistId: string) => Promise<void>
  deletePlaylist: (playlistId: string) => Promise<void>
  clearImportResult: () => void

  // 歌单歌曲下载与分析
  fetchPlaylistSong: (songId: string) => Promise<void>
  fetchAllPlaylistSongs: (playlistId: string) => Promise<void>
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
  displayMode: 'list',
  tagFilter: null,

  // 歌单相关初始状态
  playlists: [],
  currentPlaylistId: null,
  currentPlaylistSongs: [],
  playlistImporting: false,
  playlistImportError: null,
  lastImportResult: null,

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
      tags: [],
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

  setView: (view: ViewType) => set({ currentView: view, searchQuery: '', currentPlaylistId: null, currentPlaylistSongs: [], tagFilter: null }),

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
        tags: (s.tags || []) as DanceStyle[],
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
          tags: (s.tags || []) as DanceStyle[],
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
        tags: [],
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
          tags: (s.tags || []) as DanceStyle[],
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

  // ===== 显示设置 =====
  setDisplayMode: (mode: DisplayMode) => set({ displayMode: mode }),
  setTagFilter: (tag: DanceStyle | null) => set({ tagFilter: tag }),

  // ===== 歌单导入 =====
  importAndDownloadPlaylist: async (userId: string, playlistName: string, songList: ImportPlaylistRequest['songList']) => {
    set({ playlistImporting: true, playlistImportError: null, lastImportResult: null })
    try {
      if (songList.length === 0) {
        set({ playlistImporting: false, playlistImportError: '没有可导入的歌曲' })
        return null
      }

      const playlistId = `playlist-${Date.now()}`
      const storedSongs = songList.map((song, index) => ({
        id: `${playlistId}-song-${index}`,
        title: song.title,
        artist: song.artist,
        duration: song.duration,
        bpm: song.bpm,
        tags: song.tags as string[],
        source: 'thirdparty' as const,
        order: index,
      }))

      await window.electronAPI.savePlaylist({
        id: playlistId,
        name: playlistName,
        userId,
        songCount: storedSongs.length,
        songs: storedSongs,
        createdAt: Date.now(),
      })

      const newSongs: Song[] = storedSongs.map((song) => ({
        id: song.id,
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

      set((state) => ({
        songs: [...state.songs, ...newSongs.filter((song) => !state.songs.some((existing) => existing.id === song.id))],
      }))

      const success: string[] = []
      const failed: string[] = []
      for (const song of storedSongs) {
        try {
          await get().fetchPlaylistSong(song.id)
          const currentSong = get().songs.find((item) => item.id === song.id)
          if (currentSong?.sourcePath) {
            success.push(`${song.title} - ${song.artist}`)
          } else {
            failed.push(`${song.title} - ${song.artist}`)
          }
        } catch {
          failed.push(`${song.title} - ${song.artist}`)
        }
      }

      await get().loadPlaylists(userId)
      set({ playlistImporting: false })
      return { playlistId, success, failed }
    } catch (e) {
      set({ playlistImporting: false, playlistImportError: String(e) })
      return null
    }
  },

  importPlaylist: async (userId: string, playlistName: string, songList: ImportPlaylistRequest['songList']) => {
    set({ playlistImporting: true, playlistImportError: null, lastImportResult: null })
    try {
      if (songList.length === 0) {
        set({ playlistImporting: false, playlistImportError: '没有可导入的歌曲' })
        return null
      }

      const playlistId = `playlist-${Date.now()}`
      const songs = songList.map((s, i) => ({
        id: `${playlistId}-song-${i}`,
        title: s.title,
        artist: s.artist,
        duration: s.duration,
        bpm: s.bpm,
        tags: s.tags as string[],
        source: 'thirdparty' as const,
        order: i,
      }))

      // Save playlist to local database via Electron
      await window.electronAPI.savePlaylist({
        id: playlistId,
        name: playlistName,
        userId,
        songCount: songs.length,
        songs,
        createdAt: Date.now(),
      })

      const pendingCount = songList.filter((s) => s.tags.length === 0 && !s.bpm).length
      const result: ImportPlaylistResult = {
        playlistId,
        importCount: songList.length,
        pendingAnalysisCount: pendingCount,
      }

      // Also add these songs to the store's songs array
      const newSongs: Song[] = songList.map((s, i) => ({
        id: songs[i].id,
        title: s.title,
        artist: s.artist,
        duration: s.duration,
        format: 'mp3',
        fileSize: 0,
        sourceType: 'internal_catalog' as const,
        sourcePath: '',
        importStatus: 'ready' as const,
        analysisStatus: s.bpm ? 'completed' as const : 'none' as const,
        bpm: s.bpm,
        beatPoints: [],
        cuePoints: [],
        tags: s.tags,
        playlistId,
        createdAt: Date.now(),
      }))

      set((state) => ({
        playlistImporting: false,
        lastImportResult: result,
        songs: [...state.songs, ...newSongs],
      }))

      // Refresh playlist list
      await get().loadPlaylists(userId)

      // Auto-trigger download & analysis for all songs (fire-and-forget)
      get().fetchAllPlaylistSongs(playlistId).catch((e) =>
        console.error('[auto-fetch playlist songs]', e)
      )

      return result
    } catch (e) {
      set({ playlistImporting: false, playlistImportError: String(e) })
      return null
    }
  },

  loadPlaylists: async (userId?: string) => {
    try {
      const res = await window.electronAPI.getAllPlaylists(userId)
      const playlists: Playlist[] = (res.playlists || []).map((p: any) => ({
        id: p.id,
        name: p.name,
        userId: p.userId,
        songCount: p.songCount || p.songs?.length || 0,
        createdAt: p.createdAt,
      }))
      set({ playlists })

      // Also add playlist songs to the main songs array
      const allPlaylistSongs: Song[] = []
      for (const p of (res.playlists || []) as any[]) {
        for (const s of (p.songs || []) as any[]) {
          allPlaylistSongs.push({
            id: s.id,
            title: s.title,
            artist: s.artist,
            duration: s.duration || 0,
            format: 'mp3',
            fileSize: 0,
            sourceType: 'internal_catalog' as const,
            sourcePath: s.sourcePath || '',
            importStatus: 'ready' as const,
            analysisStatus: s.bpm ? 'completed' as const : 'none' as const,
            bpm: s.bpm || null,
            beatPoints: [],
            cuePoints: [],
            tags: (s.tags || []) as DanceStyle[],
            playlistId: p.id,
            createdAt: p.createdAt,
          })
        }
      }
      set((state) => {
        const existingIds = new Set(state.songs.map((s) => s.id))
        const newSongs = allPlaylistSongs.filter((s) => !existingIds.has(s.id))
        if (newSongs.length === 0) return state
        return { songs: [...state.songs, ...newSongs] }
      })
    } catch (e) {
      console.error('[loadPlaylists]', e)
    }
  },

  viewPlaylist: async (playlistId: string) => {
    try {
      const res = await window.electronAPI.getPlaylistDetail(playlistId)
      if (!res.playlist) return
      const p = res.playlist
      const songs: Song[] = (p.songs || []).map((s: any) => ({
        id: s.id,
        title: s.title,
        artist: s.artist,
        duration: s.duration || 0,
        format: 'mp3',
        fileSize: 0,
        sourceType: 'internal_catalog' as const,
        sourcePath: s.sourcePath || '',
        importStatus: 'ready' as const,
        downloadStatus: s.sourcePath ? 'downloaded' as const : 'none' as const,
        analysisStatus: s.bpm ? 'completed' as const : 'none' as const,
        bpm: s.bpm || null,
        beatPoints: [],
        cuePoints: [],
        tags: (s.tags || []) as DanceStyle[],
        playlistId,
        createdAt: s.createdAt || p.createdAt,
      }))
      set({
        currentView: 'playlist',
        currentPlaylistId: playlistId,
        currentPlaylistSongs: songs,
        searchQuery: '',
        tagFilter: null,
      })

      // Also sync playlist songs into the main songs array
      set((state) => {
        const existingIds = new Set(state.songs.map((s) => s.id))
        const newSongs = songs.filter((s) => !existingIds.has(s.id))
        if (newSongs.length === 0) return state
        return { songs: [...state.songs, ...newSongs] }
      })

      // Auto-fetch undownloaded songs
      get().fetchAllPlaylistSongs(playlistId).catch((e) =>
        console.error('[auto-fetch on viewPlaylist]', e)
      )
    } catch (e) {
      console.error('[viewPlaylist]', e)
    }
  },

  deletePlaylist: async (playlistId: string) => {
    try {
      await window.electronAPI.deletePlaylist(playlistId)
      set((state) => ({
        playlists: state.playlists.filter((p) => p.id !== playlistId),
        songs: state.songs.filter((s) => s.playlistId !== playlistId),
        currentPlaylistId: state.currentPlaylistId === playlistId ? null : state.currentPlaylistId,
        currentPlaylistSongs: state.currentPlaylistId === playlistId ? [] : state.currentPlaylistSongs,
        currentView: state.currentPlaylistId === playlistId ? 'my-library' : state.currentView,
      }))
    } catch (e) {
      console.error('[deletePlaylist]', e)
    }
  },

  clearImportResult: () => {
    set({ lastImportResult: null, playlistImportError: null })
  },

  // ===== 歌单歌曲下载与分析 =====
  fetchPlaylistSong: async (songId: string) => {
    const state = get()
    const song = state.songs.find((s) => s.id === songId)
      || state.currentPlaylistSongs.find((s) => s.id === songId)
    if (!song || song.sourcePath) return // already has file

    const updateSongInState = (id: string, updates: Partial<Song>) => {
      set((state) => ({
        songs: state.songs.map((s) => s.id === id ? { ...s, ...updates } : s),
        currentPlaylistSongs: state.currentPlaylistSongs.map((s) => s.id === id ? { ...s, ...updates } : s),
      }))
    }

    // Mark as downloading
    updateSongInState(songId, { downloadStatus: 'downloading' })

    try {
      const result = await window.electronAPI.fetchPlaylistSong(
        songId,
        song.playlistId || '',
        song.title,
        song.artist,
      )
      if (result.error) throw new Error(result.error)

      updateSongInState(songId, {
        sourcePath: result.filePath || '',
        fileSize: result.fileSize || 0,
        platformId: result.platformId,
        platformUrl: result.platformUrl,
        downloadStatus: 'downloaded',
      })

      // Auto-analyze
      if (result.filePath) {
        updateSongInState(songId, { analysisStatus: 'analyzing' })
        try {
          const analysis = await window.electronAPI.analyzeAudio(result.filePath, song.duration)
          if (!analysis.error && analysis.bpm) {
            updateSongInState(songId, {
              analysisStatus: 'completed',
              bpm: analysis.bpm ?? null,
              beatPoints: analysis.beatPoints ?? [],
              cuePoints: (analysis.cuePoints ?? []).map((c, i) => ({
                id: `cue-${songId}-${i}`,
                ...c,
              })),
            })

            // Persist BPM to platform library
            window.electronAPI.addToPlatformLibrary({
              id: songId,
              title: song.title,
              artist: song.artist,
              duration: song.duration,
              format: 'mp3',
              fileSize: result.fileSize || 0,
              sourceType: 'internal_catalog',
              sourcePath: result.filePath,
              platformId: result.platformId,
              platformUrl: result.platformUrl,
              bpm: analysis.bpm ?? null,
              beatPoints: analysis.beatPoints ?? [],
              cuePoints: (analysis.cuePoints ?? []).map((c, i) => ({
                id: `cue-${songId}-${i}`,
                ...c,
              })),
              createdAt: song.createdAt,
            }).catch(() => {})
          } else {
            updateSongInState(songId, { analysisStatus: 'error' })
          }
        } catch {
          updateSongInState(songId, { analysisStatus: 'error' })
        }
      }
    } catch (e) {
      console.error('[fetchPlaylistSong error]', songId, e)
      updateSongInState(songId, { downloadStatus: 'error' })
    }
  },

  fetchAllPlaylistSongs: async (playlistId: string) => {
    const state = get()
    const songs = state.songs.filter(
      (s) => s.playlistId === playlistId && !s.sourcePath && s.downloadStatus !== 'downloading'
    )
    // Process sequentially to avoid overwhelming fangpi.net
    for (const song of songs) {
      await get().fetchPlaylistSong(song.id)
    }
  },
}))
