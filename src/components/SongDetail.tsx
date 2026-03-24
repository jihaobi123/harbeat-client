import React from 'react'
import { FileAudio, Clock, HardDrive, Tag, Calendar, Globe, ExternalLink, Download, Loader2, CheckCircle } from 'lucide-react'
import { Song } from '../types'
import { formatDuration, formatFileSize } from '../utils/format'
import { WaveformPlayer } from './WaveformPlayer'
import { AnalysisPanel } from './AnalysisPanel'
import { useMusicStore } from '../store/useMusicStore'

interface Props {
  song: Song
}

export const SongDetail: React.FC<Props> = ({ song }) => {
  const isFangpi = !!song.platformId
  const downloadSong = useMusicStore((s) => s.downloadSong)
  const hasLocalFile = !!song.sourcePath

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto">
      {/* Song Info Card */}
      <div className="bg-surface rounded-xl p-5">
        <div className="flex items-start gap-4">
          {/* Cover placeholder */}
          <div className={`w-16 h-16 rounded-xl flex items-center justify-center flex-shrink-0 border ${
            isFangpi
              ? 'bg-gradient-to-br from-indigo-500/30 to-indigo-500/5 border-indigo-500/10'
              : 'bg-gradient-to-br from-primary/30 to-primary/5 border-primary/10'
          }`}>
            {isFangpi ? (
              <Globe size={28} className="text-indigo-400" />
            ) : (
              <FileAudio size={28} className="text-primary" />
            )}
          </div>

          {/* Song meta */}
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-bold text-white truncate">
              {song.title}
            </h2>
            <p className="text-sm text-slate-400 mt-0.5">{song.artist}</p>

            <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
              {song.duration > 0 && (
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <Clock size={11} />
                  {formatDuration(song.duration)}
                </span>
              )}
              {song.format && (
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <Tag size={11} />
                  {song.format.toUpperCase()}
                </span>
              )}
              {song.fileSize > 0 && (
                <span className="flex items-center gap-1 text-[11px] text-slate-500">
                  <HardDrive size={11} />
                  {formatFileSize(song.fileSize)}
                </span>
              )}
              <span className="flex items-center gap-1 text-[11px] text-slate-500">
                <Calendar size={11} />
                {new Date(song.createdAt).toLocaleDateString('zh-CN')}
              </span>
              {song.platformUrl && (
                <a
                  href={song.platformUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  <ExternalLink size={11} />
                  fangpi.net
                </a>
              )}
            </div>
          </div>

          {/* Status badge */}
          <span
            className={`text-[11px] px-2.5 py-1 rounded-full font-medium flex-shrink-0 ${
              isFangpi && hasLocalFile
                ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                : isFangpi
                ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                : song.importStatus === 'ready'
                ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                : song.importStatus === 'importing'
                ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                : 'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}
          >
            {isFangpi && hasLocalFile
              ? '已下载'
              : isFangpi
              ? 'fangpi.net'
              : song.importStatus === 'ready'
              ? song.sourceType === 'local_file'
                ? '本地文件'
                : '平台曲库'
              : song.importStatus === 'importing'
              ? '导入中...'
              : '导入错误'}
          </span>
        </div>
      </div>

      {/* Waveform & Player — for any song with a local file */}
      {hasLocalFile && (
        <WaveformPlayer song={song} />
      )}

      {/* Fangpi song without local file — show download option */}
      {isFangpi && !hasLocalFile && (
        <div className="bg-surface rounded-xl p-5 text-center">
          <Globe size={32} className="text-indigo-400/50 mx-auto mb-2" />
          <p className="text-sm text-slate-400">该歌曲来自 fangpi.net 曲库</p>
          <p className="text-xs text-slate-600 mt-1">点击下方按钮下载到本地曲库后即可播放</p>
          <div className="flex items-center justify-center gap-3 mt-3">
            <button
              onClick={() => {
                if (song.downloadStatus !== 'downloading') {
                  downloadSong(song.id)
                }
              }}
              disabled={song.downloadStatus === 'downloading'}
              className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm transition-colors ${
                song.downloadStatus === 'downloading'
                  ? 'bg-yellow-500/10 text-yellow-400'
                  : song.downloadStatus === 'error'
                  ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                  : 'bg-primary/10 text-primary hover:bg-primary/20'
              }`}
            >
              {song.downloadStatus === 'downloading' ? (
                <><Loader2 size={14} className="animate-spin" /> 下载中...</>
              ) : song.downloadStatus === 'error' ? (
                <><Download size={14} /> 重试下载</>
              ) : (
                <><Download size={14} /> 下载到曲库</>
              )}
            </button>
            {song.platformUrl && (
              <a
                href={song.platformUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-500/10 text-indigo-400 rounded-lg text-sm hover:bg-indigo-500/20 transition-colors"
              >
                <ExternalLink size={14} />
                在 fangpi.net 打开
              </a>
            )}
          </div>
        </div>
      )}

      {/* Downloaded fangpi song badge */}
      {isFangpi && hasLocalFile && (
        <div className="bg-surface rounded-xl p-3 flex items-center gap-2">
          <CheckCircle size={16} className="text-green-400" />
          <span className="text-xs text-green-400">已下载到本地曲库</span>
          {song.platformUrl && (
            <a
              href={song.platformUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              <ExternalLink size={11} />
              fangpi.net
            </a>
          )}
        </div>
      )}

      {/* Analysis Panel — for any song with a local file */}
      {hasLocalFile && (
        <AnalysisPanel song={song} />
      )}
    </div>
  )
}
