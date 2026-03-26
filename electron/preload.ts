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
    bpm?: number; key?: string; camelotKey?: string; beatPoints?: number[]; cuePoints?: { time: number; label: string; color: string }[]; error?: string
  }> => ipcRenderer.invoke('audio:analyze', filePath, duration),
  separateStems: (filePath: string): Promise<{
    stems?: { vocals: string; drums: string; bass: string; other: string }; error?: string
  }> => ipcRenderer.invoke('audio:separateStems', filePath),
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
  parsePlaylistUrl: (text: string): Promise<{
    playlist?: { name: string; platform: string; tracks: Array<{ title: string; artist: string; album: string; duration: number }> };
    error?: string
  }> => ipcRenderer.invoke('playlist:parse', text),
  savePlaylist: (playlist: any): Promise<{ playlist?: any; error?: string }> =>
    ipcRenderer.invoke('playlist:save', playlist),
  getAllPlaylists: (userId?: string): Promise<{ playlists: any[]; error?: string }> =>
    ipcRenderer.invoke('playlist:getAll', userId),
  getPlaylistDetail: (playlistId: string): Promise<{ playlist?: any; error?: string }> =>
    ipcRenderer.invoke('playlist:getDetail', playlistId),
  deletePlaylist: (playlistId: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('playlist:delete', playlistId),
  updatePlaylistSongTags: (playlistId: string, songId: string, tags: string[]): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('playlist:updateSongTags', playlistId, songId, tags),
  fetchPlaylistSong: (songId: string, playlistId: string, title: string, artist: string): Promise<{
    filePath?: string; fileSize?: number; platformId?: string; platformUrl?: string; error?: string
  }> =>
    ipcRenderer.invoke('playlist:fetchSong', songId, playlistId, title, artist),
})
