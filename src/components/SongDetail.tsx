import React from 'react'
import { Calendar, Download, ExternalLink, FileAudio, Globe } from 'lucide-react'

import type { Song } from '../types'
import { useMusicStore } from '../store/useMusicStore'
import { formatDuration, formatFileSize } from '../utils/format'
import { AnalysisPanel } from './AnalysisPanel'
import { WaveformPlayer } from './WaveformPlayer'

interface Props {
  song: Song
}

export const SongDetail: React.FC<Props> = ({ song }) => {
  const downloadSong = useMusicStore((state) => state.downloadSong)
  const fetchPlaylistSong = useMusicStore((state) => state.fetchPlaylistSong)
  const hasLocalFile = Boolean(song.sourcePath)
  const isPlatformSong = Boolean(song.platformId)
  const isPlaylistSong = Boolean(song.playlistId)

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      <div className="bg-surface rounded-xl p-5">
        <div className="flex items-start gap-4">
          <div className="w-16 h-16 rounded-xl flex items-center justify-center flex-shrink-0 border bg-gradient-to-br from-primary/30 to-primary/5 border-primary/10">
            {isPlatformSong ? <Globe size={28} className="text-indigo-400" /> : <FileAudio size={28} className="text-primary" />}
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-bold text-white truncate">{song.title}</h2>
            <p className="text-sm text-slate-400 mt-0.5">{song.artist}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3 text-[11px] text-slate-500">
              {song.duration > 0 && <span>{formatDuration(song.duration)}</span>}
              {song.format && <span>{song.format.toUpperCase()}</span>}
              {song.fileSize > 0 && <span>{formatFileSize(song.fileSize)}</span>}
              {song.bpm && <span className="text-primary font-medium">{song.bpm} BPM</span>}
              {song.key && <span className="text-violet-400 font-medium">{song.camelotKey} ({song.key})</span>}
              <span className="flex items-center gap-1">
                <Calendar size={11} />
                {new Date(song.createdAt).toLocaleDateString('en-CA')}
              </span>
            </div>
            {song.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {song.tags.map((tag) => (
                  <span key={tag} className="text-[10px] px-2 py-0.5 rounded-full border border-border text-slate-300">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {hasLocalFile && <WaveformPlayer song={song} />}

      {!hasLocalFile && isPlatformSong && (
        <ActionCard
          title="This track is available from platform search."
          subtitle="Download it locally to enable playback and analysis."
          actionLabel={song.downloadStatus === 'downloading' ? 'Downloading...' : 'Download Track'}
          onClick={() => void downloadSong(song.id)}
          disabled={song.downloadStatus === 'downloading'}
          link={song.platformUrl}
        />
      )}

      {!hasLocalFile && !isPlatformSong && isPlaylistSong && (
        <ActionCard
          title="This track came from a playlist import."
          subtitle="Search and download a matching audio file."
          actionLabel={song.downloadStatus === 'downloading' ? 'Searching...' : 'Fetch Audio'}
          onClick={() => void fetchPlaylistSong(song.id)}
          disabled={song.downloadStatus === 'downloading'}
        />
      )}

      {hasLocalFile && <AnalysisPanel song={song} />}
    </div>
  )
}

const ActionCard: React.FC<{
  title: string
  subtitle: string
  actionLabel: string
  onClick: () => void
  disabled?: boolean
  link?: string
}> = ({ title, subtitle, actionLabel, onClick, disabled, link }) => (
  <div className="bg-surface rounded-xl p-5 text-center">
    <p className="text-sm text-slate-300">{title}</p>
    <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
    <div className="flex items-center justify-center gap-3 mt-3">
      <button
        onClick={onClick}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary/10 text-primary rounded-lg text-sm hover:bg-primary/20 transition-colors disabled:opacity-50"
      >
        <Download size={14} />
        {actionLabel}
      </button>
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-500/10 text-indigo-400 rounded-lg text-sm hover:bg-indigo-500/20 transition-colors"
        >
          <ExternalLink size={14} />
          Open Source
        </a>
      )}
    </div>
  </div>
)
