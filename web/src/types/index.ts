export interface User {
  id: number
  username: string
  dance_style: string
  level: string
  favorite_style: string
}

export interface LibrarySong {
  id: string
  user_id: number
  title: string
  artist: string
  duration: number
  format: string
  file_size: number
  source_type: string
  source_path: string
  platform_id: string | null
  platform_url: string | null
  bpm: number | null
  key: string | null
  camelot_key: string | null
  energy: number | null
  analysis_status: string
  beat_points: number[]
  cue_points: CuePoint[]
  stems: { vocals: string; drums: string; bass: string; other: string } | null
  created_at: string
  updated_at: string
}

export interface CuePoint {
  id: string
  time: number
  label: string
  color: string
}

export interface Playlist {
  id: number
  user_id: number
  playlist_name: string
  source_type: string
  song_count: number
}

export interface PlaylistSong {
  song_id: number
  title: string
  artist: string
  audio_url: string | null
  duration: number | null
  bpm: number | null
  tags: string[]
  order_index: number
}

export interface PlaylistDetail {
  id: number
  user_id: number
  playlist_name: string
  source_type: string
  songs: PlaylistSong[]
}

export type DanceStyle =
  | 'hiphop' | 'jazz' | 'breaking' | 'popping' | 'locking'
  | 'waacking' | 'house' | 'krump' | 'funk' | 'urban'
  | 'afro' | 'dancehall' | 'other'

export const DANCE_STYLES: DanceStyle[] = [
  'hiphop', 'jazz', 'breaking', 'popping', 'locking',
  'waacking', 'house', 'krump', 'funk', 'urban',
  'afro', 'dancehall', 'other',
]

export const DANCE_STYLE_LABELS: Record<DanceStyle, string> = {
  hiphop: 'HipHop', jazz: 'Jazz', breaking: 'Breaking', popping: 'Popping',
  locking: 'Locking', waacking: 'Waacking', house: 'House', krump: 'Krump',
  funk: 'Funk', urban: 'Urban', afro: 'Afro', dancehall: 'Dancehall', other: 'Other',
}

export const DANCE_STYLE_COLORS: Record<DanceStyle, string> = {
  hiphop: '#ef4444', jazz: '#f59e0b', breaking: '#3b82f6', popping: '#8b5cf6',
  locking: '#ec4899', waacking: '#14b8a6', house: '#06b6d4', krump: '#dc2626',
  funk: '#f97316', urban: '#a855f7', afro: '#22c55e', dancehall: '#eab308', other: '#64748b',
}

export interface RecommendedSong {
  song_id: number
  title: string
  artist: string
}

export interface UserProfile {
  favorite_style: string
  avg_bpm_preference: number | null
  energy_preference: string | null
  vocal_preference: string | null
  era_preference: string | null
  groove_preference: string | null
}

export interface CatalogSong {
  id: number
  title: string
  artist: string
  audio_url: string | null
  duration: number | null
  bpm: number | null
  energy: string | null
  style: string | null
  vocal_type: string | null
  era_tag: string | null
  groove_tag: string | null
  difficulty_fit: string | null
  tags: string[]
}

export interface SongCue {
  id: number
  cue_type: string
  start_time: number
  end_time: number | null
  label: string | null
}
