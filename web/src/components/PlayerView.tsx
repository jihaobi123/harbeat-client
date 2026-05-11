import { usePlayerStore } from '../store/usePlayerStore';
import { getStreamUrl } from '../api/mix';
import WaveformBar from './WaveformBar';
import LoopControls from './LoopControls';
import VoiceButton from './VoiceButton';

function formatTime(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function PlayerView() {
  const {
    isPlaying,
    currentTime,
    duration,
    playlist,
    currentTrackIndex,
    transitions,
    offlineMix,
    play,
    pause,
    next,
    prev,
    seek,
  } = usePlayerStore();

  const currentTrack = playlist[currentTrackIndex] ?? null;
  const currentTransition = currentTrackIndex > 0 ? transitions[currentTrackIndex - 1] : null;

  const hasOfflineMix = offlineMix && Object.keys(offlineMix.stream_files).length > 0;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* Now Playing */}
      <div className="bg-gray-900 rounded-2xl p-6 space-y-4">
        {currentTrack ? (
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 bg-purple-900/50 rounded-xl flex items-center justify-center text-2xl">
              {isPlaying ? '🔊' : '🎵'}
            </div>
            <div className="flex-1 min-w-0">
              <h2 className="text-xl font-bold truncate text-white">{currentTrack.title}</h2>
              <p className="text-sm text-gray-400 truncate">{currentTrack.artist}</p>
              <div className="flex gap-3 mt-1 text-xs text-gray-500">
                {currentTrack.bpm && <span>BPM {currentTrack.bpm}</span>}
                {currentTrack.key && <span>Key {currentTrack.key}</span>}
                {currentTrack.energy && <span>Energy {currentTrack.energy}</span>}
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-2xl font-mono text-purple-300 tabular-nums">{formatTime(currentTime)}</p>
              <p className="text-xs text-gray-600 tabular-nums">/ {formatTime(duration)}</p>
            </div>
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <p className="text-lg">没有加载曲目</p>
            <p className="text-sm mt-1">请在 Dashboard 生成混音计划，然后点击"进入播放器"</p>
          </div>
        )}

        {/* Main transport */}
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={prev}
            disabled={currentTrackIndex <= 0}
            className="w-12 h-12 flex items-center justify-center rounded-full bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-white text-xl transition-colors"
          >
            ⏮
          </button>
          <button
            onClick={isPlaying ? pause : play}
            className="w-16 h-16 flex items-center justify-center rounded-full bg-purple-600 hover:bg-purple-700 text-white text-2xl transition-colors"
          >
            {isPlaying ? '⏸' : '▶'}
          </button>
          <button
            onClick={next}
            disabled={currentTrackIndex >= playlist.length - 1}
            className="w-12 h-12 flex items-center justify-center rounded-full bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-white text-xl transition-colors"
          >
            ⏭
          </button>
        </div>

        {/* Transition info */}
        {currentTransition && (
          <div className="bg-gray-800/50 rounded-lg px-4 py-2 text-xs text-gray-400 flex gap-4">
            <span>过渡: <span className="text-purple-400">{currentTransition.transition_technique}</span></span>
            <span>Crossfade: <span className="text-white">{currentTransition.crossfade_sec}s</span></span>
            <span>分数: <span className="text-white">{currentTransition.score.toFixed(3)}</span></span>
            {currentTransition.online_mix_safety && (
              <span className={currentTransition.online_mix_safety.online_mix_safe ? 'text-green-400' : 'text-yellow-400'}>
                {currentTransition.online_mix_safety.recommended_mode}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Waveform + Loop */}
      <WaveformBar />
      <LoopControls />

      {/* Offline Mix download */}
      {hasOfflineMix && (
        <div className="bg-gray-900 rounded-2xl p-4">
          <h3 className="text-sm font-semibold text-green-400 mb-2">离线混音就绪</h3>
          <div className="flex gap-2">
            {Object.entries(offlineMix!.stream_files).map(([fmt, filename]) => (
              <a
                key={fmt}
                href={getStreamUrl(filename)}
                download
                className="px-4 py-2 bg-green-600/20 border border-green-600/50 hover:bg-green-600/40 text-green-400 rounded-lg text-sm transition-colors"
              >
                下载 {fmt.toUpperCase()}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Voice Button (floating) */}
      <div className="fixed bottom-24 right-6 z-50">
        <VoiceButton />
      </div>
    </div>
  );
}
