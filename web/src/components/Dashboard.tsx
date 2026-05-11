import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMixStore } from '../store/useMixStore';
import { usePlayerStore } from '../store/usePlayerStore';
import { useAuthStore } from '../store/useAuthStore';

const STYLES = ['hiphop', 'popping', 'locking', 'breaking', 'house', 'waacking'];
const SCENES = ['battle', 'cypher', 'party', 'exercise'];
const QUALITY_MODES = [
  { value: 'fast', label: '快速' },
  { value: 'balanced', label: '均衡' },
  { value: 'hq', label: '高质' },
] as const;
const RENDER_ENGINES = [
  { value: 'groove', label: 'GrooveEngine' },
  { value: 'simple', label: '简单 Crossfade' },
] as const;

export default function Dashboard() {
  const navigate = useNavigate();
  const userId = useAuthStore((s) => s.userId);
  const mix = useMixStore();
  const {
    generateMixPlan,
    generateOfflineMix,
    mixPlan,
    playlist,
    transitions,
    isGeneratingPlan,
    isRenderingMix,
    error,
    clearError,
  } = usePlayerStore();

  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleGeneratePlan = async () => {
    if (!userId) return;
    clearError();
    await generateMixPlan(userId, {
      style: mix.style,
      duration_minutes: mix.durationMinutes,
      quality_mode: mix.qualityMode,
      diversity: mix.diversity,
      bpm: mix.bpm ?? undefined,
      energy: mix.energy ?? undefined,
      scene_type: mix.sceneType ?? undefined,
      style_ratios: Object.keys(mix.styleRatios).length > 0 ? mix.styleRatios : undefined,
      use_context_planner: !!mix.sceneType,
    });
  };

  const handleRenderMix = async () => {
    if (!userId) return;
    clearError();
    await generateOfflineMix(userId, {
      style: mix.style,
      duration_minutes: mix.durationMinutes,
      quality_mode: mix.qualityMode,
      render_engine: mix.renderEngine,
      output_format: mix.outputFormat,
      output_name: `harbeat_mix_${Date.now()}`,
      diversity: mix.diversity,
      bpm: mix.bpm ?? undefined,
      energy: mix.energy ?? undefined,
    });
  };

  const handleLaunchPlayer = () => {
    navigate('/player');
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="text-2xl font-bold">Dashboard</h2>

      {/* Mix Controls */}
      <div className="bg-gray-900 rounded-2xl p-6 space-y-4">
        <h3 className="text-lg font-semibold text-purple-300">混音控制</h3>

        {/* Style + Duration */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">舞种风格</label>
            <select
              value={mix.style}
              onChange={(e) => mix.setStyle(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
            >
              {STYLES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">时长 (分钟)</label>
            <input
              type="number"
              value={mix.durationMinutes}
              onChange={(e) => mix.setDuration(Number(e.target.value) || 15)}
              min={3}
              max={120}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
            />
          </div>
        </div>

        {/* Scene Type */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">场景类型</label>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => mix.setSceneType(null)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                !mix.sceneType ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              自动
            </button>
            {SCENES.map((s) => (
              <button
                key={s}
                onClick={() => mix.setSceneType(s)}
                className={`px-3 py-1.5 rounded-lg text-sm capitalize transition-colors ${
                  mix.sceneType === s ? 'bg-purple-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Style Ratios (if scene selected) */}
        {mix.sceneType && (
          <div>
            <label className="block text-sm text-gray-400 mb-1">风格配比</label>
            <div className="grid grid-cols-3 gap-2">
              {STYLES.slice(0, 6).map((s) => (
                <div key={s} className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 w-16">{s}</span>
                  <input
                    type="number"
                    value={mix.styleRatios[s] ?? 0}
                    onChange={(e) => mix.setStyleRatio(s, Number(e.target.value) || 0)}
                    min={0}
                    max={100}
                    className="w-full px-2 py-1 bg-gray-800 border border-gray-700 rounded text-white text-xs"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Advanced toggle */}
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="text-sm text-gray-500 hover:text-gray-300"
        >
          {showAdvanced ? '收起高级选项 ▲' : '展开高级选项 ▼'}
        </button>

        {showAdvanced && (
          <div className="space-y-3 pt-2 border-t border-gray-800">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1">质量模式</label>
                <select
                  value={mix.qualityMode}
                  onChange={(e) => mix.setQualityMode(e.target.value as typeof mix.qualityMode)}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-xs"
                >
                  {QUALITY_MODES.map((q) => (
                    <option key={q.value} value={q.value}>{q.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">渲染引擎</label>
                <select
                  value={mix.renderEngine}
                  onChange={(e) => mix.setRenderEngine(e.target.value as typeof mix.renderEngine)}
                  className="w-full px-2 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-xs"
                >
                  {RENDER_ENGINES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">多样性 ({mix.diversity})</label>
                <input
                  type="range"
                  value={mix.diversity}
                  onChange={(e) => mix.setDiversity(Number(e.target.value))}
                  min={0}
                  max={1}
                  step={0.05}
                  className="w-full"
                />
              </div>
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-900/50 border border-red-700 text-red-300 px-4 py-2 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={handleGeneratePlan}
            disabled={isGeneratingPlan}
            className="flex-1 py-2.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {isGeneratingPlan ? '生成混音计划中...' : '生成混音计划'}
          </button>
          <button
            onClick={handleRenderMix}
            disabled={isRenderingMix || !mixPlan}
            className="flex-1 py-2.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {isRenderingMix ? '渲染中...' : '离线渲染混音'}
          </button>
        </div>
      </div>

      {/* Results */}
      {mixPlan && (
        <div className="bg-gray-900 rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-green-300">
              混音计划就绪 · {playlist.length} 首
            </h3>
            <button
              onClick={handleLaunchPlayer}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-medium transition-colors"
            >
              进入播放器
            </button>
          </div>

          {/* Playlist */}
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {playlist.map((track, i) => (
              <div key={track.song_id} className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-800/50 text-sm">
                <span className="text-gray-500 w-6 text-right">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <p className="truncate text-white">{track.title}</p>
                  <p className="text-xs text-gray-500 truncate">{track.artist}</p>
                </div>
                <span className="text-xs text-gray-600">{track.bpm ? `${track.bpm} BPM` : ''}</span>
                <span className="text-xs text-gray-600">{track.key ?? ''}</span>
              </div>
            ))}
          </div>

          {/* Transitions */}
          {transitions.length > 0 && (
            <details className="text-sm">
              <summary className="text-gray-400 cursor-pointer hover:text-gray-200">
                过渡详情 ({transitions.length} 个过渡)
              </summary>
              <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
                {transitions.map((t, i) => (
                  <div key={i} className="bg-gray-800 rounded-lg p-3 text-xs">
                    <span className="text-gray-500">#{i + 1}: </span>
                    <span className="text-purple-400">{t.transition_technique}</span>
                    <span className="text-gray-500"> · score </span>
                    <span className="text-white">{t.score.toFixed(3)}</span>
                    <span className="text-gray-500"> · crossfade </span>
                    <span className="text-white">{t.crossfade_sec.toFixed(1)}s</span>
                    <span className="text-gray-500"> · tempo ratio </span>
                    <span className="text-white">{(t.tempo_ratio * 100).toFixed(1)}%</span>
                    {t.online_mix_safety && (
                      <span className={`ml-2 ${t.online_mix_safety.online_mix_safe ? 'text-green-400' : 'text-yellow-400'}`}>
                        {t.online_mix_safety.recommended_mode}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
