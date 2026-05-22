import { useState } from 'react'

/**
 * MixtapeBuilder
 * -------------------------------------------------------------------------
 * 把 Mixtape Standalone Frontend 的非混音功能整合进 DJ Session：
 *   方式 A：解析 / 导入歌单 URL  → /api/fangpi/parse-playlist + /api/fangpi/import-playlist
 *   方式 B：按舞种 / 风格标签推荐 → /api/fangpi/vibe-search (mode=style)
 *   方式 C：按 vibe 语义排序推荐  → /api/fangpi/vibe-search (mode=vibe)
 *   第 4 区块乐段选择 (intro/build/verse/drop/bridge/outro)
 *   加入待混音列表 → /api/fangpi/import-songs
 *   打标签接口调用 → /api/fangpi/download (附带 tags)
 *
 * 混音渲染 / 转场预览仍由下方 NewMixFeatures 负责。
 * ------------------------------------------------------------------------- */

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

type Segment = 'all' | 'intro' | 'build' | 'verse' | 'drop' | 'bridge' | 'outro'

const SEGMENTS: Segment[] = ['all', 'intro', 'build', 'verse', 'drop', 'bridge', 'outro']

const STYLE_TAGS = [
  'hiphop', 'breaking', 'popping', 'locking', 'krump',
  'waacking', 'vogue', 'house', 'urban', 'commercial',
  'jazzfunk', 'contemporary',
]

interface SearchItem {
  id?: string | number
  library_song_id?: string
  song_id?: number | null
  music_id?: string
  title: string
  artist: string
  source?: string
  tags?: string[]
  bpm?: number | null
  key?: string | null
}

interface QueueItem {
  key: string
  title: string
  artist: string
  segment: Segment
  source?: string
  library_song_id?: string
  song_id?: number | null
  music_id?: string
  tags: string[]
  extraTag: string
}

interface ParsedTrack {
  title: string
  artist: string
  duration?: number
  segment: Segment
}

function authHeaders(): Record<string, string> {
  const t = localStorage.getItem('harbeat_token')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function postJson<T>(path: string, body: any): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  const j: ApiEnvelope<T> = await r.json()
  if (j.code !== 0) throw new Error(j.message || 'request failed')
  return j.data
}

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(path, { headers: { ...authHeaders() } })
  const j: ApiEnvelope<T> = await r.json()
  if (j.code !== 0) throw new Error(j.message || 'request failed')
  return j.data
}

