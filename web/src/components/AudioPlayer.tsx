import { useRef, useEffect, useState, useCallback } from 'react'
import { useMusicStore } from '../store/useMusicStore'
import { useAuthStore } from '../store/useAuthStore'
import { getStreamUrl, logInteraction } from '../api/client'
import { EditorialIcon } from './editorial/EditorialIcon'

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

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    if (isPlaying) {
      audio.play().catch(() => {})
    } else {
      audio.pause()
    }
  }, [isPlaying])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !playingSong) return
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

  const handleSeekCommit = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.currentTime = currentTime
    }
    setSeeking(false)
  }, [currentTime])

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  if (!playingSong) {
    return (
      <div className="editorial-player shrink-0" role="status">
        <span className="street-subtitle text-sm">Pick a track to start / 选择一首歌曲开始播放</span>
      </div>
    )
  }

  return (
    <div className="editorial-player shrink-0">
      <audio
        ref={audioRef}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoaded}
        onEnded={() => { flushInteraction('complete'); useMusicStore.getState().togglePlay() }}
      />

      {/* Song info - compact on mobile */}
      <div className="w-28 sm:w-52 shrink-0 min-w-0">
        <div className="text-xs sm:text-sm truncate font-semibold">{playingSong.title}</div>
        <div className="text-[10px] sm:text-xs truncate">{playingSong.artist}</div>
      </div>

      {/* Play controls */}
      <div className="flex-1 flex flex-col items-center gap-0.5 sm:gap-1 max-w-2xl mx-auto">
        <button
          onClick={togglePlay}
          className="editorial-player__play w-9 h-9 sm:w-10 sm:h-10 flex items-center justify-center"
          aria-label={isPlaying ? '暂停' : '播放'}
        >
          <EditorialIcon name={isPlaying ? 'pause' : 'play'} decorative />
        </button>

        <div className="w-full flex items-center gap-1 sm:gap-2">
          <span className="text-[10px] sm:text-xs w-8 sm:w-10 text-right">{formatTime(currentTime)}</span>
          <div className="editorial-player__progress flex-1 relative h-2">
            <div className="absolute inset-y-0 left-0 bg-primary" style={{ width: `${progress}%` }} />
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
              aria-label="播放进度"
            />
          </div>
          <span className="text-[10px] sm:text-xs w-8 sm:w-10">{formatTime(duration)}</span>
        </div>
      </div>

      {/* Volume - hidden on mobile */}
      <div className="hidden sm:flex w-36 shrink-0 items-center gap-2">
        <EditorialIcon name="volume" decorative />
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={volume}
          onChange={(e) => setVolume(parseFloat(e.target.value))}
          className="w-full"
          aria-label="音量"
        />
      </div>
    </div>
  )
}
