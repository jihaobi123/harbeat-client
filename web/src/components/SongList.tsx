import { useMusicStore } from '../store/useMusicStore'
import type { LibrarySong } from '../types'

function formatDuration(sec: number): string {
  if (!sec || sec <= 0) return '--:--'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatSize(bytes: number): string {
  if (!bytes) return ''
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function SongRow({ song }: { song: LibrarySong }) {
  const { selectSong, selectedSong, playSong, playingSong } = useMusicStore()
  const isSelected = selectedSong?.id === song.id
  const isPlaying = playingSong?.id === song.id

  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 cursor-pointer transition group ${
        isSelected ? 'bg-primary/15' : 'hover:bg-surface-lighter'
      }`}
      onClick={() => selectSong(song)}
      onDoubleClick={() => playSong(song)}
    >
      {/* Play indicator / index */}
      <div className="w-8 text-center shrink-0">
        {isPlaying ? (
          <span className="text-primary text-sm">♫</span>
        ) : (
          <button
            className="opacity-0 group-hover:opacity-100 text-gray-400 hover:text-white transition"
            onClick={(e) => { e.stopPropagation(); playSong(song) }}
          >
            ▶
          </button>
        )}
      </div>

      {/* Title & Artist */}
      <div className="flex-1 min-w-0">
        <div className={`text-sm truncate ${isPlaying ? 'text-primary font-medium' : 'text-white'}`}>
          {song.title}
        </div>
        <div className="text-xs text-gray-500 truncate">{song.artist}</div>
      </div>

      {/* BPM */}
      <div className="w-14 text-xs text-gray-400 text-right shrink-0">
        {song.bpm ? `${Math.round(song.bpm)}` : '-'}
        {song.bpm && <span className="text-gray-600 ml-0.5">bpm</span>}
      </div>

      {/* Duration */}
      <div className="w-12 text-xs text-gray-400 text-right shrink-0">
        {formatDuration(song.duration)}
      </div>

      {/* Format & Size */}
      <div className="w-20 text-xs text-gray-500 text-right shrink-0 hidden lg:block">
        {song.format?.toUpperCase()} {formatSize(song.file_size)}
      </div>
    </div>
  )
}

export default function SongList() {
  const { songs, songsLoading, selectedPlaylist } = useMusicStore()

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-700 flex items-center gap-3">
        <h2 className="text-sm font-semibold text-white">
          {selectedPlaylist ? selectedPlaylist.playlist_name : '我的音乐库'}
        </h2>
        <span className="text-xs text-gray-500">
          {selectedPlaylist ? `${selectedPlaylist.songs.length} 首` : `${songs.length} 首`}
        </span>
      </div>

      {/* Column headers */}
      <div className="flex items-center gap-3 px-4 py-1.5 text-xs text-gray-500 border-b border-gray-700/50">
        <div className="w-8 shrink-0" />
        <div className="flex-1">歌曲</div>
        <div className="w-14 text-right shrink-0">BPM</div>
        <div className="w-12 text-right shrink-0">时长</div>
        <div className="w-20 text-right shrink-0 hidden lg:block">格式</div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {songsLoading ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-sm">加载中...</div>
        ) : selectedPlaylist ? (
          selectedPlaylist.songs.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-gray-500 text-sm">歌单暂无歌曲</div>
          ) : (
            selectedPlaylist.songs.map((ps) => (
              <div
                key={ps.song_id}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-lighter transition cursor-pointer"
              >
                <div className="w-8 text-center shrink-0 text-xs text-gray-500">{ps.order_index + 1}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{ps.title}</div>
                  <div className="text-xs text-gray-500 truncate">{ps.artist}</div>
                </div>
                <div className="w-14 text-xs text-gray-400 text-right shrink-0">
                  {ps.bpm || '-'}
                </div>
                <div className="w-12 text-xs text-gray-400 text-right shrink-0">
                  {formatDuration(ps.duration || 0)}
                </div>
                <div className="w-20 text-right shrink-0 hidden lg:block">
                  {ps.tags.length > 0 && (
                    <span className="text-xs bg-primary/20 text-primary px-1.5 py-0.5 rounded">{ps.tags[0]}</span>
                  )}
                </div>
              </div>
            ))
          )
        ) : songs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-48 text-gray-500">
            <div className="text-4xl mb-3">🎵</div>
            <div className="text-sm">音乐库为空</div>
            <div className="text-xs mt-1">点击右上角「上传」添加音乐</div>
          </div>
        ) : (
          songs.map((song) => <SongRow key={song.id} song={song} />)
        )}
      </div>
    </div>
  )
}
