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
  const json: ApiResponse<T> = await res.json()

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
  user_id: number; mode: string; current_song_id?: number; target_energy?: string
}) {
  return request<{ songs: import('../types').RecommendedSong[] }>(
    '/api/recommendations/for-user', { method: 'POST', body: JSON.stringify(data) }
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
  return request<{ songs: { id: string; title: string; artist: string; url: string }[] }>(
    '/api/fangpi/search', { method: 'POST', body: JSON.stringify({ query }) }
  )
}

export async function downloadFangpi(musicId: string, title: string, artist: string) {
  return request<import('../types').LibrarySong>(
    '/api/fangpi/download', { method: 'POST', body: JSON.stringify({ music_id: musicId, title, artist }) }
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
      candidates: { id: string; title: string; artist: string; url: string }[]
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
