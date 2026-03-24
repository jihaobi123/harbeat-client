import https from 'node:https'
import http from 'node:http'

export interface PlaylistTrack {
  title: string
  artist: string
  album: string
  duration: number // seconds, 0 if unknown
}

export interface ParsedPlaylist {
  name: string
  platform: 'netease' | 'qqmusic' | 'unknown'
  tracks: PlaylistTrack[]
}

// ===== URL 识别 =====

/**
 * 从用户粘贴的文本中提取歌单 URL 和平台信息
 * 支持格式:
 *   - https://music.163.com/playlist?id=xxx  (网易云)
 *   - https://music.163.com/m/playlist?id=xxx (网易云移动端)
 *   - https://music.163.com/#/playlist?id=xxx (网易云 hash 路由)
 *   - https://y.qq.com/n/ryqq/playlist/xxx    (QQ音乐)
 *   - https://c6.y.qq.com/...                  (QQ音乐短链)
 *   - https://i.y.qq.com/...                   (QQ音乐分享)
 */
export function detectPlatform(text: string): { platform: 'netease' | 'qqmusic' | 'unknown'; playlistId: string } {
  // 网易云音乐
  const neteaseMatch = text.match(/music\.163\.com.*[?&#]id=(\d+)/)
  if (neteaseMatch) {
    return { platform: 'netease', playlistId: neteaseMatch[1] }
  }

  // QQ音乐 — 标准链接 y.qq.com/n/ryqq/playlist/123
  const qqStdMatch = text.match(/y\.qq\.com\/n\/ryqq\/playlist\/(\d+)/)
  if (qqStdMatch) {
    return { platform: 'qqmusic', playlistId: qqStdMatch[1] }
  }

  // QQ音乐 — 移动端分享链接 i.y.qq.com/n2/m/share/details/taoge.html?id=123
  const qqMobileMatch = text.match(/y\.qq\.com\/[^\s]*[?&]id=(\d+)/)
  if (qqMobileMatch) {
    return { platform: 'qqmusic', playlistId: qqMobileMatch[1] }
  }

  // QQ音乐 — 短链 (c.y.qq.com, c6.y.qq.com 等) 需要跟踪重定向
  const qqShortMatch = text.match(/https?:\/\/[a-z0-9.]*y\.qq\.com\/[^\s)"'<>]+/)
  if (qqShortMatch) {
    return { platform: 'qqmusic', playlistId: qqShortMatch[0] }
  }

  return { platform: 'unknown', playlistId: '' }
}

// ===== 通用 HTTP 请求 =====

function fetchUrl(url: string, options: { headers?: Record<string, string> } = {}): Promise<string> {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http
    const req = mod.get(
      url,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
          'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
          ...options.headers,
        },
        timeout: 15000,
      },
      (res) => {
        if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          fetchUrl(res.headers.location, options).then(resolve).catch(reject)
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
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')) })
  })
}

function postJson(url: string, body: any, extraHeaders?: Record<string, string>): Promise<any> {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body)
    const parsed = new URL(url)
    const mod = parsed.protocol === 'https:' ? https : http
    const req = mod.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname + parsed.search,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(data),
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Referer': `${parsed.protocol}//${parsed.hostname}`,
          ...extraHeaders,
        },
        timeout: 15000,
      },
      (res) => {
        const chunks: Buffer[] = []
        res.on('data', (chunk: Buffer) => chunks.push(chunk))
        res.on('end', () => {
          try {
            resolve(JSON.parse(Buffer.concat(chunks).toString('utf-8')))
          } catch {
            reject(new Error('Invalid JSON response'))
          }
        })
        res.on('error', reject)
      },
    )
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('Request timeout')) })
    req.write(data)
    req.end()
  })
}

// ===== 网易云音乐 =====

