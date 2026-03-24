/// <reference types="vite/client" />

interface AnalysisResult {
  bpm?: number
  beatPoints?: number[]
  cuePoints?: { time: number; label: string; color: string }[]
  error?: string
}

interface ElectronAPI {
  openAudioFiles: () => Promise<import('./types').AudioFileInfo[]>
  getAudioUrl: (filePath: string) => Promise<string>
  getPeaks: (filePath: string, numBars: number) => Promise<number[] | null>
  analyzeAudio: (filePath: string, duration: number) => Promise<AnalysisResult>
  searchPlatform: (query: string) => Promise<{
    songs: Array<{ id: string; title: string; artist: string; url: string }>
    error?: string
  }>
  getPlatformLibrary: () => Promise<{ songs: any[]; error?: string }>
  addToPlatformLibrary: (songData: any) => Promise<{ song?: any; error?: string }>
  removeFromPlatformLibrary: (songId: string) => Promise<{ success?: boolean; error?: string }>
  downloadFromPlatform: (musicId: string, title: string, artist: string) => Promise<{ song?: any; error?: string }>
  parsePlaylistUrl: (text: string) => Promise<{
    playlist?: { name: string; platform: string; tracks: Array<{ title: string; artist: string; album: string; duration: number }> }
    error?: string
  }>
  savePlaylist: (playlist: any) => Promise<{ playlist?: any; error?: string }>
  getAllPlaylists: (userId?: string) => Promise<{ playlists: any[]; error?: string }>
  getPlaylistDetail: (playlistId: string) => Promise<{ playlist?: any; error?: string }>
  deletePlaylist: (playlistId: string) => Promise<{ success: boolean; error?: string }>
  updatePlaylistSongTags: (playlistId: string, songId: string, tags: string[]) => Promise<{ success: boolean; error?: string }>
  fetchPlaylistSong: (songId: string, playlistId: string, title: string, artist: string) => Promise<{
    filePath?: string; fileSize?: number; platformId?: string; platformUrl?: string; error?: string
  }>
}

interface Window {
  electronAPI: ElectronAPI
}
