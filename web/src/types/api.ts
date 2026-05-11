// ── API Response wrapper ──
export interface APIResponse<T> {
  code: number;
  message: string;
  data: T;
}

// ── Auth ──
export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  dance_style?: string;
  level?: string;
}

export interface TokenData {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: number;
  username: string;
}

// ── DJ Mix types ──
export type QualityMode = 'balanced' | 'hq' | 'fast';
export type OutputFormat = 'wav' | 'mp3' | 'both';
export type RenderEngine = 'simple' | 'groove';
export type OnlineMixMode = 'full_mix' | 'short_fade' | 'hard_cut' | 'normal_crossfade';
export type MixDeck = 'A' | 'B';
export type MixCurve = 'linear' | 'ease_in_out' | 'equal_power_in' | 'equal_power_out';
export type MixParam = 'gain' | 'low_eq' | 'mid_eq' | 'high_eq' | 'highpass_hz' | 'lowpass_hz' | 'playback_rate';

export interface StyleMixRequest {
  style: string;
  duration_minutes?: number;
  bpm?: number;
  energy?: string;
  playlist_id?: number;
  quality_mode?: QualityMode;
  random_seed?: number;
  diversity?: number;
  user_id?: number;
}

export interface PlaylistSongData {
  song_id: number;
  library_song_id?: string;
  title: string;
  artist: string;
  audio_url?: string;
  duration?: number;
  bpm?: number;
  replay_gain_db?: number;
  loudness_lufs?: number;
  key?: string;
  energy?: number;
  format?: string;
  analysis_status?: string;
  tags: string[];
  order_index: number;
}

export interface StyleMixResult {
  playlist: PlaylistSongData[];
  processed_files: Record<number, string>;
  meta: Record<number, Record<string, string>>;
}

export interface DjMixPlanRequest {
  style: string;
  duration_minutes?: number;
  bpm?: number;
  energy?: string;
  playlist_id?: number;
  quality_mode?: QualityMode;
  strict_harmonic?: boolean;
  max_tempo_shift?: number;
  random_seed?: number;
  diversity?: number;
  candidate_window?: number;
  user_id?: number;
  scene_type?: string;
  style_ratios?: Record<string, number>;
  use_context_planner?: boolean;
}

export interface DjFxAutomationPoint {
  target: 'from' | 'to';
  time_sec: number;
  gain_db?: number;
  lowpass_hz?: number;
  highpass_hz?: number;
  eq_low_db?: number;
  eq_mid_db?: number;
  eq_high_db?: number;
}

export interface OnlineMixSafety {
  online_mix_safe: boolean;
  recommended_mode: OnlineMixMode;
  fallback_mode: OnlineMixMode;
  min_prepare_sec: number;
  preload_before_sec: number;
  reasons: string[];
}

export interface DeckLoadEvent {
  type: 'deck_load';
  deck: MixDeck;
  time_sec: number;
  song_id: number;
  position_sec?: number;
}

export interface DeckPlayEvent {
  type: 'deck_play';
  deck: MixDeck;
  time_sec: number;
  position_sec?: number;
  playback_rate?: number;
  key_lock?: boolean;
}

export interface DeckStopEvent {
  type: 'deck_stop';
  deck: MixDeck;
  time_sec: number;
}

export interface ParamRampEvent {
  type: 'param_ramp';
  deck: MixDeck;
  time_sec: number;
  duration_sec: number;
  param: MixParam;
  from: number;
  from_?: number;
  to: number;
  curve?: MixCurve;
}

export interface ParamSetEvent {
  type: 'param_set';
  deck: MixDeck;
  time_sec: number;
  param: MixParam;
  value: number;
}

export type MixControlEvent = DeckLoadEvent | DeckPlayEvent | DeckStopEvent | ParamRampEvent | ParamSetEvent;

export interface MixControlTimeline {
  transition_id?: string;
  mode: OnlineMixMode;
  start_at_from_time_sec?: number;
  duration_sec: number;
  events: MixControlEvent[];
}

export interface DjTransitionPlanItem {
  from_song_id: number;
  to_song_id: number;
  entry_beat: number;
  exit_beat: number;
  entry_time_sec?: number;
  exit_time_sec?: number;
  from_beat_interval_sec?: number;
  to_beat_interval_sec?: number;
  phase_anchor_sec?: number;
  crossfade_sec: number;
  tempo_ratio: number;
  key_relation: string;
  transition_technique: string;
  energy_target: string;
  fx_automation: DjFxAutomationPoint[];
  score: number;
  online_mix_safety?: OnlineMixSafety;
  mix_control_timeline?: MixControlTimeline;
}

export interface DjMixPlanResult {
  playlist: PlaylistSongData[];
  processed_files: Record<number, string>;
  meta: Record<number, Record<string, string>>;
  transition_plan: DjTransitionPlanItem[];
}

export interface MixLoopRegion {
  start_bar: number;
  end_bar: number;
  repeat_count: number;
  song_id: number;
}

export interface DjOfflineMixRequest {
  style: string;
  duration_minutes?: number;
  bpm?: number;
  energy?: string;
  playlist_id?: number;
  quality_mode?: QualityMode;
  strict_harmonic?: boolean;
  max_tempo_shift?: number;
  random_seed?: number;
  diversity?: number;
  candidate_window?: number;
  user_id?: number;
  output_format?: OutputFormat;
  output_name?: string;
  stem_aware?: boolean;
  auto_separate_stems?: boolean;
  max_auto_stem_tracks?: number;
  stem_separation_timeout_sec?: number;
  render_engine?: RenderEngine;
  loop_regions?: MixLoopRegion[];
}

export interface DjOfflineMixResult {
  mix_plan: DjMixPlanResult;
  output_files: Record<string, string>;
  stream_files: Record<string, string>;
  warnings: string[];
  stem_rule_events: Record<string, unknown>[];
  sample_rate: number;
  duration_sec: number;
}

// ── Voice Control ──
export type VoiceIntent =
  | 'play' | 'pause' | 'hold' | 'release' | 'next'
  | 'lift_energy' | 'drop_energy' | 'switch_style'
  | 'emergency_stop' | 'noop';

export interface VoiceCommandRequest {
  text: string;
  session_id?: string;
  user_id?: number;
  language_hint?: 'auto' | 'zh' | 'en';
}

export interface VoiceCommandResponse {
  intent: VoiceIntent;
  confidence: number;
  matched_keywords: string[];
  command_payload: { command: string; payload: Record<string, unknown> } | null;
  action_taken: string;
  error?: string;
}

// ── Recommend ──
export interface VibeSearchRequest {
  query: string;
  user_id?: number;
  top_k?: number;
}

export interface VibeSearchSongItem {
  song_id?: number;
  title: string;
  artist: string;
  style?: string;
  energy?: string;
  spotify_id?: string;
  preview_url?: string;
  album_art?: string;
  spotify_url?: string;
  source: string;
  in_library: boolean;
  match_percentage: number;
}

export interface VibeSearchData {
  query: string;
  vibe_description: string;
  search_query: string;
  genres: string[];
  songs: VibeSearchSongItem[];
}

// ── Library ──
export interface LibrarySong {
  id: string;
  user_id: number;
  song_id: number;
  title: string;
  artist: string;
  duration: number;
  format: string;
  file_size: number;
  source_type: string;
  bpm?: number;
  key?: string;
  camelot_key?: string;
  energy?: string;
  analysis_status?: string;
  replay_gain_db?: number;
}
