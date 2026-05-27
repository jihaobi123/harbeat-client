const BASE = ''  // same-origin, proxied in dev

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

function getToken(): string | null {
  return localStorage.getItem('harbeat_token')
}

export function setToken(token: string) {
  localStorage.setItem('harbeat_token', token)
}

export function clearToken() {
  localStorage.removeItem('harbeat_token')
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }

  const token = getToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // Only set Content-Type for non-FormData bodies
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }

  const res = await fetch(`${BASE}${url}`, { ...options, headers })

  let json: ApiResponse<T>
  try {
    json = await res.json()
  } catch {
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    throw new Error('invalid server response')
  }

  if (!res.ok || json.code !== 0) {
    throw new Error(json.message || `HTTP ${res.status}`)
  }

  return json.data
}

// ---- Auth ----
export async function register(data: {
  username: string; password: string;
  dance_style?: string; level?: string; favorite_style?: string
}) {
  return request<{ access_token: string; user_id: number; username: string }>(
    '/api/auth/register', { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function login(username: string, password: string) {
  return request<{ access_token: string; user_id: number; username: string }>(
    '/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }
  )
}

export async function getMe() {
  return request<{ id: number; username: string; dance_style: string; level: string; favorite_style: string }>(
    '/api/auth/me'
  )
}

// ---- Library ----
export async function getLibrarySongs() {
  return request<{ songs: import('../types').LibrarySong[] }>('/api/library/songs')
}

export async function getLibrarySong(songId: string) {
  return request<import('../types').LibrarySong>(`/api/library/songs/${songId}`)
}

export async function searchLibrarySongs(q: string) {
  return request<{ songs: import('../types').LibrarySong[] }>(`/api/library/songs/search?q=${encodeURIComponent(q)}`)
}

export async function uploadSong(file: File, title?: string, artist?: string) {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  if (artist) form.append('artist', artist)
  return request<import('../types').LibrarySong>('/api/library/upload', { method: 'POST', body: form })
}

export async function analyzeSong(songId: string) {
  return request<import('../types').LibrarySong>(`/api/library/songs/${songId}/analyze`, { method: 'POST' })
}

export async function deleteSong(songId: string) {
  return request<{ success: boolean }>(`/api/library/songs/${songId}`, { method: 'DELETE' })
}

export function getStreamUrl(songId: string): string {
  const token = getToken()
  return `${BASE}/api/stream/${songId}?token=${token || ''}`
}

export function getStemStreamUrl(songId: string, stemName: string): string {
  const token = getToken()
  return `${BASE}/api/stream/${songId}/stem/${stemName}?token=${token || ''}`
}

// ---- Playlists ----
export async function getPlaylists(userId: number) {
  return request<{ playlists: import('../types').Playlist[] }>(`/api/playlists?user_id=${userId}`)
}

export async function getPlaylistDetail(playlistId: number) {
  return request<import('../types').PlaylistDetail>(`/api/playlists/${playlistId}`)
}

export async function importPlaylist(data: {
  user_id: number; playlist_name: string; source_type?: string;
  songs: { title: string; artist: string; duration?: number; bpm?: number; tags?: string[] }[]
}) {
  return request<{ playlist_id: number; import_count: number; pending_analysis_count: number }>(
    '/api/playlists/import', { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function deletePlaylist(playlistId: number) {
  return request<{ success: boolean }>(`/api/playlists/${playlistId}`, { method: 'DELETE' })
}

export async function updatePlaylistSongTags(playlistId: number, songId: number, tags: string[]) {
  return request<{ success: boolean }>(
    `/api/playlists/${playlistId}/songs/${songId}/tags`,
    { method: 'PATCH', body: JSON.stringify({ tags }) }
  )
}

// ---- Catalog Music (songs table) ----
export async function getCatalogSongs() {
  return request<{ songs: import('../types').CatalogSong[] }>('/api/music/songs')
}

export async function searchCatalogSongs(q: string) {
  return request<{ songs: import('../types').CatalogSong[] }>(`/api/music/songs/search?q=${encodeURIComponent(q)}`)
}

export async function getCatalogSong(songId: number) {
  return request<import('../types').CatalogSong>(`/api/music/songs/${songId}`)
}

export async function updateSongTags(songId: number, tags: {
  bpm?: number; energy?: string; style?: string; vocal_type?: string;
  era_tag?: string; groove_tag?: string; difficulty_fit?: string; tags?: string[]
}) {
  return request<import('../types').CatalogSong>(
    `/api/music/songs/${songId}/tags`, { method: 'PATCH', body: JSON.stringify(tags) }
  )
}

export async function upsertSongTags(data: {
  title: string; artist: string; tags?: string[]; energy?: string[]; scenes?: string[]; bpm?: number
}) {
  return request<import('../types').CatalogSong>(
    '/api/music/songs/upsert', { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function createCue(songId: number, data: {
  user_id: number; song_id: number; cue_type: string; start_time: number;
  end_time?: number; label?: string
}) {
  return request<import('../types').SongCue>(
    `/api/music/songs/${songId}/cues`, { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function getCues(songId: number, userId: number) {
  return request<import('../types').SongCue[]>(`/api/music/songs/${songId}/cues?user_id=${userId}`)
}

// ---- Recommendations ----
export async function getRecommendations(data: {
  user_id: number; mode: string; current_song_id?: number; target_energy?: string; source?: string
}) {
  return request<{ songs: import('../types').RecommendedSong[] }>(
    '/api/recommendations/for-user', { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function discoverSongs(userId: number) {
  return request<{ sections: import('../types').DiscoverSection[] }>(
    '/api/recommendations/discover', { method: 'POST', body: JSON.stringify({ user_id: userId }) }
  )
}

export async function addSongToLibrary(userId: number, songId: number) {
  return request<{ library_song_id: string; title: string; artist: string }>(
    '/api/recommendations/add-to-library', { method: 'POST', body: JSON.stringify({ user_id: userId, song_id: songId }) }
  )
}

// ---- Profiles ----
export async function generateProfile(userId: number) {
  return request<import('../types').UserProfile>(
    '/api/profiles/generate', { method: 'POST', body: JSON.stringify({ user_id: userId }) }
  )
}

export async function getProfile(userId: number) {
  return request<import('../types').UserProfile>(`/api/profiles/${userId}`)
}

// ---- Sessions ----
export async function startSession(userId: number, mode: string) {
  return request<{ session_id: number }>(
    '/api/sessions/start', { method: 'POST', body: JSON.stringify({ user_id: userId, mode }) }
  )
}

export async function logSessionEvent(sessionId: number, eventType: string, eventValue?: string) {
  return request<{ success: boolean }>(
    '/api/sessions/event', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, event_type: eventType, event_value: eventValue, timestamp: new Date().toISOString() })
    }
  )
}

export async function endSession(sessionId: number) {
  return request<{ success: boolean }>(
    '/api/sessions/end', { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }
  )
}

// ---- Fangpi.net ----
export async function searchFangpi(query: string) {
  return request<{ songs: { id: string; title: string; artist: string; url: string; source?: string }[] }>(
    '/api/fangpi/search', { method: 'POST', body: JSON.stringify({ query }) }
  )
}

export async function downloadFangpi(musicId: string, title: string, artist: string, tags?: { tags?: string[]; energy?: string[]; scenes?: string[] }, source?: string) {
  return request<import('../types').LibrarySong>(
    '/api/fangpi/download', { method: 'POST', body: JSON.stringify({ music_id: musicId, title, artist, ...tags, source: source || 'fangpi' }) }
  )
}

export async function parsePlaylistUrl(url: string) {
  return request<{ name: string; platform: string; tracks: { title: string; artist: string; album: string; duration: number }[] }>(
    '/api/fangpi/parse-playlist', { method: 'POST', body: JSON.stringify({ url }) }
  )
}

export async function batchSearchFangpi(songs: { title: string; artist: string }[]) {
  return request<{
    results: {
      title: string; artist: string; found: boolean;
      candidates: { id: string; title: string; artist: string; url: string; source?: string }[]
    }[]
  }>(
    '/api/fangpi/batch-search', { method: 'POST', body: JSON.stringify({ songs }) }
  )
}

// ---- Playlists (create / add songs) ----
export async function createPlaylist(name: string) {
  return request<{ id: number; playlist_name: string }>(
    '/api/playlists/create', { method: 'POST', body: JSON.stringify({ name }) }
  )
}

export async function addSongsToPlaylist(playlistId: number, librarySongIds: string[]) {
  return request<{ added: number }>(
    `/api/playlists/${playlistId}/add-songs`, { method: 'POST', body: JSON.stringify({ library_song_ids: librarySongIds }) }
  )
}

// ---- Stem Separation ----
export async function separateStems(songId: string) {
  return request<{ stems: { vocals: string; drums: string; bass: string; other: string } }>(
    `/api/library/songs/${songId}/separate-stems`, { method: 'POST' }
  )
}

// ---- Sessions / Interaction Logs ----
export interface InteractionLogPayload {
  user_id: number
  track_id: string
  action_type: string
  listen_mode?: string
  current_dance_style?: string
  play_duration_sec?: number
  completion_rate?: number
  skip_timestamp?: number | null
  drum_boost_enabled?: boolean
  bpm_adjusted_to?: number | null
  ab_loop_used?: boolean
  cue_points_added?: number
  rewind_count?: number
}

export async function logInteraction(payload: InteractionLogPayload) {
  return request<{ success: boolean }>(
    '/api/sessions/log-interaction', { method: 'POST', body: JSON.stringify(payload) }
  )
}

export interface PracticeTrack {
  id: string
  title: string
  artist: string
  bpm: number | null
  camelot_key: string | null
  energy: number | null
  duration: number
}

export async function generatePracticeList(userId: number, targetDuration: number = 30, danceStyle?: string) {
  return request<{ user_id: number; target_duration: number; tracks: PracticeTrack[] }>(
    '/api/sessions/generate-practice-list', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, target_duration: targetDuration, dance_style: danceStyle })
    }
  )
}

// ---- Style Processing ----
export async function processSongStyle(songId: number, data: {
  styles: string[]; bpm?: number; energy?: string; quality_mode?: import('../types').QualityMode
}) {
  return request<import('../types').StyleProcessResult>(
    `/api/music/songs/${songId}/process-style`, { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function generateStyleMix(data: {
  style: string; duration_minutes?: number; bpm?: number; energy?: string; quality_mode?: import('../types').QualityMode
}) {
  return request<import('../types').StyleMixResult>(
    '/api/playlists/generate-style-mix', { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function generateDjMixPlan(data: {
  style: string
  duration_minutes?: number
  bpm?: number
  energy?: string
  playlist_id?: number
  quality_mode?: import('../types').QualityMode
  strict_harmonic?: boolean
  max_tempo_shift?: number
  random_seed?: number
  diversity?: number
  candidate_window?: number
}) {
  return request<import('../types').DjMixPlanResult>(
    '/api/playlists/generate-dj-mix-plan',
    { method: 'POST', body: JSON.stringify(data) }
  )
}

export async function generateDjOfflineMix(data: {
  style: string
  duration_minutes?: number
  bpm?: number
  energy?: string
  playlist_id?: number
  quality_mode?: import('../types').QualityMode
  strict_harmonic?: boolean
  max_tempo_shift?: number
  random_seed?: number
  diversity?: number
  candidate_window?: number
  output_format?: 'wav' | 'mp3' | 'both'
  output_name?: string
  stem_aware?: boolean
  auto_separate_stems?: boolean
  max_auto_stem_tracks?: number
  stem_separation_timeout_sec?: number
}) {
  return request<import('../types').DjOfflineMixResult>(
    '/api/playlists/generate-dj-offline-mix',
    { method: 'POST', body: JSON.stringify(data) }
  )
}

export function getProcessedStreamUrl(filePath: string): string {
  const token = getToken()
  // filePath looks like "data/music-files/shared/processed/1_breaking_balanced.wav"
  const filename = filePath.split('/').pop() || filePath
  return `${BASE}/api/stream/processed/${encodeURIComponent(filename)}?token=${token || ''}`
}

export function getMixStreamUrl(filename: string): string {
  const token = getToken()
  return `${BASE}/api/stream/mixes/${encodeURIComponent(filename)}?token=${token || ''}`
}

// ---- DJ Control ----
export interface DjStyle { key: string; label_zh: string; bpm_range: [number, number] }
export interface DjScoredSong {
  song_id: string; title: string; artist: string
  bpm: number | null; duration: number | null; score: number; energy: number | null
}
export interface DjSequenceEntry {
  song_id: string; position: number; target_energy: number; actual_energy: number
  breakdown: Record<string, number>
}
export interface DjTransitionRule { key: string; label_zh: string }
export interface DjFxItem { key: string; label_zh: string; default_duration: number }

export async function djListStyles() {
  return request<{ styles: DjStyle[] }>('/api/dj/styles')
}
export async function djPickByStyle(style: string, target_duration_sec: number, min_score = 0.35) {
  return request<{ style: string; target_duration_sec: number; achieved_duration_sec: number; songs: DjScoredSong[] }>(
    '/api/dj/styles/pick', { method: 'POST', body: JSON.stringify({ style, target_duration_sec, min_score }) }
  )
}
export async function djListSequencePresets() {
  return request<{ presets: string[] }>('/api/dj/sequence/presets')
}
export async function djSequence(song_ids: string[], preset: string) {
  return request<{ preset: string; sequence: DjSequenceEntry[] }>(
    '/api/dj/sequence', { method: 'POST', body: JSON.stringify({ song_ids, preset }) }
  )
}
export async function djSongEnergy(songId: string) {
  return request<Record<string, number>>(`/api/dj/songs/${songId}/energy`)
}
export async function djListTransitionRules() {
  return request<{ analyzed: DjTransitionRule[]; raw: DjTransitionRule[] }>('/api/dj/transitions/rules')
}
export async function djPlanTransition(prev_song_id: string, next_song_id: string, cursor_sec = 0, rule_key?: string) {
  return request<Record<string, unknown>>(
    '/api/dj/transitions/plan',
    { method: 'POST', body: JSON.stringify({ prev_song_id, next_song_id, cursor_sec, rule_key }) }
  )
}
export async function djPlanCut(payload: {
  strategy: 'fast_cut' | 'energy_up_cut' | 'energy_down_cut'
  current_song_id: string
  cursor_sec: number
  queue_song_ids: string[]
  current_index: number
  pool_song_ids?: string[]
  max_wait_sec?: number
}) {
  return request<Record<string, unknown>>('/api/dj/cut/plan', { method: 'POST', body: JSON.stringify(payload) })
}
export async function djListFx() {
  return request<{ fx: DjFxItem[] }>('/api/dj/fx')
}
export function djFxAudioUrl(key: string, duration?: number) {
  const q = duration ? `?duration=${duration}` : ''
  return `${BASE}/api/dj/fx/${key}.wav${q}`
}
