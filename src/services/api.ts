import type {
  ApiResponse,
  ImportPlaylistResult,
  Playlist,
  Tag,
  User,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

interface BackendResponse<T> {
  code: number
  message: string
  data: T
}

export interface InitializeUserRequest {
  username: string
  dance_style: string
  level: string
  favorite_style: string
}

export interface ImportPlaylistRequest {
  userId: string
  playlistName: string
  songList: Array<{
    title: string
    artist: string
    duration: number
    bpm: number | null
    tags: string[]
    audioUrl?: string
  }>
}

export interface PlaylistDetailResponse {
  playlist: Playlist
  songs: Array<{
    songId: string
    title: string
    artist: string
    audioUrl?: string
    duration: number
    bpm: number | null
    tags: string[]
    order: number
  }>
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<BackendResponse<T>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  const payload = await response.json().catch(() => null) as BackendResponse<T> | null
  if (!response.ok || !payload) {
    throw new Error(payload?.message || `HTTP ${response.status}`)
  }
  return payload
}

function normalizeUser(raw: {
  id: number
  username: string
  dance_style: string
  level: string
  favorite_style: string
}): User {
  return {
    id: String(raw.id),
    username: raw.username,
    nickname: raw.username,
    danceStyle: raw.dance_style,
    level: raw.level,
    favoriteStyle: raw.favorite_style,
  }
}

export async function initializeUser(params: InitializeUserRequest): Promise<ApiResponse<User>> {
  try {
    const existing = await getUserByUsername(params.username)
    return existing
  } catch {
    const created = await request<{ user_id: number }>('/api/users', {
      method: 'POST',
      body: JSON.stringify(params),
    })
    const user = await getUserInfo(String(created.data.user_id))
    return user
  }
}

export async function getUserInfo(userId: string): Promise<ApiResponse<User>> {
  const response = await request<{
    id: number
    username: string
    dance_style: string
    level: string
    favorite_style: string
  }>(`/api/users/${encodeURIComponent(userId)}`)

  return {
    code: response.code,
    message: response.message,
    data: normalizeUser(response.data),
  }
}

export async function getUserByUsername(username: string): Promise<ApiResponse<User>> {
  const response = await request<{
    id: number
    username: string
    dance_style: string
    level: string
    favorite_style: string
  }>(`/api/users/by-username/${encodeURIComponent(username)}`)

  return {
    code: response.code,
    message: response.message,
    data: normalizeUser(response.data),
  }
}

export async function importPlaylist(params: ImportPlaylistRequest): Promise<ApiResponse<ImportPlaylistResult>> {
  const userId = parseInt(params.userId, 10)
  if (isNaN(userId)) {
    throw new Error('Invalid user id')
  }
  const response = await request<{
    playlist_id: number
    import_count: number
    pending_analysis_count: number
  }>('/api/playlists/import', {
    method: 'POST',
    body: JSON.stringify({
      user_id: userId,
      playlist_name: params.playlistName,
      songs: params.songList.map((song) => ({
        title: song.title,
        artist: song.artist,
        audio_url: song.audioUrl || undefined,
        duration: song.duration || undefined,
        bpm: song.bpm ?? undefined,
        tags: song.tags,
      })),
      source_type: 'playlist_import',
    }),
  })

  return {
    code: response.code,
    message: response.message,
    data: {
      playlistId: String(response.data.playlist_id),
      importCount: response.data.import_count,
      pendingAnalysisCount: response.data.pending_analysis_count,
    },
  }
}

export async function getPlaylists(userId: string): Promise<ApiResponse<Playlist[]>> {
  const response = await request<{
    playlists: Array<{
      id: number
      user_id: number
      playlist_name: string
      source_type: string
      song_count: number
    }>
  }>(`/api/playlists?user_id=${encodeURIComponent(userId)}`)

  return {
    code: response.code,
    message: response.message,
    data: response.data.playlists.map((playlist) => ({
      id: String(playlist.id),
      name: playlist.playlist_name,
      userId: String(playlist.user_id),
      songCount: playlist.song_count,
      createdAt: Date.now(),
    })),
  }
}

export async function getPlaylistDetail(playlistId: string): Promise<ApiResponse<PlaylistDetailResponse>> {
  const response = await request<{
    id: number
    user_id: number
    playlist_name: string
    source_type: string
    songs: Array<{
      song_id: number
      title: string
      artist: string
      audio_url?: string
      duration?: number
      bpm?: number
      tags: string[]
      order_index: number
    }>
  }>(`/api/playlists/${encodeURIComponent(playlistId)}`)

  return {
    code: response.code,
    message: response.message,
    data: {
      playlist: {
        id: String(response.data.id),
        name: response.data.playlist_name,
        userId: String(response.data.user_id),
        songCount: response.data.songs.length,
        createdAt: Date.now(),
      },
      songs: response.data.songs.map((song) => ({
        songId: String(song.song_id),
        title: song.title,
        artist: song.artist,
        audioUrl: song.audio_url,
        duration: song.duration || 0,
        bpm: song.bpm || null,
        tags: song.tags || [],
        order: song.order_index,
      })),
    },
  }
}

export async function deletePlaylist(playlistId: string): Promise<ApiResponse<{ success: boolean }>> {
  const response = await request<{ success: boolean }>(`/api/playlists/${encodeURIComponent(playlistId)}`, {
    method: 'DELETE',
  })
  return response
}

export async function updatePlaylistSongTags(
  playlistId: string,
  songId: string,
  tags: string[],
): Promise<ApiResponse<{ success: boolean }>> {
  return request<{ success: boolean }>(
    `/api/playlists/${encodeURIComponent(playlistId)}/songs/${encodeURIComponent(songId)}/tags`,
    {
      method: 'PATCH',
      body: JSON.stringify({ tags }),
    }
  )
}

export async function getTagsBySong(songId: string): Promise<ApiResponse<Tag[]>> {
  const response = await request<{
    id: number
    title: string
    artist: string
    tags: string[]
  }>(`/api/music/songs/${encodeURIComponent(songId)}`)

  return {
    code: response.code,
    message: response.message,
    data: response.data.tags.map((tag) => ({
      id: `${songId}-${tag}`,
      name: tag,
      style: tag as Tag['style'],
    })),
  }
}