async function fetchNeteasePlaylist(playlistId: string): Promise<ParsedPlaylist> {
  console.log('[playlist] Fetching NetEase playlist:', playlistId)

  // 使用网易云音乐 API v3 (无需登录即可获取歌单基本信息)
  const apiUrl = `https://music.163.com/api/v3/playlist/detail?id=${playlistId}&n=5000`
  const html = await fetchUrl(apiUrl, {
    headers: {
      'Referer': 'https://music.163.com/',
      'Cookie': 'appver=2.9.7; os=pc;',
    },
  })

  let data: any
  try {
    data = JSON.parse(html)
  } catch {
    throw new Error('网易云歌单解析失败，请检查链接是否正确')
  }

  if (data.code !== 200 || !data.playlist) {
    throw new Error(data.message || '获取网易云歌单失败，歌单可能不存在或为私密歌单')
  }

  const playlist = data.playlist
  const tracks: PlaylistTrack[] = (playlist.tracks || []).map((t: any) => ({
    title: t.name || '',
    artist: (t.ar || []).map((a: any) => a.name).join(' / ') || '未知',
    album: t.al?.name || '',
    duration: Math.round((t.dt || 0) / 1000),
  }))

  // 如果 tracks 为空但 trackIds 不为空，说明详情被截断，尝试用 trackIds 获取
  if (tracks.length === 0 && playlist.trackIds?.length > 0) {
    const ids = playlist.trackIds.map((t: any) => t.id).slice(0, 500)
    const detailData = await postJson('https://music.163.com/api/v3/song/detail', {
      c: JSON.stringify(ids.map((id: number) => ({ id }))),
    })
    if (detailData.songs) {
      for (const t of detailData.songs) {
        tracks.push({
          title: t.name || '',
          artist: (t.ar || []).map((a: any) => a.name).join(' / ') || '未知',
          album: t.al?.name || '',
          duration: Math.round((t.dt || 0) / 1000),
        })
      }
    }
  }

  console.log('[playlist] NetEase:', playlist.name, '→', tracks.length, 'tracks')

  return {
    name: playlist.name || '未知歌单',
    platform: 'netease',
    tracks,
  }
}

// ===== QQ音乐 =====

async function resolveQQMusicPlaylistId(input: string): Promise<string> {
  // 如果已经是纯数字 id，直接返回
  if (/^\d+$/.test(input)) return input

  console.log('[playlist] Resolving QQ Music short link:', input)

  // 先从 input URL 自身尝试提取 id
  const selfIdMatch = input.match(/[?&]id=(\d+)/)
  if (selfIdMatch) {
    console.log('[playlist] Found ID in input URL:', selfIdMatch[1])
    return selfIdMatch[1]
  }

  // 对短链做 HTTP 请求，手动跟踪重定向并检查每一跳的 URL
  try {
    const resolvedId = await followRedirectsForId(input, 5)
    if (resolvedId) {
      console.log('[playlist] Resolved QQ playlist ID from redirect chain:', resolvedId)
      return resolvedId
    }
  } catch (e) {
    console.log('[playlist] Short link resolve failed:', e)
  }

  throw new Error('无法解析 QQ音乐歌单链接，请尝试打开链接后复制浏览器地址栏中的完整地址')
}

/** 跟踪重定向链，从每一跳的 Location URL 和最终页面内容中提取歌单 ID */
function followRedirectsForId(url: string, maxRedirects: number): Promise<string | null> {
  return new Promise((resolve, reject) => {
    const mod = url.startsWith('https') ? https : http
    const req = mod.get(
      url,
      {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'zh-CN,zh;q=0.9',
        },
        timeout: 15000,
      },
      (res) => {
        // 检查重定向
        if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          const location = res.headers.location
          console.log('[playlist] Redirect →', location)

          // 尝试从 Location URL 中提取 id
          const idMatch = location.match(/[?&]id=(\d+)/)
          if (idMatch) {
            res.resume() // drain the response
            resolve(idMatch[1])
            return
          }
          // 从路径中提取 (如 /n/ryqq/playlist/12345)
          const pathMatch = location.match(/playlist\/(\d+)/)
          if (pathMatch) {
            res.resume()
            resolve(pathMatch[1])
            return
          }

          if (maxRedirects <= 0) {
            res.resume()
            resolve(null)
            return
          }
          res.resume()
          followRedirectsForId(location, maxRedirects - 1).then(resolve).catch(reject)
          return
        }

        // 最终页面 — 从 HTML 内容中提取
        const chunks: Buffer[] = []
        res.on('data', (chunk: Buffer) => chunks.push(chunk))
        res.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf-8')
          const patterns = [
            /disstid[=:]["'\s]*(\d+)/,
            /[?&]id=(\d+)/,
            /playlist[/"'](\d+)/,
            /"dissid"\s*:\s*(\d+)/,
          ]
          for (const p of patterns) {
            const m = body.match(p)
            if (m) { resolve(m[1]); return }
          }
          resolve(null)
        })
        res.on('error', reject)
      },
    )
    req.on('error', reject)
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')) })
  })
}

