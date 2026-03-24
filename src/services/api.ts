import type { ApiResponse, LoginRequest, LoginResponse, User, ImportPlaylistResult, Playlist, Tag, DanceStyle } from '../types'

// 后端 API 基础地址，后续部署时替换为实际地址
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3000/api'

// 开发模式：设为 true 时跳过后端，用本地 mock 数据
const DEV_MOCK = !import.meta.env.VITE_API_BASE_URL

// ===== 通用请求封装 =====

function getToken(): string | null {
  try {
    const stored = localStorage.getItem('harbeat_user')
    if (stored) {
      const user = JSON.parse(stored) as User
      return user.token
    }
  } catch { /* ignore */ }
  return null
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }

  return res.json()
}

// ===== 认证相关 =====

export async function login(params: LoginRequest): Promise<LoginResponse> {
  if (DEV_MOCK) {
    // 开发模式：任意用户名密码均可登录
    const mockUser: User = {
      id: 'dev-user-001',
      username: params.username,
      nickname: params.username,
      token: 'dev-mock-token',
    }
    return { code: 0, message: 'ok', data: { user: mockUser, token: 'dev-mock-token' } }
  }
  const res = await request<{ user: User; token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(params),
  })
  return {
    code: res.code,
    message: res.message,
    data: res.data,
  }
}

export async function getUserInfo(): Promise<ApiResponse<User>> {
  if (DEV_MOCK) {
    return { code: 0, message: 'ok', data: undefined }
  }
  return request<User>('/auth/me')
}

// ===== 歌单导入 =====

export interface ImportPlaylistRequest {
  userId: string
  playlistName: string
  songList: Array<{
    title: string
    artist: string
    duration: number
    bpm: number | null
    tags: DanceStyle[]    // 已有的舞种标签
    fileHash?: string     // 可选，用于去重
  }>
}

export async function importPlaylist(
  params: ImportPlaylistRequest
): Promise<ApiResponse<ImportPlaylistResult>> {
  if (DEV_MOCK) {
    // 开发模式：模拟导入结果
    const pendingCount = params.songList.filter((s) => s.tags.length === 0 && !s.bpm).length
    const mockResult: ImportPlaylistResult = {
      playlistId: `playlist-${Date.now()}`,
      importCount: params.songList.length,
      pendingAnalysisCount: pendingCount,
    }
    // 模拟保存到本地
    const existing = JSON.parse(localStorage.getItem('harbeat_playlists') || '[]') as Playlist[]
    existing.push({
      id: mockResult.playlistId,
      name: params.playlistName,
      userId: params.userId,
      songCount: params.songList.length,
      createdAt: Date.now(),
    })
    localStorage.setItem('harbeat_playlists', JSON.stringify(existing))
    return { code: 0, message: 'ok', data: mockResult }
  }
  return request<ImportPlaylistResult>('/playlists/import', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

// ===== 歌单管理 =====

export async function getPlaylists(userId: string): Promise<ApiResponse<Playlist[]>> {
  if (DEV_MOCK) {
    const all = JSON.parse(localStorage.getItem('harbeat_playlists') || '[]') as Playlist[]
    return { code: 0, message: 'ok', data: all.filter((p) => p.userId === userId) }
  }
  return request<Playlist[]>(`/playlists?userId=${encodeURIComponent(userId)}`)
}

export async function getPlaylistDetail(playlistId: string): Promise<ApiResponse<{
  playlist: Playlist
  songs: Array<{ songId: string; title: string; artist: string; tags: Tag[]; order: number }>
}>> {
  return request(`/playlists/${encodeURIComponent(playlistId)}`)
}

// ===== 标签管理 =====

export async function getAllTags(): Promise<ApiResponse<Tag[]>> {
  return request<Tag[]>('/tags')
}

export async function getTagsBySong(songId: string): Promise<ApiResponse<Tag[]>> {
  return request<Tag[]>(`/songs/${encodeURIComponent(songId)}/tags`)
}

export async function addTagToSong(
  songId: string,
  style: DanceStyle
): Promise<ApiResponse<Tag>> {
  return request<Tag>(`/songs/${encodeURIComponent(songId)}/tags`, {
    method: 'POST',
    body: JSON.stringify({ style }),
  })
}
