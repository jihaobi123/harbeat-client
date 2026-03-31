import { useRef, useEffect, useState, useCallback } from 'react'
import { useMusicStore } from '../store/useMusicStore'
import { useAuthStore } from '../store/useAuthStore'
import { getStreamUrl, logInteraction } from '../api/client'

function formatTime(sec: number): string {
  if (!sec || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function AudioPlayer() {
  const { playingSong, isPlaying, volume, togglePlay, setVolume } = useMusicStore()
  const { user } = useAuthStore()
  const audioRef = useRef<HTMLAudioElement>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [seeking, setSeeking] = useState(false)
  const playStartRef = useRef<{ songId: string; startTime: number } | null>(null)

  // Log interaction when song changes or playback ends
  const flushInteraction = useCallback((action: string) => {
    const info = playStartRef.current
    if (!info || !user) return
    const dur = (Date.now() - info.startTime) / 1000
    const audioDur = audioRef.current?.duration || 0
    logInteraction({
      user_id: user.id,
      track_id: info.songId,
      action_type: action,
      play_duration_sec: dur,
      completion_rate: audioDur > 0 ? Math.min(1, dur / audioDur) : 0,
    }).catch(() => {})
    playStartRef.current = null
  }, [user])

  // Sync play/pause
  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    if (isPlaying) {
      audio.play().catch(() => {})
    } else {
      audio.pause()
    }
  }, [isPlaying])

  // Change source when song changes
  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !playingSong) return
    // Log previous song as 'skip' if switching
    if (playStartRef.current && playStartRef.current.songId !== playingSong.id) {
      flushInteraction('skip')
    }
    audio.src = getStreamUrl(playingSong.id)
    audio.load()
    playStartRef.current = { songId: playingSong.id, startTime: Date.now() }
    if (isPlaying) {
      audio.play().catch(() => {})
    }
  }, [playingSong])

  // Volume
  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume
  }, [volume])

  const handleTimeUpdate = useCallback(() => {
    if (!seeking && audioRef.current) {
      setCurrentTime(audioRef.current.currentTime)
    }
  }, [seeking])

  const handleLoaded = useCallback(() => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration || 0)
    }
  }, [])

  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value)
    setCurrentTime(val)
  }, [])

  const handleSeekCommit = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    if (audioRef.current) {
      audioRef.current.currentTime = currentTime
    }
    setSeeking(false)
  }, [currentTime])

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  if (!playingSong) {
    return (
      <div className="h-20 bg-surface-light border-t border-gray-700 flex items-center justify-center shrink-0">
        <span className="text-gray-500 text-sm">选择一首歌曲开始播放</span>
      </div>
    )
  }

  return (
    <div className="h-20 bg-surface-light border-t border-gray-700 flex items-center px-4 gap-4 shrink-0">
      <audio
        ref={audioRef}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoaded}
        onEnded={() => { flushInteraction('complete'); useMusicStore.getState().togglePlay() }}
      />

      {/* Song info */}
      <div className="w-52 shrink-0 min-w-0">
        <div className="text-sm text-white truncate">{playingSong.title}</div>
        <div className="text-xs text-gray-500 truncate">{playingSong.artist}</div>
      </div>

      {/* Controls */}
      <div className="flex-1 flex flex-col items-center gap-1 max-w-2xl mx-auto">
        <div className="flex items-center gap-4">
          <button
            onClick={togglePlay}
            className="w-9 h-9 rounded-full bg-white flex items-center justify-center hover:scale-105 transition"
          >
            {isPlaying ? (
              <svg className="w-4 h-4 text-surface" fill="currentColor" viewBox="0 0 24 24">
                <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
              </svg>
            ) : (
              <svg className="w-4 h-4 text-surface ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z"/>
              </svg>
            )}
          </button>
        </div>

        {/* Progress bar */}
        <div className="w-full flex items-center gap-2">
          <span className="text-xs text-gray-500 w-10 text-right">{formatTime(currentTime)}</span>
          <div className="flex-1 relative h-1 group">
            <div className="absolute inset-0 bg-gray-600 rounded-full" />
            <div className="absolute inset-y-0 left-0 bg-primary rounded-full" style={{ width: `${progress}%` }} />
            <input
              type="range"
              min={0}
              max={duration || 0}
              step={0.1}
              value={currentTime}
              onChange={handleSeek}
              onMouseDown={() => setSeeking(true)}
              onMouseUp={handleSeekCommit}
              onTouchStart={() => setSeeking(true)}
              onTouchEnd={handleSeekCommit}
              className="absolute inset-0 w-full opacity-0 cursor-pointer"
            />
          </div>
          <span className="text-xs text-gray-500 w-10">{formatTime(duration)}</span>
        </div>
      </div>

      {/* Volume */}
      <div className="w-32 shrink-0 flex items-center gap-2">
        <svg className="w-4 h-4 text-gray-400 shrink-0" fill="currentColor" viewBox="0 0 24 24">
          <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
        </svg>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={volume}
          onChange={(e) => setVolume(parseFloat(e.target.value))}
          className="w-full accent-primary"
        />
      </div>
    </div>
  )
}
