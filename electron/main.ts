import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import http from 'node:http'
import { fileURLToPath } from 'node:url'
import { decryptNcm } from './ncmDecrypt'
import { analyzeAudio as realAnalyzeAudio, computePeaks as realComputePeaks } from './audioAnalyzer'
import { searchFangpi, downloadFangpiSong, type FangpiSong } from './fangpiService'
import { parsePlaylistUrl } from './playlistParser'
import { initLibrary, getAllSongs, addSong, removeSong as removeLibrarySong, updateSong as updateLibrarySong, getMusicDir, PlatformSongRecord } from './platformLibrary'
import { initPlaylistStore, savePlaylist, getAllPlaylists, getPlaylist, deletePlaylist, updatePlaylistSongTags, updatePlaylistSongSource, type StoredPlaylist, type StoredPlaylistSong } from './playlistStore'

// Disable GPU to prevent native renderer crash (0xC0000005)
app.disableHardwareAcceleration()

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const AUDIO_MIME: Record<string, string> = {
  '.mp3': 'audio/mpeg',
  '.aac': 'audio/aac',
  '.m4a': 'audio/mp4',
  '.wav': 'audio/wav',
  '.ogg': 'audio/ogg',
  '.oga': 'audio/ogg',
  '.opus': 'audio/opus',
  '.flac': 'audio/flac',
  '.wma': 'audio/x-ms-wma',
  '.aiff': 'audio/aiff',
  '.aif': 'audio/aiff',
  '.ape': 'audio/x-ape',
  '.wv': 'audio/x-wavpack',
  '.m4b': 'audio/mp4',
  '.m4r': 'audio/mp4',
  '.amr': 'audio/amr',
  '.mid': 'audio/midi',
  '.midi': 'audio/midi',
  '.webm': 'audio/webm',
}

// Allowed file paths — only files that were opened via dialog can be served
const allowedPaths = new Set<string>()

let audioServerPort = 0

function normalizeFangpiText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[()（）\[\]【】'"`]/g, ' ')
    .replace(/feat\.?|ft\.?/gi, ' ')
    .replace(/\s+\/\s+.+$/g, ' ')
    .replace(/[^a-zA-Z0-9\u4e00-\u9fa5]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

function buildPlaylistSearchQueries(title: string, artist: string): string[] {
  const normalizedTitle = title.trim()
  const normalizedArtist = artist.split('/')[0].split(' / ')[0].trim()
  const titleWithoutParen = normalizedTitle.replace(/\s*[（(].*?[)）]\s*/g, ' ').replace(/\s+/g, ' ').trim()

  return Array.from(new Set([
    normalizedTitle,
    titleWithoutParen,
    `${normalizedTitle} ${normalizedArtist}`.trim(),
    `${titleWithoutParen} ${normalizedArtist}`.trim(),
  ].filter((query) => query.length > 0)))
}

function scoreFangpiCandidate(song: FangpiSong, title: string, artist: string): number {
  const targetTitle = normalizeFangpiText(title)
  const targetArtist = normalizeFangpiText(artist)
  const songTitle = normalizeFangpiText(song.title)
  const songArtist = normalizeFangpiText(song.artist)

  let score = 0
  if (songTitle === targetTitle) score += 100
  else if (songTitle.includes(targetTitle) || targetTitle.includes(songTitle)) score += 65

  if (targetArtist && songArtist === targetArtist) score += 50
  else if (targetArtist && (songArtist.includes(targetArtist) || targetArtist.includes(songArtist))) score += 25

  return score
}

async function findBestFangpiCandidates(title: string, artist: string): Promise<FangpiSong[]> {
  const candidates = new Map<string, FangpiSong>()
  const queries = buildPlaylistSearchQueries(title, artist)

  for (const query of queries) {
    try {
      const results = await searchFangpi(query)
      for (const result of results) {
        if (!candidates.has(result.id)) {
          candidates.set(result.id, result)
        }
      }
      if (results.length > 0 && query === title.trim()) {
        break
      }
    } catch (error) {
      console.warn('[fangpi search fallback]', query, error)
    }
  }

  return Array.from(candidates.values()).sort(
    (left, right) => scoreFangpiCandidate(right, title, artist) - scoreFangpiCandidate(left, title, artist)
  )
}

// Start a local HTTP server to serve audio files safely
function startAudioServer(): Promise<number> {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      try {
        if (!req.url) { res.writeHead(400).end(); return }
        const url = new URL(req.url, `http://localhost`)
        const filePath = url.searchParams.get('path')
        if (!filePath) { res.writeHead(400).end('Missing path'); return }

        // Security: only serve files the user explicitly chose
        if (!allowedPaths.has(filePath)) { res.writeHead(403).end('Forbidden'); return }

        const ext = path.extname(filePath).toLowerCase()
        const mime = AUDIO_MIME[ext]
        if (!mime) { res.writeHead(415).end('Unsupported format'); return }
        if (!fs.existsSync(filePath)) { res.writeHead(404).end('Not found'); return }

        const stat = fs.statSync(filePath)
        const range = req.headers.range

        if (range) {
          // Support range requests for seeking
          const parts = range.replace(/bytes=/, '').split('-')
          const start = parseInt(parts[0], 10)
          const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1
          const chunkSize = end - start + 1
          const stream = fs.createReadStream(filePath, { start, end })
          res.writeHead(206, {
            'Content-Range': `bytes ${start}-${end}/${stat.size}`,
            'Accept-Ranges': 'bytes',
            'Content-Length': chunkSize,
            'Content-Type': mime,
            'Access-Control-Allow-Origin': '*',
          })
          stream.pipe(res)
        } else {
          res.writeHead(200, {
            'Content-Length': stat.size,
            'Content-Type': mime,
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*',
          })
          fs.createReadStream(filePath).pipe(res)
        }
      } catch (e) {
        console.error('[audio server error]', e)
        if (!res.headersSent) res.writeHead(500).end('Internal error')
      }
    })

    // Listen on random available port on localhost only
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address()
      const port = typeof addr === 'object' && addr ? addr.port : 0
      console.log(`[audio server] listening on http://127.0.0.1:${port}`)
      resolve(port)
    })
  })
}

