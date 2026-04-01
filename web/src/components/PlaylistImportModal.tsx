import { useState } from 'react'
import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import { DANCE_STYLES, DANCE_STYLE_LABELS, DANCE_STYLE_COLORS } from '../types'
import type { DanceStyle } from '../types'
import * as api from '../api/client'

interface Props {
  onClose: () => void
}

interface TrackItem {
  key: string
  title: string
  artist: string
  album: string
  duration: number
  selected: boolean
  fangpiId: string | null
  fangpiTitle: string | null
  fangpiArtist: string | null
  fangpiSource: string | null
  searchStatus: 'pending' | 'found' | 'not-found'
  tags: DanceStyle[]
  energy: string[]
  scenes: string[]
  downloadStatus: 'pending' | 'downloading' | 'done' | 'failed'
}

type Stage = 'parse' | 'select' | 'search' | 'tag' | 'downloading' | 'done'

export default function PlaylistImportModal({ onClose }: Props) {
  const { user } = useAuthStore()
  const { loadSongs, loadPlaylists } = useMusicStore()

  const [stage, setStage] = useState<Stage>('parse')
  const [playlistName, setPlaylistName] = useState('')
  const [linkText, setLinkText] = useState('')
  const [tracks, setTracks] = useState<TrackItem[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState({ current: 0, total: 0, label: '' })

  const handleParse = async () => {
    if (!linkText.trim()) return
    setBusy(true)
    setError('')
    try {
      const result = await api.parsePlaylistUrl(linkText.trim())
      if (result.tracks.length === 0) throw new Error('歌单为空或解析失败')
      if (!playlistName.trim()) setPlaylistName(result.name)
      setTracks(result.tracks.map((t, i) => ({
        key: `${i}-${t.title}`,
        title: t.title,
        artist: t.artist,
        album: t.album,
        duration: t.duration,
        selected: true,
        fangpiId: null,
        fangpiTitle: null,
        fangpiArtist: null,
        fangpiSource: null,
        searchStatus: 'pending' as const,
        tags: [],
        energy: [],
        scenes: [],
        downloadStatus: 'pending' as const,
      })))
      setStage('select')
    } catch (e: any) {
      setError(e.message || '解析失败')
    } finally {
      setBusy(false)
    }
  }

  const toggleTrack = (key: string) => {
    setTracks(prev => prev.map(t => t.key === key ? { ...t, selected: !t.selected } : t))
  }
  const toggleAll = (val: boolean) => {
    setTracks(prev => prev.map(t => ({ ...t, selected: val })))
  }

  const handleBatchSearch = async () => {
    const selected = tracks.filter(t => t.selected)
    if (selected.length === 0) { setError('请至少选择一首歌曲'); return }
    if (!playlistName.trim()) { setError('请输入歌单名称'); return }
    setStage('search')
    setBusy(true)
    setError('')
    setProgress({ current: 0, total: selected.length, label: '正在搜索歌曲资源...' })

    try {
      const result = await api.batchSearchFangpi(
        selected.map(t => ({ title: t.title, artist: t.artist }))
      )
      setTracks(prev => {
        const updated = [...prev]
        let resultIdx = 0
        for (let i = 0; i < updated.length; i++) {
          if (!updated[i].selected) continue
          const r = result.results[resultIdx]
          resultIdx++
          if (r && r.found && r.candidates.length > 0) {
            const best = r.candidates[0]
            updated[i] = { ...updated[i], fangpiId: best.id, fangpiTitle: best.title, fangpiArtist: best.artist, fangpiSource: best.source || 'fangpi', searchStatus: 'found' }
          } else {
            updated[i] = { ...updated[i], searchStatus: 'not-found' }
          }
        }
        return updated
      })
      setStage('tag')
    } catch (e: any) {
      setError(e.message || '搜索失败')
      setStage('select')
    } finally {
      setBusy(false)
    }
  }

  const toggleTag = (key: string, tag: DanceStyle) => {
    setTracks(prev => prev.map(t => {
      if (t.key !== key) return t
      const tags = t.tags.includes(tag) ? t.tags.filter(x => x !== tag) : [...t.tags, tag]
      return { ...t, tags }
    }))
  }

  const toggleEnergy = (key: string, val: string) => {
    setTracks(prev => prev.map(t => {
      if (t.key !== key) return t
      const energy = t.energy.includes(val) ? t.energy.filter(x => x !== val) : [...t.energy, val]
      return { ...t, energy }
    }))
  }

  const toggleScene = (key: string, val: string) => {
    setTracks(prev => prev.map(t => {
      if (t.key !== key) return t
      const scenes = t.scenes.includes(val) ? t.scenes.filter(x => x !== val) : [...t.scenes, val]
      return { ...t, scenes }
    }))
  }

  const applyTagToAll = (tag: DanceStyle) => {
    setTracks(prev => prev.map(t => {
      if (!t.selected || t.searchStatus !== 'found') return t
      const tags = t.tags.includes(tag) ? t.tags.filter(x => x !== tag) : [...t.tags, tag]
      return { ...t, tags }
    }))
  }

  const applyEnergyToAll = (val: string) => {
    setTracks(prev => prev.map(t => {
      if (!t.selected || t.searchStatus !== 'found') return t
      const energy = t.energy.includes(val) ? t.energy.filter(x => x !== val) : [...t.energy, val]
      return { ...t, energy }
    }))
  }

  const applySceneToAll = (val: string) => {
    setTracks(prev => prev.map(t => {
      if (!t.selected || t.searchStatus !== 'found') return t
      const scenes = t.scenes.includes(val) ? t.scenes.filter(x => x !== val) : [...t.scenes, val]
      return { ...t, scenes }
    }))
  }

  const handleDownloadAndSave = async () => {
    if (!user) return
    const foundTracks = tracks.filter(t => t.selected && t.searchStatus === 'found' && t.fangpiId)
    if (foundTracks.length === 0) { setError('没有可下载的歌曲'); return }

    setStage('downloading')
    setProgress({ current: 0, total: foundTracks.length, label: '' })

    const failed: string[] = []
    const succeeded: TrackItem[] = []
    for (let i = 0; i < foundTracks.length; i++) {
      const t = foundTracks[i]
      setProgress({ current: i + 1, total: foundTracks.length, label: `${t.title} - ${t.artist}` })
      setTracks(prev => prev.map(x => x.key === t.key ? { ...x, downloadStatus: 'downloading' } : x))
      try {
        const tagData = (t.tags.length || t.energy.length || t.scenes.length)
          ? { tags: t.tags as string[], energy: t.energy, scenes: t.scenes }
          : undefined
        await api.downloadFangpi(t.fangpiId!, t.title, t.artist, tagData, t.fangpiSource || undefined)
        setTracks(prev => prev.map(x => x.key === t.key ? { ...x, downloadStatus: 'done' } : x))
        succeeded.push(t)
      } catch {
        failed.push(t.title)
        setTracks(prev => prev.map(x => x.key === t.key ? { ...x, downloadStatus: 'failed' } : x))
      }
    }

    await loadSongs()
    // Only add successfully downloaded songs to the playlist
    if (succeeded.length > 0) {
      try {
        await useMusicStore.getState().importPlaylistFromSongs(
          user.id,
          playlistName.trim(),
          succeeded.map(item => ({ title: item.title, artist: item.artist, duration: item.duration, tags: item.tags }))
        )
      } catch { /* playlist creation failed but downloads done */ }
    }
    if (user) loadPlaylists(user.id)
    setStage('done')
    setError(failed.length > 0 ? `以下歌曲下载失败: ${failed.join(', ')}` : '')
  }

  const selectedCount = tracks.filter(t => t.selected).length
  const foundCount = tracks.filter(t => t.selected && t.searchStatus === 'found').length
  const notFoundCount = tracks.filter(t => t.selected && t.searchStatus === 'not-found').length

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-surface-light rounded-2xl w-full max-w-[800px] mx-4 max-h-[85vh] flex flex-col shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            <span className="text-lg">📋</span>
            <h2 className="text-base font-semibold text-white">
              {stage === 'parse' && '导入歌单'}
              {stage === 'select' && '选择歌曲'}
              {stage === 'search' && '搜索音源中...'}
              {stage === 'tag' && '设置标签并下载'}
              {stage === 'downloading' && '下载中...'}
              {stage === 'done' && '导入完成'}
            </h2>
          </div>
          <div className="flex items-center gap-1.5">
            {['解析', '选曲', '标签', '下载'].map((label, i) => (
              <div key={label} className="flex items-center gap-1">
                <div className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-medium transition ${
                  i <= ['parse', 'select', 'tag', 'downloading', 'done'].indexOf(stage) ? 'bg-primary text-white' : 'bg-gray-700 text-gray-500'
                }`}>{i + 1}</div>
                <span className={`text-[10px] ${i <= ['parse', 'select', 'tag', 'downloading', 'done'].indexOf(stage) ? 'text-gray-300' : 'text-gray-600'}`}>{label}</span>
                {i < 3 && <span className="text-gray-700 mx-0.5">›</span>}
              </div>
            ))}
            <button onClick={onClose} className="text-gray-500 hover:text-white text-xl ml-3 transition">×</button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto min-h-0">
          {stage === 'parse' && (
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1.5">歌单名称</label>
                <input type="text" placeholder="自动从链接获取，或手动输入" value={playlistName}
                  onChange={e => setPlaylistName(e.target.value)}
                  className="w-full bg-surface rounded-lg px-4 py-2 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm" />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1.5">歌单链接</label>
                <div className="flex gap-2">
                  <input value={linkText} onChange={e => setLinkText(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleParse()}
                    placeholder="粘贴网易云音乐 / QQ音乐歌单链接..."
                    className="flex-1 bg-surface rounded-lg px-3 py-2.5 text-white border border-gray-600 focus:border-primary focus:outline-none text-sm" />
                  <button onClick={handleParse} disabled={busy || !linkText.trim()}
                    className="bg-cyan-600 hover:bg-cyan-700 disabled:opacity-40 text-white px-5 py-2.5 rounded-lg text-sm transition whitespace-nowrap">
                    {busy ? '解析中...' : '解析歌单'}
                  </button>
                </div>
                <p className="text-xs text-gray-600 mt-1.5">支持：music.163.com / y.qq.com 歌单链接</p>
              </div>
            </div>
          )}

          {stage === 'select' && (
            <div className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm text-gray-300">
                  共 <span className="text-white font-medium">{tracks.length}</span> 首，
                  已选 <span className="text-primary font-medium">{selectedCount}</span> 首
                </p>
                <div className="flex gap-2">
                  <button onClick={() => toggleAll(true)} className="text-xs text-gray-400 hover:text-white transition">全选</button>
                  <button onClick={() => toggleAll(false)} className="text-xs text-gray-400 hover:text-white transition">全不选</button>
                </div>
              </div>
              <div className="max-h-[50vh] overflow-y-auto border border-gray-700 rounded-lg divide-y divide-gray-700/50">
                {tracks.map((t, idx) => (
                  <label key={t.key} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-lighter cursor-pointer transition">
                    <input type="checkbox" checked={t.selected} onChange={() => toggleTrack(t.key)} className="accent-primary w-4 h-4" />
                    <span className="text-xs text-gray-600 w-6">{idx + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white truncate">{t.title}</p>
                      <p className="text-xs text-gray-500 truncate">{t.artist}{t.album ? ` · ${t.album}` : ''}</p>
                    </div>
                    {t.duration > 0 && (
                      <span className="text-xs text-gray-600 tabular-nums">{Math.floor(t.duration / 60)}:{String(t.duration % 60).padStart(2, '0')}</span>
                    )}
                  </label>
                ))}
              </div>
            </div>
          )}

          {stage === 'search' && (
            <div className="px-8 py-16 flex flex-col items-center">
              <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin mb-4" />
              <p className="text-white">正在搜索 fangpi.net 音源...</p>
              <p className="text-xs text-gray-500 mt-2">共 {progress.total} 首歌曲，请耐心等待</p>
            </div>
          )}

          {stage === 'tag' && (
            <div className="p-5 space-y-3">
              <div className="flex gap-3">
                <div className="bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2 text-xs text-green-400 flex-1">
                  ✅ 找到音源: {foundCount} 首
                </div>
                {notFoundCount > 0 && (
                  <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg px-3 py-2 text-xs text-yellow-400 flex-1">
                    ⚠️ 未找到: {notFoundCount} 首
                  </div>
                )}
              </div>

              {/* Batch apply */}
              <div className="bg-surface rounded-lg p-3 space-y-2">
                <p className="text-xs text-gray-500 mb-1">批量设置（应用到所有已找到音源的歌曲）</p>
                <div>
                  <span className="text-[10px] text-gray-600 mr-2">舞种:</span>
                  <span className="inline-flex flex-wrap gap-1">
                    {DANCE_STYLES.map(style => (
                      <button key={style} onClick={() => applyTagToAll(style)}
                        className="px-2 py-0.5 rounded text-[10px] transition border"
                        style={{ borderColor: DANCE_STYLE_COLORS[style] + '60', color: DANCE_STYLE_COLORS[style] }}>
                        {DANCE_STYLE_LABELS[style]}
                      </button>
                    ))}
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-gray-600 mr-2">能量:</span>
                  {['low', 'medium', 'high'].map(v => (
                    <button key={v} onClick={() => applyEnergyToAll(v)}
                      className="px-2 py-0.5 rounded text-[10px] border border-gray-600 text-gray-400 hover:text-primary hover:border-primary transition mr-1">
                      {v === 'low' ? '🔋低' : v === 'medium' ? '⚡中' : '🔥高'}
                    </button>
                  ))}
                </div>
                <div>
                  <span className="text-[10px] text-gray-600 mr-2">场景:</span>
                  {[{v:'freeplay',l:'🎧自由'},{v:'cypher',l:'🔄Cypher'},{v:'battle',l:'⚔️Battle'},{v:'showcase',l:'🎭Showcase'},{v:'training',l:'📚训练'}].map(({v,l}) => (
                    <button key={v} onClick={() => applySceneToAll(v)}
                      className="px-2 py-0.5 rounded text-[10px] border border-gray-600 text-gray-400 hover:text-primary hover:border-primary transition mr-1">
                      {l}
                    </button>
                  ))}
                </div>
              </div>

              {/* Per-song tags */}
              <div className="max-h-[40vh] overflow-y-auto space-y-2">
                {tracks.filter(t => t.selected).map(t => (
                  <div key={t.key} className={`rounded-lg p-3 ${t.searchStatus === 'found' ? 'bg-surface' : 'bg-surface opacity-60'}`}>
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${t.searchStatus === 'found' ? 'bg-green-400' : 'bg-yellow-400'}`} />
                      <span className="text-sm text-white truncate">{t.title}</span>
                      <span className="text-xs text-gray-500">- {t.artist}</span>
                      {t.searchStatus === 'not-found' && <span className="text-xs text-yellow-500 ml-auto">未找到音源</span>}
                    </div>
                    {t.searchStatus === 'found' && (
                      <div className="space-y-1.5 mt-1">
                        {/* Dance style */}
                        <div className="flex flex-wrap gap-1">
                          {DANCE_STYLES.map(style => (
                            <button key={style} onClick={() => toggleTag(t.key, style)}
                              className="px-2 py-0.5 rounded text-[10px] transition"
                              style={{
                                backgroundColor: t.tags.includes(style) ? DANCE_STYLE_COLORS[style] + '30' : 'transparent',
                                color: t.tags.includes(style) ? DANCE_STYLE_COLORS[style] : '#6b7280',
                                border: `1px solid ${t.tags.includes(style) ? DANCE_STYLE_COLORS[style] : '#374151'}`,
                              }}>
                              {DANCE_STYLE_LABELS[style]}
                            </button>
                          ))}
                        </div>
                        {/* Energy */}
                        <div className="flex items-center gap-1">
                          <span className="text-[10px] text-gray-600 mr-1">能量:</span>
                          {['low', 'medium', 'high'].map(v => (
                            <button key={v} onClick={() => toggleEnergy(t.key, v)}
                              className={`px-2 py-0.5 rounded text-[10px] transition border ${
                                t.energy.includes(v) ? 'bg-primary/20 text-primary border-primary' : 'border-gray-700 text-gray-500'
                              }`}>
                              {v === 'low' ? '🔋低' : v === 'medium' ? '⚡中' : '🔥高'}
                            </button>
                          ))}
                        </div>
                        {/* Scene */}
                        <div className="flex items-center flex-wrap gap-1">
                          <span className="text-[10px] text-gray-600 mr-1">场景:</span>
                          {[{v:'freeplay',l:'🎧自由'},{v:'cypher',l:'🔄Cypher'},{v:'battle',l:'⚔️Battle'},{v:'showcase',l:'🎭Showcase'},{v:'training',l:'📚训练'}].map(({v,l}) => (
                            <button key={v} onClick={() => toggleScene(t.key, v)}
                              className={`px-2 py-0.5 rounded text-[10px] transition border ${
                                t.scenes.includes(v) ? 'bg-primary/20 text-primary border-primary' : 'border-gray-700 text-gray-500'
                              }`}>
                              {l}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {stage === 'downloading' && (
            <div className="p-5 space-y-3">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                <p className="text-white text-sm">下载中 {progress.current}/{progress.total}</p>
              </div>
              <p className="text-xs text-gray-400 truncate">{progress.label}</p>
              <div className="w-full h-2 bg-surface rounded-full overflow-hidden">
                <div className="h-full bg-primary rounded-full transition-all"
                  style={{ width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%` }} />
              </div>
              <div className="max-h-[40vh] overflow-y-auto space-y-1 mt-3">
                {tracks.filter(t => t.selected && t.searchStatus === 'found').map(t => (
                  <div key={t.key} className="flex items-center gap-2 px-3 py-1.5 text-xs">
                    {t.downloadStatus === 'done' && <span className="text-green-400">✓</span>}
                    {t.downloadStatus === 'downloading' && <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />}
                    {t.downloadStatus === 'failed' && <span className="text-red-400">✕</span>}
                    {t.downloadStatus === 'pending' && <span className="text-gray-600">○</span>}
                    <span className="text-gray-300 truncate">{t.title} - {t.artist}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {stage === 'done' && (
            <div className="px-8 py-12 flex flex-col items-center">
              <div className="text-4xl mb-4">✅</div>
              <p className="text-lg text-white font-medium mb-2">导入完成！</p>
              <p className="text-sm text-gray-400">歌单「{playlistName}」已创建</p>
              {error && <p className="text-xs text-yellow-400 mt-3 text-center max-w-md">{error}</p>}
            </div>
          )}
        </div>

        {error && stage !== 'done' && <div className="px-5 pb-2 text-sm text-red-400">{error}</div>}

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-700 flex justify-between">
          {stage === 'parse' && <><span /><button onClick={onClose} className="text-gray-400 hover:text-white text-sm transition">取消</button></>}
          {stage === 'select' && (
            <>
              <button onClick={() => setStage('parse')} className="text-gray-400 hover:text-white text-sm transition">← 返回</button>
              <button onClick={handleBatchSearch} disabled={selectedCount === 0 || busy}
                className="bg-primary hover:bg-primary-dark disabled:opacity-40 text-white px-5 py-2 rounded-lg text-sm transition">
                搜索音源 ({selectedCount} 首)
              </button>
            </>
          )}
          {stage === 'tag' && (
            <>
              <button onClick={() => setStage('select')} className="text-gray-400 hover:text-white text-sm transition">← 返回选择</button>
              <button onClick={handleDownloadAndSave} disabled={foundCount === 0}
                className="bg-primary hover:bg-primary-dark disabled:opacity-40 text-white px-5 py-2 rounded-lg text-sm transition">
                下载并创建歌单 ({foundCount} 首)
              </button>
            </>
          )}
          {stage === 'done' && (
            <><span /><button onClick={onClose} className="bg-primary hover:bg-primary-dark text-white px-5 py-2 rounded-lg text-sm transition">完成</button></>
          )}
        </div>
      </div>
    </div>
  )
}
