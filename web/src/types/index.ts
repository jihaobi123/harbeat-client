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
  in_library: boolean
}

export interface DiscoverSongItem {
  song_id: number
  title: string
  artist: string
  style: string | null
  energy: string | null
  in_library: boolean
}

export interface DiscoverSection {
  key: string
  title: string
  icon: string
  description: string
  songs: DiscoverSongItem[]
}

export interface UserProfile {
  favorite_style: string
  avg_bpm_preference: number | null
  energy_preference: string | null
  vocal_preference: string | null
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

/* ─── Style Processing ─── */
export type QualityMode = 'balanced' | 'hq' | 'fast'

export interface StyleProcessMeta {
  selected_models: Record<string, string>
  bpm: number | null
  energy: string | null
  note: string | null
}

export interface StyleProcessResult {
  song_id: number
  processed_files: Record<string, string>
  meta: Record<string, StyleProcessMeta>
}

export interface StyleMixResult {
  playlist: PlaylistSong[]
  processed_files: Record<number, string>
  stem_files: Record<number, Record<string, string>>
  meta: Record<number, Record<string, string>>
}

// ── DJ Auto-Mix types (DJ.studio-inspired) ──────────────────────────────

export interface TransitionAutomation {
  sample_rate: number
  a_drums: number[]
  a_bass: number[]
  a_vocals: number[]
  a_other: number[]
  a_volume: number[]
  a_echo: number[]
  b_drums: number[]
  b_bass: number[]
  b_vocals: number[]
  b_other: number[]
  b_volume: number[]
}

export interface SegmentInfo {
  start_sec: number
  end_sec: number
  bars: number
  label: string
}

export interface TransitionData {
  from_song_id: number
  to_song_id: number
  score: number
  bpm_score: number
  key_score: number
  energy_score: number
  a_play_start: number
  a_play_end: number
  b_play_start: number
  b_play_end: number
  overlap_bars: number
  overlap_sec: number
  mix_start_time: number
  mix_duration_sec: number
  mix_duration_bars: number
  b_cue_time: number
  bpm_shift: number
  automation: TransitionAutomation | null
}

export interface DJMixResult {
  playlist: PlaylistSong[]
  processed_files: Record<number, string>
  stem_files: Record<number, Record<string, string>>
  segments: Record<number, SegmentInfo>
  transitions: TransitionData[]
  energy_profile: string
  harmonic_weight: string
  total_duration_sec: number
  avg_score: number
}
