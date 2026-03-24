import fs from 'node:fs'
import path from 'node:path'

export interface PlatformSongRecord {
  id: string
  title: string
  artist: string
  duration: number
  format: string
  fileSize: number
  sourceType: 'local_file' | 'internal_catalog'
  sourcePath: string       // local file path to the downloaded / imported audio
  platformId?: string      // fangpi music id
  platformUrl?: string     // fangpi music page URL
  bpm: number | null
  beatPoints: number[]
  cuePoints: { id: string; time: number; label: string; color: string }[]
  createdAt: number
}

interface LibraryData {
  version: number
  songs: PlatformSongRecord[]
}

const DB_FILENAME = 'platform-library.json'
const MUSIC_DIR = 'music-files'

let dbPath = ''
let musicDir = ''
let library: LibraryData = { version: 1, songs: [] }

export function initLibrary(baseDir: string) {
  dbPath = path.join(baseDir, DB_FILENAME)
  musicDir = path.join(baseDir, MUSIC_DIR)

  if (!fs.existsSync(musicDir)) {
    fs.mkdirSync(musicDir, { recursive: true })
  }

  if (fs.existsSync(dbPath)) {
    try {
      const raw = fs.readFileSync(dbPath, 'utf-8')
      library = JSON.parse(raw)
    } catch {
      console.error('[platformLibrary] Failed to read DB, starting fresh')
      library = { version: 1, songs: [] }
    }
  }

  console.log(`[platformLibrary] Loaded ${library.songs.length} songs from ${dbPath}`)
}

function saveLibrary() {
  fs.writeFileSync(dbPath, JSON.stringify(library, null, 2), 'utf-8')
}

export function getAllSongs(): PlatformSongRecord[] {
  return library.songs
}

export function addSong(song: PlatformSongRecord): PlatformSongRecord {
  // Check for duplicate by platformId or by title+artist+sourceType
  const existing = library.songs.find(
    (s) =>
      (song.platformId && s.platformId === song.platformId) ||
      (s.title === song.title && s.artist === song.artist && s.sourceType === song.sourceType)
  )
  if (existing) {
    // Update existing record
    Object.assign(existing, song)
    saveLibrary()
    return existing
  }

  library.songs.push(song)
  saveLibrary()
  return song
}

export function removeSong(id: string) {
  library.songs = library.songs.filter((s) => s.id !== id)
  saveLibrary()
}

export function updateSong(id: string, updates: Partial<PlatformSongRecord>) {
  const song = library.songs.find((s) => s.id === id)
  if (song) {
    Object.assign(song, updates)
    saveLibrary()
  }
}

export function getSong(id: string): PlatformSongRecord | undefined {
  return library.songs.find((s) => s.id === id)
}

export function getMusicDir(): string {
  return musicDir
}
