import React, { useMemo, useState } from 'react'
import { AlertCircle, CheckCircle, Link2, ListMusic, Loader2, Search, Tag, Upload, X } from 'lucide-react'

import { useAuthStore } from '../store/useAuthStore'
import { useMusicStore } from '../store/useMusicStore'
import type { DanceStyle, ImportPlaylistResult } from '../types'
import { getPlaylistDetail, type ImportPlaylistRequest, updatePlaylistSongTags } from '../services/api'

const DANCE_STYLES: Array<{ value: DanceStyle; label: string; color: string }> = [
  { value: 'hiphop', label: 'HipHop', color: '#ef4444' },
  { value: 'jazz', label: 'Jazz', color: '#f59e0b' },
  { value: 'breaking', label: 'Breaking', color: '#3b82f6' },
  { value: 'popping', label: 'Popping', color: '#8b5cf6' },
  { value: 'locking', label: 'Locking', color: '#ec4899' },
  { value: 'waacking', label: 'Waacking', color: '#14b8a6' },
  { value: 'house', label: 'House', color: '#06b6d4' },
  { value: 'krump', label: 'Krump', color: '#dc2626' },
  { value: 'funk', label: 'Funk', color: '#f97316' },
  { value: 'urban', label: 'Urban', color: '#a855f7' },
  { value: 'afro', label: 'Afro', color: '#22c55e' },
  { value: 'dancehall', label: 'Dancehall', color: '#eab308' },
  { value: 'other', label: 'Other', color: '#64748b' },
]

type SourceTab = 'link' | 'local' | 'platform'

interface ImportSongItem {
  key: string
  title: string
  artist: string
  duration: number
  bpm: number | null
  tags: DanceStyle[]
}

interface Props {
  visible: boolean
  onClose: () => void
}

