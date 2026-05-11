import { usePlayerStore } from '../store/usePlayerStore';

export default function LoopControls() {
  const {
    currentTime,
    loopA,
    loopB,
    loopActive,
    setLoopA,
    setLoopB,
    toggleLoop,
    clearLoop,
  } = usePlayerStore();

  return (
    <div className="flex items-center gap-3 bg-gray-900 rounded-xl p-3">
      <button
        onClick={() => setLoopA(currentTime)}
        className="px-3 py-2 bg-green-600/20 border border-green-600/50 hover:bg-green-600/40 text-green-400 rounded-lg text-sm font-mono transition-colors"
        title="设置循环起点"
      >
        Set A
      </button>
      <button
        onClick={() => setLoopB(currentTime)}
        disabled={loopA === null}
        className="px-3 py-2 bg-red-600/20 border border-red-600/50 hover:bg-red-600/40 text-red-400 rounded-lg text-sm font-mono transition-colors disabled:opacity-30"
        title="设置循环终点"
      >
        Set B
      </button>

      <div className="w-px h-6 bg-gray-700" />

      <button
        onClick={toggleLoop}
        disabled={loopA === null || loopB === null}
        className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
          loopActive
            ? 'bg-green-600 text-white'
            : 'bg-gray-800 text-gray-300 hover:bg-gray-700 border border-gray-600'
        } disabled:opacity-30`}
        title="开关循环"
      >
        {loopActive ? 'Loop ON' : 'Loop OFF'}
      </button>

      <button
        onClick={clearLoop}
        disabled={loopA === null && loopB === null}
        className="px-3 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-sm transition-colors disabled:opacity-30"
        title="清除循环点"
      >
        Clear
      </button>

      <div className="flex-1" />

      {/* Loop info */}
      <div className="text-xs text-gray-500 font-mono space-x-3">
        <span className="text-green-400">A: {loopA !== null ? loopA.toFixed(2) : '—'}</span>
        <span className="text-red-400">B: {loopB !== null ? loopB.toFixed(2) : '—'}</span>
      </div>
    </div>
  );
}