async function fetchQQMusicPlaylist(playlistIdOrUrl: string): Promise<ParsedPlaylist> {
  console.log('[playlist] Fetching QQ Music playlist:', playlistIdOrUrl)

  const playlistId = await resolveQQMusicPlaylistId(playlistIdOrUrl)
  console.log('[playlist] Resolved ID:', playlistId)
  const numericId = parseInt(playlistId, 10)
  if (isNaN(numericId)) {
    throw new Error('QQ音乐歌单 ID 无效: ' + playlistId)
  }

  // 使用新版 QQ音乐 API (u.y.qq.com/cgi-bin/musicu.fcg)
  const reqBody = {
    comm: {
      cv: 4747474, ct: 24, format: 'json',
      inCharset: 'utf-8', outCharset: 'utf-8',
      notice: 0, platform: 'yqq.json', needNewCode: 1, uin: 0,
    },
    req_0: {
      module: 'srf_diss_info.DissInfoServer',
      method: 'CgiGetDiss',
      param: { disstid: numericId, onlysonglist: 0, song_begin: 0, song_num: 500 },
    },
  }

  const data = await postJson('https://u.y.qq.com/cgi-bin/musicu.fcg', reqBody, {
    'Referer': 'https://y.qq.com/',
    'Origin': 'https://y.qq.com',
  })

  console.log('[playlist] QQ API response code:', data?.code, 'req_0.code:', data?.req_0?.code)
  const reqData = data?.req_0?.data
  console.log('[playlist] QQ API songlist length:', reqData?.songlist?.length, 'title:', reqData?.dirinfo?.title)

  if (!reqData || data.req_0?.code !== 0) {
    // 降级到旧 API 尝试
    console.log('[playlist] New API failed, trying legacy API...')
    return fetchQQMusicPlaylistLegacy(playlistId)
  }

  const dirinfo = reqData.dirinfo || {}
  const songlist = reqData.songlist || []

  const tracks: PlaylistTrack[] = songlist.map((t: any) => ({
    title: t.name || t.title || '',
    artist: (t.singer || []).map((s: any) => s.name).join(' / ') || '未知',
    album: t.album?.name || '',
    duration: t.interval || 0,
  }))

  console.log('[playlist] QQ Music:', dirinfo.title, '→', tracks.length, 'tracks')

  return {
    name: dirinfo.title || '未知歌单',
    platform: 'qqmusic',
    tracks,
  }
}

// 旧版 API 作为降级备选
async function fetchQQMusicPlaylistLegacy(playlistId: string): Promise<ParsedPlaylist> {
  const apiUrl = `https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg?type=1&json=1&utf8=1&onlysong=0&disstid=${playlistId}&format=json&platform=h5&needNewCode=1`
  const json = await fetchUrl(apiUrl, {
    headers: { 'Referer': 'https://y.qq.com/' },
  })

  let data: any
  try {
    data = JSON.parse(json)
  } catch {
    throw new Error('QQ音乐歌单解析失败，请检查链接是否正确')
  }

  const cdlist = data.cdlist?.[0]
  if (!cdlist) {
    throw new Error('获取 QQ音乐歌单失败，歌单可能不存在或为私密歌单')
  }

  const tracks: PlaylistTrack[] = (cdlist.songlist || []).map((t: any) => ({
    title: t.songname || t.name || '',
    artist: (t.singer || []).map((s: any) => s.name).join(' / ') || '未知',
    album: t.albumname || '',
    duration: t.interval || 0,
  }))

  return {
    name: cdlist.dissname || '未知歌单',
    platform: 'qqmusic',
    tracks,
  }
}

// ===== 统一解析入口 =====

export async function parsePlaylistUrl(text: string): Promise<ParsedPlaylist> {
  const { platform, playlistId } = detectPlatform(text)
  console.log('[playlist] detectPlatform:', platform, playlistId)

  if (platform === 'unknown' || !playlistId) {
    throw new Error('不支持的歌单链接格式。\n目前支持：网易云音乐、QQ音乐的歌单分享链接')
  }

  if (platform === 'netease') {
    return fetchNeteasePlaylist(playlistId)
  }

  if (platform === 'qqmusic') {
    return fetchQQMusicPlaylist(playlistId)
  }

  throw new Error('未知平台')
}
