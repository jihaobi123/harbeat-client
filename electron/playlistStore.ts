import fs from 'node:fs'
import path from 'node:path'

// ===== 本地歌单存储 =====
// 存储位置: database/playlists.json

export interface StoredPlaylistSong {
  id: string
  title: string
  artist: string
  album?: string
  duration: number
  bpm: number | null
  tags: string[]          // DanceStyle values
  source: 'thirdparty' | 'local' | 'platform'
  sourcePath?: string     // 本地文件路径
  platformId?: string
  platformUrl?: string
  order: number
}

export interface StoredPlaylist {
  id: string
  name: string
  userId: string
  songCount: number
  songs: StoredPlaylistSong[]
  createdAt: number
}

interface PlaylistDB {
  version: number
  playlists: StoredPlaylist[]
}

let dbPath = ''
let db: PlaylistDB = { version: 1, playlists: [] }

export function initPlaylistStore(baseDir: string) {
  dbPath = path.join(baseDir, 'playlists.json')

  if (fs.existsSync(dbPath)) {
    try {
      const raw = fs.readFileSync(dbPath, 'utf-8')
      db = JSON.parse(raw)
    } catch {
      console.error('[playlistStore] Failed to read DB, starting fresh')
      db = { version: 1, playlists: [] }
    }
  }

  console.log(`[playlistStore] Loaded ${db.playlists.length} playlists from ${dbPath}`)
}

function save() {
  fs.writeFileSync(dbPath, JSON.stringify(db, null, 2), 'utf-8')
}

export function savePlaylist(playlist: StoredPlaylist): StoredPlaylist {
  const existing = db.playlists.findIndex((p) => p.id === playlist.id)
  if (existing >= 0) {
    db.playlists[existing] = playlist
  } else {
    db.playlists.push(playlist)
  }
  save()
  return playlist
}

export function getAllPlaylists(userId?: string): StoredPlaylist[] {
  if (userId) {
    return db.playlists.filter((p) => p.userId === userId)
  }
  return db.playlists
}

export function getPlaylist(playlistId: string): StoredPlaylist | undefined {
  return db.playlists.find((p) => p.id === playlistId)
}

export function deletePlaylist(playlistId: string): boolean {
  const before = db.playlists.length
  db.playlists = db.playlists.filter((p) => p.id !== playlistId)
  if (db.playlists.length < before) {
    save()
    return true
  }
  return false
}

export function updatePlaylistSongTags(
  playlistId: string,
  songId: string,
  tags: string[]
): boolean {
  const playlist = db.playlists.find((p) => p.id === playlistId)
  if (!playlist) return false
  const song = playlist.songs.find((s) => s.id === songId)
  if (!song) return false
  song.tags = tags
  save()
  return true
}

export function updatePlaylistSongSource(
  playlistId: string,
  songId: string,
  updates: { sourcePath?: string; platformId?: string; platformUrl?: string; bpm?: number | null }
): boolean {
  const playlist = db.playlists.find((p) => p.id === playlistId)
  if (!playlist) return false
  const song = playlist.songs.find((s) => s.id === songId)
  if (!song) return false
  if (updates.sourcePath !== undefined) song.sourcePath = updates.sourcePath
  if (updates.platformId !== undefined) song.platformId = updates.platformId
  if (updates.platformUrl !== undefined) song.platformUrl = updates.platformUrl
  if (updates.bpm !== undefined) song.bpm = updates.bpm
  save()
  return true
}