export default function MixtapeBuilder() {
  // ---- search state ----
  const [mode, setMode] = useState<'style' | 'vibe'>('style')
  const [tags, setTags] = useState<string[]>(['hiphop'])
  const [vibe, setVibe] = useState('')
  const [searchLoading, setSearchLoading] = useState(false)
  const [localResults, setLocalResults] = useState<SearchItem[]>([])
  const [externalResults, setExternalResults] = useState<SearchItem[]>([])

  // ---- queue ----
  const [queue, setQueue] = useState<QueueItem[]>([])
  const [playlistName, setPlaylistName] = useState('Mixtape')
  const [playlistId, setPlaylistId] = useState<number | null>(null)
  const [importLoading, setImportLoading] = useState(false)

  // ---- playlist URL import ----
  const [playlistUrl, setPlaylistUrl] = useState('')
  const [parsedTracks, setParsedTracks] = useState<ParsedTrack[]>([])
  const [parsedSelected, setParsedSelected] = useState<Set<number>>(new Set())
  const [parsePlatform, setParsePlatform] = useState('')
  const [parseLoading, setParseLoading] = useState(false)
  const [playlistImportLoading, setPlaylistImportLoading] = useState(false)
  const [importJob, setImportJob] = useState<null | {
    job_id: string
    status: string
    total: number
    done: number
    current: string
    imported: any[]
    failed: any[]
    playlist_id: number | null
    error: string | null
  }>(null)

  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const toggleTag = (tag: string) => {
    setTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]))
  }

  const doSearch = async () => {
    setSearchLoading(true); setError(''); setMessage('')
    try {
      const data = await postJson<any>('/api/fangpi/vibe-search', {
        mode,
        vibe: mode === 'vibe' ? vibe : '',
        tags: mode === 'style' ? tags : [],
        limit: 30,
      })
      setLocalResults(data.local_results || [])
      setExternalResults(data.external_results || [])
      setMessage(`本地 ${data.local_results?.length ?? 0} / 外部 ${data.external_results?.length ?? 0}`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSearchLoading(false)
    }
  }

  const addToQueue = (item: SearchItem, fromExternal = false) => {
    const key = `${fromExternal ? 'ext' : 'loc'}:${item.library_song_id ?? item.song_id ?? item.id ?? item.music_id ?? item.title}`
    setQueue((prev) => {
      if (prev.some((q) => q.key === key)) return prev
      return [...prev, {
        key,
        title: item.title,
        artist: item.artist || 'Unknown Artist',
        segment: 'all',
        source: fromExternal ? (item.source || 'fangpi') : 'local',
        library_song_id: item.library_song_id,
        song_id: item.song_id,
        music_id: fromExternal ? String(item.music_id ?? item.id ?? '') : undefined,
        tags: (item.tags ?? []).slice(0, 6),
        extraTag: '',
      }]
    })
  }

  const updateSegment = (key: string, seg: Segment) =>
    setQueue((prev) => prev.map((q) => (q.key === key ? { ...q, segment: seg } : q)))

  const removeFromQueue = (key: string) =>
    setQueue((prev) => prev.filter((q) => q.key !== key))

  const addExtraTag = (key: string) => {
    setQueue((prev) => prev.map((q) => {
      if (q.key !== key) return q
      const t = q.extraTag.trim()
      if (!t) return q
      return { ...q, tags: Array.from(new Set([...q.tags, t])), extraTag: '' }
    }))
  }

  const setExtraTag = (key: string, value: string) =>
    setQueue((prev) => prev.map((q) => (q.key === key ? { ...q, extraTag: value } : q)))

  const importQueue = async () => {
    if (queue.length === 0) return
    setImportLoading(true); setError(''); setMessage('')
    try {
      const data = await postJson<any>('/api/fangpi/import-songs', {
        playlist_id: playlistId,
        playlist_name: playlistName || 'Mixtape',
        songs: queue.map((q) => ({
          title: q.title,
          artist: q.artist,
          music_id: q.music_id,
          source: q.source === 'local' ? 'fangpi' : (q.source || 'fangpi'),
          library_song_id: q.library_song_id,
          song_id: q.song_id ?? undefined,
          segment: q.segment,
          tags: q.tags,
        })),
      })
      setPlaylistId(data.playlist_id)
      const importedIds: string[] = (data.imported || [])
        .map((it: any) => it?.library_song_id)
        .filter((x: any) => typeof x === 'string' && x)
      try {
        if (importedIds.length) {
          window.localStorage.setItem('harbeat_pending_library_ids', JSON.stringify(importedIds))
          window.dispatchEvent(new CustomEvent('harbeat:mixtape-imported', {
            detail: { playlist_id: data.playlist_id, library_song_ids: importedIds }
          }))
        }
      } catch {}
      setMessage(`导入: ${data.imported?.length ?? 0} 首, 失败 ${data.failed?.length ?? 0}; playlist=${data.playlist_id}`)
      setQueue([])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setImportLoading(false)
    }
  }

  const parsePlaylist = async () => {
    if (!playlistUrl.trim()) return
    setParseLoading(true); setError(''); setMessage('')
    try {
      const data = await postJson<any>('/api/fangpi/parse-playlist', { url: playlistUrl.trim() })
      const items: ParsedTrack[] = (data.tracks || []).map((t: any) => ({
        title: t.title, artist: t.artist, duration: t.duration, segment: 'all',
      }))
      setParsedTracks(items)
      setParsedSelected(new Set(items.map((_, i) => i)))   // 默认全选
      setParsePlatform(data.platform || '')
      setMessage(`解析 ${data.platform || '?'}: ${items.length} 首`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setParseLoading(false)
    }
  }

  const updateParsedSegment = (i: number, seg: Segment) =>
    setParsedTracks((prev) => prev.map((t, idx) => (idx === i ? { ...t, segment: seg } : t)))

  const toggleParsedSelect = (i: number) =>
    setParsedSelected((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i); else next.add(i)
      return next
    })
  const selectAllParsed = () => setParsedSelected(new Set(parsedTracks.map((_, i) => i)))
  const clearParsedSelect = () => setParsedSelected(new Set())

  const importPlaylistSelected = async (mode: 'all' | 'selected') => {
    if (!playlistUrl.trim() || parsedTracks.length === 0) return
    const indices = mode === 'all'
      ? parsedTracks.map((_, i) => i)
      : Array.from(parsedSelected).sort((a, b) => a - b)
    if (indices.length === 0) { setError('请先勾选要导入的歌曲'); return }
    setPlaylistImportLoading(true); setError(''); setMessage('')
    setImportJob({ job_id: '', status: 'starting', total: indices.length, done: 0, current: '准备中…', imported: [], failed: [], playlist_id: null, error: null })
    try {
      const start = await postJson<any>('/api/fangpi/import-playlist-start', {
        url: playlistUrl.trim(),
        playlist_id: playlistId,
        playlist_name: playlistName || 'Mixtape',
        default_segment: 'all',
        track_segments: indices.map((idx) => ({
          index: idx, title: parsedTracks[idx].title, artist: parsedTracks[idx].artist, segment: parsedTracks[idx].segment,
        })),
        limit: indices.length,
      })
      const jobId = start.job_id
      setImportJob((p) => p ? { ...p, job_id: jobId, status: 'queued' } : p)
      // Poll progress every 1s
      const poll = async () => {
        try {
          const job = await getJson<any>(`/api/fangpi/import-playlist-progress/${jobId}`)
          setImportJob(job)
          if (job.status === 'completed' || job.status === 'failed') {
            setPlaylistImportLoading(false)
            if (job.playlist_id) setPlaylistId(job.playlist_id)
            const importedIds: string[] = (job.imported || []).map((r: any) => r.library_song_id).filter(Boolean)
            if (importedIds.length >= 2) {
              try { localStorage.setItem('harbeat_pending_library_ids', JSON.stringify(importedIds)) } catch {}
              window.dispatchEvent(new CustomEvent('harbeat:mixtape-imported', {
                detail: { playlist_id: job.playlist_id, library_song_ids: importedIds },
              }))
            }
            if (job.status === 'failed') setError(`导入失败: ${job.error || 'unknown'}`)
            else setMessage(`歌单导入${mode === 'selected' ? '选中' : ''}完成: 成功 ${job.imported?.length ?? 0} / 失败 ${job.failed?.length ?? 0}`)
            return
          }
          setTimeout(poll, 1000)
        } catch (e: any) {
          setError(`轮询进度失败: ${e.message}`)
          setPlaylistImportLoading(false)
        }
      }
      poll()
    } catch (e: any) {
      setError(e.message)
      setPlaylistImportLoading(false)
      setImportJob(null)
    }
  }

  const importPlaylistUrl = () => importPlaylistSelected('all')

  return (
    <div className="street-sticker bg-surface-light p-4 sm:p-5 space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg sm:text-xl street-title">Mixtape 待混音列表</h3>
        <span className="text-xs street-subtitle text-gray-500">
          方式 A 歌单导入 · 方式 B 风格 · 方式 C vibe · 乐段 · 打标签
        </span>
      </div>

      {(message || error) && (
        <div className={`text-xs ${error ? 'text-red-400' : 'text-gray-600'}`}>
          {error || message}
        </div>
      )}

      {/* ===== 方式 B / C: 风格 + vibe 搜索 ===== */}
      <section className="space-y-2">
        <div className="text-sm street-subtitle">方式 B / C：按风格 / vibe 搜索本地库 + 外部候选</div>
        <div className="flex gap-2 flex-wrap text-xs">
          <button onClick={() => setMode('style')}
                  className={mode === 'style' ? 'bg-primary text-white px-3 py-1' : 'px-3 py-1'}>
            B 风格标签
          </button>
          <button onClick={() => setMode('vibe')}
                  className={mode === 'vibe' ? 'bg-primary text-white px-3 py-1' : 'px-3 py-1'}>
            C Vibe 语义
          </button>
        </div>

        {mode === 'style' ? (
          <div className="flex flex-wrap gap-1">
            {STYLE_TAGS.map((t) => (
              <button key={t} onClick={() => toggleTag(t)}
                      className={`text-xs px-2 py-1 ${tags.includes(t) ? 'bg-cyan-500 text-black' : 'bg-surface-lighter'}`}>
                {t}
              </button>
            ))}
          </div>
        ) : (
          <textarea value={vibe} onChange={(e) => setVibe(e.target.value)}
                    placeholder="rainy night drive, battle energy, warm old-school groove..."
                    className="w-full px-2 py-1 text-xs min-h-16" />
        )}

        <button onClick={doSearch} disabled={searchLoading}
                className="bg-primary text-white text-sm px-4 py-2">
          {searchLoading ? '搜索中…' : '🔍 搜索'}
        </button>

        <div className="grid sm:grid-cols-2 gap-2 max-h-72 overflow-auto">
          <div className="space-y-1">
            <div className="text-[11px] text-gray-500">本地 ({localResults.length})</div>
            {localResults.map((item) => (
              <div key={`loc-${item.library_song_id ?? item.id}`} className="flex items-center justify-between bg-surface-lighter p-2">
                <div className="min-w-0">
                  <div className="text-xs font-bold truncate">{item.title}</div>
                  <div className="text-[10px] text-gray-500 truncate">
                    {item.artist} · BPM {item.bpm ?? '-'} · {item.key ?? '-'}
                  </div>
                </div>
                <button onClick={() => addToQueue(item, false)} className="text-xs px-2 py-1 bg-emerald-500 text-black">＋</button>
              </div>
            ))}
          </div>
          <div className="space-y-1">
            <div className="text-[11px] text-gray-500">外部候选 ({externalResults.length})</div>
            {externalResults.map((item, idx) => (
              <div key={`ext-${item.id ?? idx}`} className="flex items-center justify-between bg-surface-lighter p-2">
                <div className="min-w-0">
                  <div className="text-xs font-bold truncate">{item.title}</div>
                  <div className="text-[10px] text-gray-500 truncate">{item.artist} · {item.source || 'fangpi'}</div>
                </div>
                <button onClick={() => addToQueue(item, true)} className="text-xs px-2 py-1 bg-amber-500 text-black">＋</button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 方式 A: 歌单 URL 解析 + 导入 ===== */}
      <section className="space-y-2">
        <div className="text-sm street-subtitle">方式 A：导入歌单 URL（网易云 / QQ 音乐）</div>
        <div className="flex gap-2 flex-wrap">
          <input value={playlistUrl} onChange={(e) => setPlaylistUrl(e.target.value)}
                 placeholder="https://music.163.com/playlist?id=..."
                 className="flex-1 min-w-0 px-2 py-1 text-xs" />
          <button onClick={parsePlaylist} disabled={parseLoading}
                  className="text-xs px-3 py-1 bg-cyan-500 text-black">
            {parseLoading ? '解析中…' : '解析'}
          </button>
          <button onClick={() => importPlaylistSelected('selected')}
                  disabled={playlistImportLoading || parsedSelected.size === 0}
                  className="text-xs px-3 py-1 bg-amber-500 text-black">
            {playlistImportLoading ? '导入中…' : `导入选中 (${parsedSelected.size})`}
          </button>
          <button onClick={importPlaylistUrl} disabled={playlistImportLoading || parsedTracks.length === 0}
                  className="text-xs px-3 py-1 bg-emerald-500 text-black">
            {playlistImportLoading ? '导入中…' : '一键全导入'}
          </button>
        </div>
        {parsePlatform && (
          <div className="flex items-center gap-2 text-[10px] text-gray-500">
            <span>{parsePlatform} · {parsedTracks.length} 首 · 选中 {parsedSelected.size}</span>
            <button onClick={selectAllParsed} className="px-2 py-0.5 bg-surface-lighter">全选</button>
            <button onClick={clearParsedSelect} className="px-2 py-0.5 bg-surface-lighter">清空</button>
          </div>
        )}
        {importJob && (
          <div className="bg-surface-lighter p-2 space-y-1">
            <div className="flex justify-between text-[11px]">
              <span>
                {importJob.status === 'queued' && '⏳ 排队中…'}
                {importJob.status === 'starting' && '⏳ 启动中…'}
                {importJob.status === 'running' && `⏬ 导入中 ${importJob.done}/${importJob.total}`}
                {importJob.status === 'completed' && `✔ 完成 ${importJob.done}/${importJob.total}`}
                {importJob.status === 'failed' && `✗ 失败: ${importJob.error}`}
              </span>
              {(importJob.status === 'completed' || importJob.status === 'failed') && (
                <button onClick={() => setImportJob(null)} className="text-[10px] px-2 bg-surface-light">关闭</button>
              )}
            </div>
            <div className="h-1.5 bg-gray-700 rounded overflow-hidden">
              <div
                className={`h-full transition-all ${importJob.status === 'failed' ? 'bg-red-500' : 'bg-emerald-500'}`}
                style={{ width: `${importJob.total ? Math.round((importJob.done / importJob.total) * 100) : 0}%` }}
              />
            </div>
            {importJob.current && <div className="text-[10px] text-gray-500 truncate">当前: {importJob.current}</div>}
            {importJob.failed.length > 0 && (
              <div className="text-[10px] text-red-400">
                失败 {importJob.failed.length} 首: {importJob.failed.slice(0, 3).map((f: any) => f.title).join(', ')}{importJob.failed.length > 3 ? '…' : ''}
              </div>
            )}
          </div>
        )}
        <div className="max-h-40 overflow-auto space-y-1">
          {parsedTracks.map((t, i) => (
            <div key={i} className="flex items-center justify-between bg-surface-lighter p-2 gap-2">
              <input type="checkbox"
                     checked={parsedSelected.has(i)}
                     onChange={() => toggleParsedSelect(i)}
                     className="shrink-0" />
              <div className="min-w-0 text-[11px] flex-1">
                <div className="truncate font-bold">{i + 1}. {t.title}</div>
                <div className="text-gray-500 truncate">{t.artist}</div>
              </div>
              <select value={t.segment} onChange={(e) => updateParsedSegment(i, e.target.value as Segment)}
                      className="text-[11px] px-1 py-1">
                {SEGMENTS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          ))}
        </div>
      </section>

      {/* ===== 待混音列表 + 乐段选择 + 打标签 ===== */}
      <section className="space-y-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="text-sm street-subtitle">待混音列表（{queue.length}）</div>
          <div className="flex gap-2 items-center text-xs">
            <input value={playlistName} onChange={(e) => setPlaylistName(e.target.value)}
                   placeholder="歌单名"
                   className="px-2 py-1 w-32" />
            {playlistId && <span className="text-gray-500">playlist_id={playlistId}</span>}
            <button onClick={importQueue} disabled={importLoading || queue.length === 0}
                    className="bg-emerald-500 text-black px-3 py-1">
              {importLoading ? '导入中…' : '✓ 加入歌单'}
            </button>
          </div>
        </div>
        <div className="space-y-1 max-h-60 overflow-auto">
          {queue.map((q) => (
            <div key={q.key} className="bg-surface-lighter p-2 space-y-1">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="min-w-0 text-xs flex-1">
                  <div className="font-bold truncate">{q.title}</div>
                  <div className="text-gray-500 truncate">{q.artist} · {q.source}</div>
                </div>
                <select value={q.segment} onChange={(e) => updateSegment(q.key, e.target.value as Segment)}
                        className="text-[11px] px-1 py-1">
                  {SEGMENTS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
                <button onClick={() => removeFromQueue(q.key)} className="text-[10px] px-2 py-1">✕</button>
              </div>
              <div className="flex flex-wrap gap-1 items-center">
                {q.tags.map((t) => <span key={t} className="text-[10px] bg-fuchsia-500/30 px-2 py-0.5">{t}</span>)}
                <input value={q.extraTag} onChange={(e) => setExtraTag(q.key, e.target.value)}
                       onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addExtraTag(q.key) } }}
                       placeholder="新标签"
                       className="text-[10px] px-2 py-0.5 w-24" />
                <button onClick={() => addExtraTag(q.key)} className="text-[10px] px-2 py-0.5">＋</button>
              </div>
            </div>
          ))}
          {queue.length === 0 && (
            <div className="text-xs text-gray-500">从上方搜索结果或歌单解析中点击 ＋ 加入待混音。</div>
          )}
        </div>
        <p className="text-[10px] text-gray-500">
          每首可独立选择乐段（intro / build / verse / drop / bridge / outro），同时可为该曲追加标签，
          标签会随 <code>/api/fangpi/import-songs</code> 写入歌单。
        </p>
      </section>
    </div>
  )
}
