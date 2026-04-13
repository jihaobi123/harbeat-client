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
  library_song_id: string | null
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

export interface VibeSearchSongItem {
  song_id: number
  title: string
  artist: string
  style: string | null
  energy: string | null
  distance: number
  in_library: boolean
}

export interface VibeSearchResult {
  query: string
  vibe_description: string
  genres: string[]
  songs: VibeSearchSongItem[]
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
  meta: Record<number, Record<string, string>>
}

export interface DjFxAutomationPoint {
  target?: 'from' | 'to'
  time_sec: number
  gain_db: number
  lowpass_hz: number
  highpass_hz: number
  eq_low_db: number
  eq_mid_db: number
  eq_high_db: number
}

export interface DjTransitionPlanItem {
  from_song_id: number
  to_song_id: number
  entry_beat: number
  exit_beat: number
  entry_time_sec?: number | null
  exit_time_sec?: number | null
  from_beat_interval_sec?: number | null
  to_beat_interval_sec?: number | null
  phase_anchor_sec?: number | null
  crossfade_sec: number
  tempo_ratio: number
  key_relation: string
  transition_technique?: string
  energy_target: string
  fx_automation: DjFxAutomationPoint[]
  score: number
}

export interface DjMixPlanResult extends StyleMixResult {
  transition_plan: DjTransitionPlanItem[]
}

export interface DjOfflineMixResult {
  mix_plan: DjMixPlanResult
  output_files: Record<string, string>
  stream_files: Record<string, string>
  warnings: string[]
  stem_rule_events: Array<Record<string, string | number | boolean | string[]>>
  sample_rate: number
  duration_sec: number
}
