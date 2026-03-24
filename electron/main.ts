import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import http from 'node:http'
import { fileURLToPath } from 'node:url'
import { decryptNcm } from './ncmDecrypt'
import { analyzeAudio as realAnalyzeAudio, computePeaks as realComputePeaks } from './audioAnalyzer'
import { searchFangpi, downloadFangpiSong } from './fangpiService'
import { initLibrary, getAllSongs, addSong, removeSong as removeLibrarySong, updateSong as updateLibrarySong, getMusicDir, PlatformSongRecord } from './platformLibrary'

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
          "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http://127.0.0.1:* http://localhost:* ws://localhost:*"
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

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
