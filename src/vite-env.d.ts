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
}

interface Window {
  electronAPI: ElectronAPI
}
