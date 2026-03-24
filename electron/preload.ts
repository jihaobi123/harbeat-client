import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  openAudioFiles: (): Promise<Array<{ name: string; path: string; size: number; format: string }>> =>
    ipcRenderer.invoke('dialog:openAudioFiles'),
  getAudioUrl: (filePath: string): Promise<string> =>
    ipcRenderer.invoke('audio:getServerPort').then((port: number) =>
      `http://127.0.0.1:${port}/audio?path=${encodeURIComponent(filePath)}`
    ),
  getPeaks: (filePath: string, numBars: number): Promise<number[] | null> =>
    ipcRenderer.invoke('audio:getPeaks', filePath, numBars),
  analyzeAudio: (filePath: string, duration: number): Promise<{
    bpm?: number; beatPoints?: number[]; cuePoints?: { time: number; label: string; color: string }[]; error?: string
  }> => ipcRenderer.invoke('audio:analyze', filePath, duration),
  searchPlatform: (query: string): Promise<{
    songs: Array<{ id: string; title: string; artist: string; url: string }>; error?: string
  }> => ipcRenderer.invoke('platform:search', query),
  getPlatformLibrary: (): Promise<{ songs: any[]; error?: string }> =>
    ipcRenderer.invoke('platform:getLibrary'),
  addToPlatformLibrary: (songData: any): Promise<{ song?: any; error?: string }> =>
    ipcRenderer.invoke('platform:addToLibrary', songData),
  removeFromPlatformLibrary: (songId: string): Promise<{ success?: boolean; error?: string }> =>
    ipcRenderer.invoke('platform:removeFromLibrary', songId),
  downloadFromPlatform: (musicId: string, title: string, artist: string): Promise<{ song?: any; error?: string }> =>
    ipcRenderer.invoke('platform:download', musicId, title, artist),
})
