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
  key: string | null
  camelotKey: string | null
  stems: {
    vocals: string
    drums: string
    bass: string
    other: string
  } | null
  tags: DanceStyle[]
  playlistId?: string      // 所属歌单ID
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

// ===== 舞种标签 =====
export type DanceStyle =
  | 'hiphop'
  | 'jazz'
  | 'breaking'
  | 'popping'
  | 'locking'
  | 'waacking'
  | 'house'
  | 'krump'
  | 'funk'
  | 'urban'
  | 'afro'
  | 'dancehall'
  | 'other'

export interface Tag {
  id: string
  name: string
  style: DanceStyle
}

// ===== 歌单 =====
export interface Playlist {
  id: string
  name: string
  userId: string
  songCount: number
  createdAt: number
}

export interface PlaylistSong {
  playlistId: string
  songId: string
  order: number
}

export interface PlaylistWithSongs extends Playlist {
  songs: Song[]
}

// ===== 导入歌单结果 =====
export interface ImportPlaylistResult {
  playlistId: string
  importCount: number
  pendingAnalysisCount: number
}

// ===== 用户认证 =====
export interface User {
  id: string
  username: string
  nickname?: string
  avatar?: string
  token?: string
  danceStyle?: string
  level?: string
  favoriteStyle?: string
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  code: number
  message: string
  data?: {
    user: User
    token: string
  }
}

export interface ApiResponse<T = any> {
  code: number
  message: string
  data?: T
}