export const PlaylistImportModal: React.FC<Props> = ({ visible, onClose }) => {
  const user = useAuthStore((state) => state.user)
  const songs = useMusicStore((state) => state.songs)
  const playlistImporting = useMusicStore((state) => state.playlistImporting)
  const playlistImportError = useMusicStore((state) => state.playlistImportError)
  const lastImportResult = useMusicStore((state) => state.lastImportResult)
  const importAndDownloadPlaylist = useMusicStore((state) => state.importAndDownloadPlaylist)
  const clearImportResult = useMusicStore((state) => state.clearImportResult)

  const [tab, setTab] = useState<SourceTab>('link')
  const [stage, setStage] = useState<'source' | 'downloading' | 'tag'>('source')
  const [playlistName, setPlaylistName] = useState('')
  const [linkText, setLinkText] = useState('')
  const [query, setQuery] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [searchResults, setSearchResults] = useState<Array<{ id: string; title: string; artist: string }>>([])
  const [songItems, setSongItems] = useState<ImportSongItem[]>([])
  const [importedPlaylistId, setImportedPlaylistId] = useState<string | null>(null)
  const [downloadResult, setDownloadResult] = useState<{ success: string[]; failed: string[] } | null>(null)

  const localSongs = useMemo(
    () => songs.filter((song) => song.importStatus === 'ready'),
    [songs]
  )

  const reset = () => {
    clearImportResult()
    setTab('link')
    setStage('source')
    setPlaylistName('')
    setLinkText('')
    setQuery('')
    setStatusMessage('')
    setBusy(false)
    setSearchResults([])
    setSongItems([])
    setImportedPlaylistId(null)
    setDownloadResult(null)
    onClose()
  }

  const addSongs = (items: ImportSongItem[]) => {
    setSongItems((previous) => {
      const seen = new Set(previous.map((song) => `${song.title}||${song.artist}`.toLowerCase()))
      const additions = items.filter((song) => !seen.has(`${song.title}||${song.artist}`.toLowerCase()))
      return [...previous, ...additions]
    })
  }

  const parsePlaylistLink = async () => {
    if (!linkText.trim()) return
    setBusy(true)
    setStatusMessage('')
    try {
      const result = await window.electronAPI.parsePlaylistUrl(linkText.trim())
      if (result.error) throw new Error(result.error)
      if (!result.playlist || result.playlist.tracks.length === 0) {
        throw new Error('No songs parsed from the playlist link.')
      }
      addSongs(
        result.playlist.tracks.map((track, index) => ({
          key: `link-${Date.now()}-${index}`,
          title: track.title,
          artist: track.artist,
          duration: track.duration,
          bpm: null,
          tags: [],
        }))
      )
      setStatusMessage(`Added ${result.playlist.tracks.length} songs.`)
      setLinkText('')
    } catch (error) {
      setStatusMessage(String(error))
    } finally {
      setBusy(false)
    }
  }

  const searchPlatform = async () => {
    if (!query.trim()) return
    setBusy(true)
    setStatusMessage('')
    try {
      const result = await window.electronAPI.searchPlatform(query.trim())
      if (result.error) throw new Error(result.error)
      setSearchResults(result.songs || [])
    } catch (error) {
      setStatusMessage(String(error))
    } finally {
      setBusy(false)
    }
  }

  const startImport = async () => {
    if (!user || songItems.length === 0 || !playlistName.trim()) return
    setStage('downloading')
    const songList: ImportPlaylistRequest['songList'] = songItems.map((song) => ({
      title: song.title,
      artist: song.artist,
      duration: song.duration,
      bpm: song.bpm,
      tags: song.tags,
    }))
    const result = await importAndDownloadPlaylist(user.id, playlistName.trim(), songList)
    if (!result) {
      setStage('source')
      return
    }
    setImportedPlaylistId(result.playlistId)
    setDownloadResult({ success: result.success, failed: result.failed })
    setStage('tag')
  }

  const saveTags = async () => {
    if (!importedPlaylistId) return
    const detailResponse = await getPlaylistDetail(importedPlaylistId)
    const backendSongs = [...(detailResponse.data?.songs || [])].sort((a, b) => a.order - b.order)
    for (let index = 0; index < songItems.length; index += 1) {
      const backendSong = backendSongs[index]
      if (!backendSong) continue
      await updatePlaylistSongTags(importedPlaylistId, backendSong.songId, songItems[index].tags)
    }
    reset()
  }

  if (!visible) return null
  if (lastImportResult) return <ImportResultView result={lastImportResult} onClose={reset} />

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface rounded-xl shadow-2xl w-[760px] max-h-[85vh] flex flex-col border border-border">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <ListMusic size={18} className="text-primary" />
            <h2 className="text-base font-semibold text-white">
              {stage === 'tag' ? 'Save Playlist Tags' : 'Import Playlist'}
            </h2>
          </div>
          <button onClick={reset} className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-hover transition-all">
            <X size={18} />
          </button>
        </div>

        {stage === 'downloading' ? (
          <div className="px-8 py-12 flex flex-col items-center">
            <Loader2 size={34} className="animate-spin text-primary mb-4" />
            <p className="text-white">Matching and downloading tracks.</p>
            <p className="text-xs text-slate-500 mt-2">You will save tags after this finishes.</p>
          </div>
        ) : stage === 'tag' ? (
          <>
            <div className="flex-1 overflow-y-auto">
              {songItems.map((item) => (
                <div key={item.key} className="px-5 py-3 border-b border-border/40">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm text-slate-200 truncate">{item.title}</p>
                      <p className="text-[11px] text-slate-500 truncate">{item.artist}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {DANCE_STYLES.map((style) => {
                      const active = item.tags.includes(style.value)
                      return (
                        <button
                          key={style.value}
                          onClick={() => {
                            setSongItems((previous) =>
                              previous.map((song) =>
                                song.key !== item.key
                                  ? song
                                  : {
                                      ...song,
                                      tags: active
                                        ? song.tags.filter((tag) => tag !== style.value)
                                        : [...song.tags, style.value],
                                    }
                              )
                            )
                          }}
                          className="px-2 py-0.5 text-[10px] rounded-full border"
                          style={active ? { backgroundColor: `${style.color}20`, borderColor: `${style.color}60`, color: style.color } : undefined}
                        >
                          {style.label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
            {downloadResult && downloadResult.failed.length > 0 && (
              <div className="mx-5 mt-3 px-4 py-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-xs text-yellow-400">
                Missing local audio: {downloadResult.failed.join(' / ')}
              </div>
            )}
            <div className="px-5 py-4 border-t border-border flex items-center justify-between">
              <p className="text-xs text-slate-500">Tags are saved through the formal FastAPI endpoints.</p>
              <button onClick={saveTags} className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-white px-5 py-2 rounded-lg text-sm font-medium transition-all">
                <Tag size={14} />
                Save Tags
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="px-5 py-4 space-y-4 overflow-y-auto">
              <div>
                <label className="block text-xs text-slate-400 mb-1.5">Playlist Name</label>
                <input
                  value={playlistName}
                  onChange={(event) => setPlaylistName(event.target.value)}
                  placeholder="Example: Practice Playlist"
                  className="w-full bg-surface-dark border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
                />
              </div>

              <div className="flex gap-1 bg-surface-dark rounded-lg p-1">
                <button onClick={() => setTab('link')} className={`flex-1 py-2 text-xs rounded-md ${tab === 'link' ? 'bg-primary/20 text-primary' : 'text-slate-400'}`}>
                  <Link2 size={14} className="inline mr-1" />
                  Link
                </button>
                <button onClick={() => setTab('local')} className={`flex-1 py-2 text-xs rounded-md ${tab === 'local' ? 'bg-primary/20 text-primary' : 'text-slate-400'}`}>
                  <Upload size={14} className="inline mr-1" />
                  Local
                </button>
                <button onClick={() => setTab('platform')} className={`flex-1 py-2 text-xs rounded-md ${tab === 'platform' ? 'bg-primary/20 text-primary' : 'text-slate-400'}`}>
                  <Search size={14} className="inline mr-1" />
                  Platform
                </button>
              </div>

              {tab === 'link' && (
                <div className="flex gap-2">
                  <input
                    value={linkText}
                    onChange={(event) => setLinkText(event.target.value)}
                    onKeyDown={(event) => event.key === 'Enter' && parsePlaylistLink()}
                    placeholder="Paste a playlist link"
                    className="flex-1 bg-surface-dark border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
                  />
                  <button onClick={parsePlaylistLink} disabled={busy || !linkText.trim()} className="bg-cyan-600 hover:bg-cyan-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm">
                    {busy ? <Loader2 size={14} className="animate-spin" /> : 'Parse'}
                  </button>
                </div>
              )}

              {tab === 'local' && (
                <div className="max-h-[220px] overflow-y-auto border border-border rounded-lg divide-y divide-border/40">
                  {localSongs.map((song) => (
                    <button
                      key={song.id}
                      onClick={() => addSongs([{ key: `local-${song.id}`, title: song.title, artist: song.artist, duration: song.duration, bpm: song.bpm, tags: [] }])}
                      className="w-full text-left px-3 py-2 hover:bg-hover"
                    >
                      <p className="text-sm text-slate-200 truncate">{song.title}</p>
                      <p className="text-[11px] text-slate-500 truncate">{song.artist}</p>
                    </button>
                  ))}
                </div>
              )}

              {tab === 'platform' && (
                <>
                  <div className="flex gap-2">
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      onKeyDown={(event) => event.key === 'Enter' && searchPlatform()}
                      placeholder="Search platform music"
                      className="flex-1 bg-surface-dark border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-primary transition-colors"
                    />
                    <button onClick={searchPlatform} disabled={busy || !query.trim()} className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white px-4 py-2 rounded-lg text-sm">
                      {busy ? <Loader2 size={14} className="animate-spin" /> : 'Search'}
                    </button>
                  </div>
                  <div className="max-h-[220px] overflow-y-auto border border-border rounded-lg divide-y divide-border/40">
                    {searchResults.map((song) => (
                      <button
                        key={song.id}
                        onClick={() => addSongs([{ key: `platform-${song.id}`, title: song.title, artist: song.artist, duration: 0, bpm: null, tags: [] }])}
                        className="w-full text-left px-3 py-2 hover:bg-hover"
                      >
                        <p className="text-sm text-slate-200 truncate">{song.title}</p>
                        <p className="text-[11px] text-slate-500 truncate">{song.artist}</p>
                      </button>
                    ))}
                  </div>
                </>
              )}

              {statusMessage && (
                <div className="flex items-center gap-2 p-3 rounded-lg text-xs bg-surface-dark border border-border text-slate-300">
                  <AlertCircle size={14} />
                  <span>{statusMessage}</span>
                </div>
              )}

              {playlistImportError && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-xs text-red-400">
                  <AlertCircle size={14} />
                  <span>{playlistImportError}</span>
                </div>
              )}

              <div className="max-h-[220px] overflow-y-auto border border-border rounded-lg divide-y divide-border/40">
                {songItems.map((item) => (
                  <div key={item.key} className="flex items-center gap-3 px-3 py-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-200 truncate">{item.title}</p>
                      <p className="text-[11px] text-slate-500 truncate">{item.artist}</p>
                    </div>
                    <button onClick={() => setSongItems((previous) => previous.filter((song) => song.key !== item.key))} className="p-1 text-slate-600 hover:text-red-400 transition-colors">
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="px-5 py-4 border-t border-border flex items-center justify-between">
              <p className="text-xs text-slate-500">Desktop still handles discovery and downloads. Playlist metadata now goes through the API.</p>
              <button onClick={startImport} disabled={playlistImporting || songItems.length === 0 || !playlistName.trim()} className="flex items-center gap-2 bg-primary hover:bg-primary-hover disabled:opacity-40 text-white px-5 py-2 rounded-lg text-sm font-medium transition-all">
                <ListMusic size={14} />
                Start Import
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const ImportResultView: React.FC<{ result: ImportPlaylistResult; onClose: () => void }> = ({ result, onClose }) => (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
    <div className="bg-surface rounded-xl shadow-2xl w-[420px] border border-border">
      <div className="flex flex-col items-center px-6 py-8">
        <div className="w-16 h-16 rounded-full bg-green-500/10 flex items-center justify-center mb-4">
          <CheckCircle size={32} className="text-green-400" />
        </div>
        <h3 className="text-lg font-semibold text-white mb-2">Playlist Imported</h3>
        <div className="w-full space-y-3 mt-4 p-4 bg-surface-dark rounded-lg">
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">Playlist ID</span>
            <span className="text-white font-mono text-xs">{result.playlistId}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">Imported</span>
            <span className="text-green-400 font-medium">{result.importCount}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-400">Pending Analysis</span>
            <span className={`font-medium ${result.pendingAnalysisCount > 0 ? 'text-yellow-400' : 'text-slate-500'}`}>
              {result.pendingAnalysisCount}
            </span>
          </div>
        </div>
        <button onClick={onClose} className="mt-6 bg-primary hover:bg-primary-hover text-white px-8 py-2.5 rounded-lg text-sm font-medium transition-all">
          Done
        </button>
      </div>
    </div>
  </div>
)
