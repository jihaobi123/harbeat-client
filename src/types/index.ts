export interface Song {
  id: string
  title: string
  artist: string
  duration: number // seconds
  format: string
  fileSize: number // bytes
  sourceType: 'local_file' | 'internal_catalog'
  sourcePath: string // local file path, empty for catalog songs
  platformId?: string   // fangpi.net music id
  platformUrl?: string  // fangpi.net music page URL
  importStatus: 'importing' | 'ready' | 'error'
  downloadStatus?: 'none' | 'downloading' | 'downloaded' | 'error'
  analysisStatus: 'none' | 'analyzing' | 'completed' | 'error'
  bpm: number | null
  beatPoints: number[] // timestamps in seconds
  cuePoints: CuePoint[]
  createdAt: number // timestamp ms
}

export interface CuePoint {
  id: string
  time: number // seconds
  label: string
  color: string
}

export interface AudioAsset {
  id: string
  songId: string
  localPath: string
  objectUrl: string | null
  waveformData: number[] | null
  playable: boolean
  decodable: boolean
}

export interface AudioFileInfo {
  name: string
  path: string
  size: number
  format: string
  artist?: string
  originalPath?: string
  error?: string
}
