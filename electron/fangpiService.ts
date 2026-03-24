import https from 'node:https'
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'

export interface FangpiSong {
  id: string          // fangpi music id
  title: string
  artist: string
  url: string         // full URL to the music page on fangpi.net
}

/**
 * Search songs on fangpi.net by keyword.
 * Fetches the search results page and parses HTML to extract song list.
 */
export async function searchFangpi(query: string): Promise<FangpiSong[]> {
  if (!query.trim()) return []

  const encoded = encodeURIComponent(query.trim())
  const url = `https://www.fangpi.net/s/${encoded}`

  const html = await fetchPage(url)
  return parseSearchResults(html)
}

function fetchPage(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http
    const req = mod.get(
      url,
      {
        headers: {
          'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          Accept:
            'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        },
        timeout: 10000,
      },
      (res) => {
        // Follow redirects (3xx)
        if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          fetchPage(res.headers.location).then(resolve).catch(reject)
          return
        }
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode}`))
          return
        }

        const chunks: Buffer[] = []
        res.on('data', (chunk: Buffer) => chunks.push(chunk))
        res.on('end', () => resolve(Buffer.concat(chunks).toString('utf-8')))
        res.on('error', reject)
      },
    )
    req.on('error', reject)
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('Request timeout'))
    })
  })
}

/**
 * Parse the search results HTML from fangpi.net.
 * Song links: <a href="/music/11572022" ... title="阴天快乐 - 陈奕迅">
 * The title attribute contains "songTitle - artist".
 */
function parseSearchResults(html: string): FangpiSong[] {
  // Extract only the search results section (between "搜索结果" and the sidebar)
  const startIdx = html.indexOf('搜索结果')
  if (startIdx < 0) return []
  // The results section ends at the next card/sidebar or "热门推荐" / "相关专题"
  let endIdx = html.indexOf('热门推荐', startIdx)
  if (endIdx < 0) endIdx = html.indexOf('相关专题', startIdx)
  if (endIdx < 0) endIdx = html.indexOf('大家都在搜', startIdx)
  if (endIdx < 0) endIdx = html.length

  const section = html.substring(startIdx, endIdx)

  const results: FangpiSong[] = []
  const seen = new Set<string>()

  // Match <a> tags linking to /music/{id} with title="xxx - yyy"
  const regex = /href=["']\/music\/(\d+)["'][^>]*title=["']([^"']+?)\s+-\s+([^"']+?)["']/gi
  let match: RegExpExecArray | null

  while ((match = regex.exec(section)) !== null) {
    const id = match[1]
    const title = decodeHtmlEntities(match[2].trim())
    const artist = decodeHtmlEntities(match[3].trim())

    // Skip duplicates
    if (seen.has(id) || !title || !artist) continue

    seen.add(id)
    results.push({
      id,
      title,
      artist,
      url: `https://www.fangpi.net/music/${id}`,
    })
  }

  return results
}

function decodeHtmlEntities(s: string): string {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
}

/**
 * Get the direct audio CDN URL for a fangpi music page.
 * Flow: fetch /music/{id} → parse window.appData for play_id → POST /api/play-url → CDN URL
 */
export async function getFangpiAudioUrl(musicId: string): Promise<string> {
  // Step 1: fetch the music page to extract appData
  const pageHtml = await fetchPage(`https://www.fangpi.net/music/${musicId}`)

  // Extract the JSON.parse('...') content from window.appData
  const appDataMatch = pageHtml.match(/window\.appData\s*=\s*JSON\.parse\('(.+?)'\)/)
  if (!appDataMatch) throw new Error('Cannot find appData on music page')

  const rawJson = appDataMatch[1]
  // Decode the double-escaped JSON:
  // 1. Protect \\uXXXX (literal backslash + uXXXX) → placeholder
  // 2. Decode \u0022 etc (JS string escapes) → actual chars
  // 3. Restore placeholder → \uXXXX (for JSON.parse)
  // 4. Fix \\/ → /
  const PLACEHOLDER = '\x00UESC'
  let decoded = rawJson.replace(/\\\\u([0-9a-fA-F]{4})/g, `${PLACEHOLDER}$1`)
  decoded = decoded.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) =>
    String.fromCharCode(parseInt(hex, 16))
  )
  decoded = decoded.replace(new RegExp(PLACEHOLDER.replace('\x00', '\\x00'), 'g'), '\\u')
  decoded = decoded.replace(/\\\//g, '/')

  let appData: { play_id?: string }
  try {
    appData = JSON.parse(decoded)
  } catch {
    throw new Error('Failed to parse appData JSON')
  }

  if (!appData.play_id) throw new Error('No play_id in appData')

  // Step 2: POST to /api/play-url to get CDN URL
  const apiResult = await postPlayUrl(appData.play_id)
  if (!apiResult.url) throw new Error(apiResult.error || 'No audio URL returned')

  return apiResult.url
}

function postPlayUrl(playId: string): Promise<{ url?: string; error?: string }> {
  return new Promise((resolve, reject) => {
    const postData = `id=${encodeURIComponent(playId)}`
    const req = https.request(
      {
        hostname: 'www.fangpi.net',
        path: '/api/play-url',
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'Content-Length': Buffer.byteLength(postData),
          'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          Referer: 'https://www.fangpi.net/',
          'X-Requested-With': 'XMLHttpRequest',
        },
        timeout: 10000,
      },
      (res) => {
        const chunks: Buffer[] = []
        res.on('data', (chunk: Buffer) => chunks.push(chunk))
        res.on('end', () => {
          try {
            const body = JSON.parse(Buffer.concat(chunks).toString('utf-8'))
            if (body.code === 1 && body.data?.url) {
              resolve({ url: body.data.url })
            } else {
              resolve({ error: body.msg || 'API returned error' })
            }
          } catch {
            resolve({ error: 'Invalid API response' })
          }
        })
        res.on('error', reject)
      },
    )
    req.on('error', reject)
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('API request timeout'))
    })
    req.write(postData)
    req.end()
  })
}

/**
 * Download a song from fangpi.net to a local file.
 * Returns the local file path of the downloaded MP3.
 */
export async function downloadFangpiSong(
  musicId: string,
  title: string,
  artist: string,
  destDir: string,
): Promise<{ filePath: string; fileSize: number }> {
  const audioUrl = await getFangpiAudioUrl(musicId)

  // Sanitize filename
  const safeName = `${title} - ${artist}`.replace(/[<>:"/\\|?*]/g, '_').substring(0, 200)
  const filePath = path.join(destDir, `${safeName}.mp3`)

  // Download the file
  await downloadFile(audioUrl, filePath)

  const stats = fs.statSync(filePath)
  return { filePath, fileSize: stats.size }
}

function downloadFile(url: string, dest: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http
    const req = mod.get(
      url,
      {
        headers: {
          'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
        timeout: 60000,
      },
      (res) => {
        if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          downloadFile(res.headers.location, dest).then(resolve).catch(reject)
          return
        }
        if (res.statusCode !== 200) {
          reject(new Error(`Download failed: HTTP ${res.statusCode}`))
          return
        }
        const ws = fs.createWriteStream(dest)
        res.pipe(ws)
        ws.on('finish', () => {
          ws.close()
          resolve()
        })
        ws.on('error', (err) => {
          fs.unlink(dest, () => {})
          reject(err)
        })
        res.on('error', (err) => {
          ws.close()
          fs.unlink(dest, () => {})
          reject(err)
        })
      },
    )
    req.on('error', reject)
    req.on('timeout', () => {
      req.destroy()
      reject(new Error('Download timeout'))
    })
  })
}