let mainWindow: BrowserWindow | null = null

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: '#0d0d12',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  })

  // Allow connecting to local audio server
  mainWindow.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http://127.0.0.1:* http://localhost:* ws://localhost:* https:"
        ],
      },
    })
  })

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL)
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error('[CRASH] Renderer gone:', details.reason, details.exitCode)
  })
}

app.whenReady().then(async () => {
  // Use project folder for database and music files
  const dbDir = path.join(__dirname, '..', 'database')
  if (!fs.existsSync(dbDir)) fs.mkdirSync(dbDir, { recursive: true })
  initLibrary(dbDir)
  initPlaylistStore(dbDir)
  audioServerPort = await startAudioServer()

  // Register all previously downloaded music files as allowed for audio server
  for (const song of getAllSongs()) {
    if (song.sourcePath) allowedPaths.add(song.sourcePath)
  }

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

// IPC: Open file dialog and return audio file info
ipcMain.handle('dialog:openAudioFiles', async () => {
  if (!mainWindow) return []

  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    filters: [
      {
        name: 'Audio Files',
        extensions: [
          'mp3', 'aac', 'm4a', 'wav', 'ogg', 'oga', 'opus', 'flac',
          'wma', 'aiff', 'aif', 'ape', 'wv', 'm4b', 'm4r', 'amr',
          'mid', 'midi', 'webm',
          'ncm', // NetEase Cloud Music encrypted
        ],
      },
    ],
  })

  if (result.canceled || result.filePaths.length === 0) return []

  return result.filePaths.map((filePath) => {
    const stats = fs.statSync(filePath)
    const ext = path.extname(filePath).toLowerCase().slice(1)
    const name = path.basename(filePath, path.extname(filePath))

    // NCM files need decryption first
    if (ext === 'ncm') {
      try {
        const ncmResult = decryptNcm(filePath)
        // Register the decrypted file path
        allowedPaths.add(ncmResult.audioPath)
        return {
          name: ncmResult.title || name,
          artist: ncmResult.artist,
          path: ncmResult.audioPath,
          originalPath: filePath,
          size: fs.statSync(ncmResult.audioPath).size,
          format: ncmResult.format,
        }
      } catch (e) {
        console.error('[NCM decrypt error]', e)
        return { name, path: filePath, size: stats.size, format: 'ncm', error: 'decrypt_failed' }
      }
    }

    // Register this path as allowed
    allowedPaths.add(filePath)
    return { name, path: filePath, size: stats.size, format: ext }
  })
})

