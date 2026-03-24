import fs from 'node:fs'
import path from 'node:path'

export interface PlatformCuePointRecord {
  id: string
  time: number
  label: string
  color: string
}

export interface PlatformSongRecord {
  id: string
  title: string
  artist: string
  duration: number
  format: string
  fileSize: number
  sourceType: 'local_file' | 'internal_catalog'
  sourcePath: string
  platformId?: string
  platformUrl?: string
  bpm: number | null
  beatPoints: number[]
  cuePoints: PlatformCuePointRecord[]
  createdAt: number
}

interface LibrarySongApiRecord {
  id: string
  user_id: number
  title: string
  artist: string
  duration: number
  format: string
  file_size: number
  source_type: 'local_file' | 'internal_catalog'
  source_path: string
  platform_id?: string
  platform_url?: string
  bpm: number | null
  beat_points: number[]
  cue_points: PlatformCuePointRecord[]
  created_at: string
  updated_at: string
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

const DEFAULT_LIBRARY_API_URL = 'http://127.0.0.1:8000'
const DEFAULT_LIBRARY_USER_ID = 1
const MUSIC_DIR = 'music-files'

let musicDir = ''

function getLibraryApiUrl(): string {
  return process.env.LIBRARY_API_URL || process.env.VITE_LIBRARY_API_URL || DEFAULT_LIBRARY_API_URL
}

function getLibraryUserId(): number {
  const raw = process.env.LIBRARY_USER_ID || process.env.VITE_LIBRARY_USER_ID
  const parsed = raw ? Number.parseInt(raw, 10) : DEFAULT_LIBRARY_USER_ID
  return Number.isNaN(parsed) ? DEFAULT_LIBRARY_USER_ID : parsed
}

function mapFromApi(song: LibrarySongApiRecord): PlatformSongRecord {
  return {
    id: song.id,
    title: song.title,
    artist: song.artist,
    duration: song.duration || 0,
    format: song.format || 'mp3',
    fileSize: song.file_size || 0,
    sourceType: song.source_type || 'internal_catalog',
    sourcePath: song.source_path || '',
    platformId: song.platform_id,
    platformUrl: song.platform_url,
    bpm: song.bpm,
    beatPoints: song.beat_points || [],
    cuePoints: song.cue_points || [],
    createdAt: song.created_at ? new Date(song.created_at).getTime() : Date.now(),
  }
}

function mapToApi(song: PlatformSongRecord): Record<string, unknown> {
  return {
    id: song.id,
    user_id: getLibraryUserId(),
    title: song.title,
    artist: song.artist,
    duration: song.duration,
    format: song.format,
    file_size: song.fileSize,
    source_type: song.sourceType,
    source_path: song.sourcePath,
    platform_id: song.platformId,
    platform_url: song.platformUrl,
    bpm: song.bpm,
    beat_points: song.beatPoints,
    cue_points: song.cuePoints,
    created_at: new Date(song.createdAt).toISOString(),
  }
}

async function request<T>(pathname: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getLibraryApiUrl()}${pathname}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })

  const payload = await response.json() as ApiResponse<T>
  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.message || `Request failed: ${response.status}`)
  }
  return payload.data
}

export async function initLibrary(baseDir: string) {
  musicDir = path.join(baseDir, MUSIC_DIR)
  if (!fs.existsSync(musicDir)) {
    fs.mkdirSync(musicDir, { recursive: true })
  }
}

export async function getAllSongs(): Promise<PlatformSongRecord[]> {
  const data = await request<{ songs: LibrarySongApiRecord[] }>(
    `/api/library/songs?user_id=${getLibraryUserId()}`
  )
  return (data.songs || []).map(mapFromApi)
}

export async function addSong(song: PlatformSongRecord): Promise<PlatformSongRecord> {
  const saved = await request<LibrarySongApiRecord>('/api/library/songs', {
    method: 'POST',
    body: JSON.stringify(mapToApi(song)),
  })
  return mapFromApi(saved)
}

export async function removeSong(id: string): Promise<void> {
  await request<{ success: boolean }>(`/api/library/songs/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}

export async function updateSong(
  id: string,
  updates: Partial<PlatformSongRecord>,
): Promise<PlatformSongRecord> {
  const payload: Record<string, unknown> = {}
  if (updates.title !== undefined) payload.title = updates.title
  if (updates.artist !== undefined) payload.artist = updates.artist
  if (updates.duration !== undefined) payload.duration = updates.duration
  if (updates.format !== undefined) payload.format = updates.format
  if (updates.fileSize !== undefined) payload.file_size = updates.fileSize
  if (updates.sourceType !== undefined) payload.source_type = updates.sourceType
  if (updates.sourcePath !== undefined) payload.source_path = updates.sourcePath
  if (updates.platformId !== undefined) payload.platform_id = updates.platformId
  if (updates.platformUrl !== undefined) payload.platform_url = updates.platformUrl
  if (updates.bpm !== undefined) payload.bpm = updates.bpm
  if (updates.beatPoints !== undefined) payload.beat_points = updates.beatPoints
  if (updates.cuePoints !== undefined) payload.cue_points = updates.cuePoints

  const saved = await request<LibrarySongApiRecord>(
    `/api/library/songs/${encodeURIComponent(id)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  )
  return mapFromApi(saved)
}

export function getMusicDir(): string {
  return musicDir
}
