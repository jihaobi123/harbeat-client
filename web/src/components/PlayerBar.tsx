import { usePlayerStore } from '../store/usePlayerStore';

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function PlayerBar() {
  const {
    isPlaying,
    currentTime,
    duration,
    playlist,
    currentTrackIndex,
    play,
    pause,
    next,
    prev,
    seek,
  } = usePlayerStore();

  const currentTrack = playlist[currentTrackIndex] ?? null;
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className="h-20 bg-gray-900 border-t border-gray-800 flex items-center px-6 gap-4 flex-shrink-0">
      {/* Track info */}
      <div className="w-48 min-w-0 flex-shrink-0">
        {currentTrack ? (
          <>
            <p className="text-sm font-medium truncate text-white">{currentTrack.title}</p>
            <p className="text-xs text-gray-500 truncate">{currentTrack.artist}</p>
          </>
        ) : (
          <p className="text-sm text-gray-600">未选择曲目</p>
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <button
          onClick={prev}
          disabled={currentTrackIndex <= 0}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-white transition-colors"
          title="上一首"
        >
          ⏮
        </button>
        <button
          onClick={isPlaying ? pause : play}
          className="w-11 h-11 flex items-center justify-center rounded-full bg-purple-600 hover:bg-purple-700 text-white transition-colors"
          title={isPlaying ? '暂停' : '播放'}
        >
          {isPlaying ? '⏸' : '▶'}
        </button>
        <button
          onClick={next}
          disabled={currentTrackIndex >= playlist.length - 1}
          className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-white transition-colors"
          title="下一首"
        >
          ⏭
        </button>
      </div>

      {/* Progress */}
      <div className="flex-1 flex items-center gap-3">
        <span className="text-xs text-gray-500 w-12 text-right tabular-nums">{formatTime(currentTime)}</span>
        <div
          className="flex-1 h-1.5 bg-gray-800 rounded-full cursor-pointer group relative"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = (e.clientX - rect.left) / rect.width;
            seek(pct * duration);
          }}
        >
          <div
            className="h-full bg-purple-500 rounded-full transition-[width] duration-100"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-xs text-gray-500 w-12 tabular-nums">{formatTime(duration)}</span>
      </div>

      {/* Deck indicator */}
      <div className="flex items-center gap-2 text-xs text-gray-600">
        <span className="w-2 h-2 rounded-full bg-green-500" />
        {playlist.length > 0 && `${currentTrackIndex + 1}/${playlist.length}`}
      </div>
    </div>
  );
}