// IPC: Get the audio server port
ipcMain.handle('audio:getServerPort', () => audioServerPort)

// IPC: Compute waveform peaks via FFmpeg decoding (real PCM data)
ipcMain.handle('audio:getPeaks', async (_event, filePath: string, numBars: number) => {
  try {
    if (!allowedPaths.has(filePath)) return null
    return realComputePeaks(filePath, numBars)
  } catch (e) {
    console.error('[getPeaks error]', e)
    return null
  }
})

// IPC: Analyze audio — real BPM detection via FFmpeg decode + DSP
ipcMain.handle('audio:analyze', async (_event, filePath: string, totalDuration: number) => {
  try {
    if (!allowedPaths.has(filePath)) return { error: 'File not allowed' }
    console.log('[analyze] start:', filePath)
    const result = realAnalyzeAudio(filePath, totalDuration || undefined)
    console.log('[analyze] done. BPM:', result.bpm, 'beats:', result.beatPoints.length, 'cues:', result.cuePoints.length)
    return { bpm: result.bpm, beatPoints: result.beatPoints, cuePoints: result.cuePoints }
  } catch (e) {
    console.error('[analyze error]', e)
    return { error: String(e) }
  }
})

// IPC: Search platform songs from fangpi.net
ipcMain.handle('platform:search', async (_event, query: string) => {
  try {
    console.log('[platform:search]', query)
    const results = await searchFangpi(query)
    console.log('[platform:search] results:', results.length)
    return { songs: results }
  } catch (e) {
    console.error('[platform:search error]', e)
    return { songs: [], error: String(e) }
  }
})

// IPC: Get all songs from persistent platform library
ipcMain.handle('platform:getLibrary', async () => {
  try {
    return { songs: getAllSongs() }
  } catch (e) {
    console.error('[platform:getLibrary error]', e)
    return { songs: [], error: String(e) }
  }
})

// IPC: Add a song to the persistent platform library (e.g. from local import)
ipcMain.handle('platform:addToLibrary', async (_event, songData: PlatformSongRecord) => {
  try {
    const saved = addSong(songData)
    if (saved.sourcePath) allowedPaths.add(saved.sourcePath)
    return { song: saved }
  } catch (e) {
    console.error('[platform:addToLibrary error]', e)
    return { error: String(e) }
  }
})

// IPC: Remove a song from the persistent platform library
ipcMain.handle('platform:removeFromLibrary', async (_event, songId: string) => {
  try {
    removeLibrarySong(songId)
    return { success: true }
  } catch (e) {
    console.error('[platform:removeFromLibrary error]', e)
    return { error: String(e) }
  }
})

// IPC: Download a song from fangpi.net to local platform library
ipcMain.handle('platform:download', async (_event, musicId: string, title: string, artist: string) => {
  try {
    console.log('[platform:download]', musicId, title, artist)
    const destDir = getMusicDir()
    const { filePath, fileSize } = await downloadFangpiSong(musicId, title, artist, destDir)

    // Register as allowed for audio server
    allowedPaths.add(filePath)

    // Save to persistent library
    const songRecord: PlatformSongRecord = {
      id: `fangpi-${musicId}`,
      title,
      artist,
      duration: 0,
      format: 'mp3',
      fileSize,
      sourceType: 'internal_catalog',
      sourcePath: filePath,
      platformId: musicId,
      platformUrl: `https://www.fangpi.net/music/${musicId}`,
      bpm: null,
      beatPoints: [],
      cuePoints: [],
      createdAt: Date.now(),
    }
    const saved = addSong(songRecord)
    console.log('[platform:download] saved:', saved.id, filePath)
    return { song: saved }
  } catch (e) {
    console.error('[platform:download error]', e)
    return { error: String(e) }
  }
})

// IPC: Parse third-party playlist URL (NetEase / QQ Music)
ipcMain.handle('playlist:parse', async (_event, text: string) => {
  try {
    console.log('[playlist:parse]', text.substring(0, 80))
    const result = await parsePlaylistUrl(text)
    console.log('[playlist:parse] done:', result.name, result.tracks.length, 'tracks')
    return { playlist: result }
  } catch (e) {
    console.error('[playlist:parse error]', e)
    return { error: String(e) }
  }
})

// IPC: Save a playlist with its songs to local database
ipcMain.handle('playlist:save', async (_event, playlist: StoredPlaylist) => {
  try {
    const saved = savePlaylist(playlist)
    // Also add songs to platform library for unified access
    for (const song of playlist.songs) {
      if (song.sourcePath) {
        addSong({
          id: song.id,
          title: song.title,
          artist: song.artist,
          duration: song.duration,
          format: song.sourcePath ? song.sourcePath.split('.').pop() || 'mp3' : 'mp3',
          fileSize: 0,
          sourceType: song.sourcePath ? 'local_file' : 'internal_catalog',
          sourcePath: song.sourcePath || '',
          platformId: song.platformId,
          platformUrl: song.platformUrl,
          bpm: song.bpm,
          beatPoints: [],
          cuePoints: [],
          createdAt: Date.now(),
        })
        allowedPaths.add(song.sourcePath)
      }
    }
    return { playlist: saved }
  } catch (e) {
    console.error('[playlist:save error]', e)
    return { error: String(e) }
  }
})

// IPC: Get all playlists
ipcMain.handle('playlist:getAll', async (_event, userId?: string) => {
  try {
    return { playlists: getAllPlaylists(userId) }
  } catch (e) {
    console.error('[playlist:getAll error]', e)
    return { playlists: [], error: String(e) }
  }
})

// IPC: Get a single playlist with songs
ipcMain.handle('playlist:getDetail', async (_event, playlistId: string) => {
  try {
    const playlist = getPlaylist(playlistId)
    return { playlist: playlist || null }
  } catch (e) {
    console.error('[playlist:getDetail error]', e)
    return { playlist: null, error: String(e) }
  }
})

// IPC: Delete a playlist
ipcMain.handle('playlist:delete', async (_event, playlistId: string) => {
  try {
    const success = deletePlaylist(playlistId)
    return { success }
  } catch (e) {
    console.error('[playlist:delete error]', e)
    return { success: false, error: String(e) }
  }
})

// IPC: Update song tags within a playlist
ipcMain.handle('playlist:updateSongTags', async (_event, playlistId: string, songId: string, tags: string[]) => {
  try {
    const success = updatePlaylistSongTags(playlistId, songId, tags)
    return { success }
  } catch (e) {
    console.error('[playlist:updateSongTags error]', e)
    return { success: false, error: String(e) }
  }
})

// IPC: Search fangpi.net for a song, download it, and update the playlist DB
ipcMain.handle('playlist:fetchSong', async (_event, songId: string, playlistId: string, title: string, artist: string) => {
  try {
    console.log('[playlist:fetchSong]', title, artist)
    const candidates = await findBestFangpiCandidates(title, artist)
    if (candidates.length === 0) return { error: '未找到匹配歌曲' }

    const destDir = getMusicDir()
    let lastError: unknown = null

    for (const candidate of candidates) {
      try {
        const { filePath, fileSize } = await downloadFangpiSong(candidate.id, title, artist, destDir)

        allowedPaths.add(filePath)

        const platformId = candidate.id
        const platformUrl = candidate.url || `https://www.fangpi.net/music/${candidate.id}`

        addSong({
          id: songId,
          title,
          artist,
          duration: 0,
          format: 'mp3',
          fileSize,
          sourceType: 'internal_catalog',
          sourcePath: filePath,
          platformId,
          platformUrl,
          bpm: null,
          beatPoints: [],
          cuePoints: [],
          createdAt: Date.now(),
        })

        if (playlistId) {
          updatePlaylistSongSource(playlistId, songId, { sourcePath: filePath, platformId, platformUrl })
        }

        console.log('[playlist:fetchSong] matched:', candidate.title, candidate.artist, candidate.id)
        console.log('[playlist:fetchSong] done:', filePath)
        return { filePath, fileSize, platformId, platformUrl }
      } catch (error) {
        lastError = error
        console.warn('[playlist:fetchSong candidate failed]', candidate.id, candidate.title, candidate.artist, error)
      }
    }

    return { error: String(lastError || '未找到可下载的匹配歌曲') }
  } catch (e) {
    console.error('[playlist:fetchSong error]', e)
    return { error: String(e) }
  }
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
