import { useEffect, useMemo, useState } from 'react';
import { devMixApi, type DevSongItem } from '../api/devMix';
import { BattleDanceSfxPlayer } from '../engine/BattleDanceSfxPlayer';
import { MixSessionController, type EnergyPreference, type MixSessionSnapshot, type MixStrategy, type PlanMode } from '../engine/MixSessionController';
import VoiceButton from './VoiceButton';
import type { DjMixPlanResult, VoiceCommandResponse } from '../types/api';

function formatTime(sec?: number | null): string {
  if (!sec || sec <= 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function createInitialSnapshot(controller: MixSessionController): MixSessionSnapshot {
  return controller.getSnapshot();
}

const MIX_STRATEGIES: { value: MixStrategy; label: string }[] = [
  { value: 'clean_blend', label: 'CLEAN_BLEND' },
  { value: 'echo_out', label: 'ECHO_OUT' },
  { value: 'riser', label: 'RISER' },
  { value: 'cut_swap', label: 'CUT_SWAP' },
  { value: 'triplet_swap', label: 'TRIPLET_SWAP' },
  { value: 'melodic_reset', label: 'MELODIC_RESET' },
];

export default function MixLabPage() {
  const controller = useMemo(() => new MixSessionController(), []);
  const [snapshot, setSnapshot] = useState<MixSessionSnapshot>(() => createInitialSnapshot(controller));
  const [songs, setSongs] = useState<DevSongItem[]>([]);
  const [plan, setPlan] = useState<DjMixPlanResult | null>(null);
  const [loadingSongs, setLoadingSongs] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [style, setStyle] = useState('hiphop');
  const [duration, setDuration] = useState(10);
  const [manualStrategy, setManualStrategy] = useState<MixStrategy>('clean_blend');
  const [selectedSongIds, setSelectedSongIds] = useState<number[]>([]);
  const [planMode, setPlanMode] = useState<PlanMode>('random');
  const [energyPreference, setEnergyPreference] = useState<EnergyPreference>('none');
  const [voiceEnabled, setVoiceEnabled] = useState(false);

  const sfx_player = useMemo(() => new BattleDanceSfxPlayer(), []);
  useEffect(() => {
    controller.setOnStateChange(setSnapshot);
  }, [controller]);

  const loadSongs = async () => {
    setLoadingSongs(true);
    setError(null);
    try {
      const res = await devMixApi.listSongs(32);
      setSongs(res.data.data.songs);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load songs');
    } finally {
      setLoadingSongs(false);
    }
  };

  const generatePlan = async () => {
    setGenerating(true);
    setError(null);
    try {
      controller.syncPlanModeFromUi(planMode);
      const res = await devMixApi.generateMixPlan({
        style,
        duration_minutes: duration,
        quality_mode: 'fast',
        diversity: 0.35,
        max_tracks: 8,
        song_ids: selectedSongIds.length >= 2 ? selectedSongIds.slice(0, 2) : undefined,
      });
      const nextPlan = res.data.data;
      setPlan(nextPlan);
      controller.loadPlan(nextPlan);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate mix plan');
    } finally {
      setGenerating(false);
    }
  };

  const play = async () => {
    setError(null);
    try {
      await controller.play();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Play failed');
    }
  };

  const play_sfx = async (action: () => void) => {
    try {
      await sfx_player.prepare();
      action();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SFX failed');
    }
  };

  const next = async () => {
    setError(null);
    try {
      await controller.next(true, manualStrategy);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Next failed');
    }
  };

  const transition = plan?.transition_plan[Math.max(0, snapshot.currentIndex)] ?? null;

  const handleVoiceCommand = async (cmd: VoiceCommandResponse) => {
    const payload = (cmd.command_payload?.payload ?? null) as Record<string, unknown> | null;
    switch (cmd.intent) {
      case 'play':
      case 'release':
        await controller.play();
        break;
      case 'pause':
      case 'hold':
        controller.pause();
        break;
      case 'next':
        await controller.next(true, manualStrategy);
        break;
      case 'emergency_stop':
        controller.stop();
        break;
      case 'lift_energy':
        setEnergyPreference('higher');
        controller.setEnergyPreference('higher');
        break;
      case 'drop_energy':
        setEnergyPreference('lower');
        controller.setEnergyPreference('lower');
        break;
      case 'switch_style': {
        const rawStyle = typeof payload?.style === 'string' ? payload.style : null;
        if (rawStyle) {
          const normalizedStyle = rawStyle.toLowerCase().replace(/[-\s]/g, '');
          setStyle(normalizedStyle);
        }
        break;
      }
      case 'noop':
      default:
        break;
    }
  };

  const loop_play_hint =
    snapshot.isLoopMode && snapshot.loopStartSec != null && snapshot.loopEndSec != null && snapshot.loopEndSec > snapshot.loopStartSec + 0.1
      ? snapshot.isLoopCyclePlayback
        ? '再按 Play：退出区间循环并恢复自动接歌'
        : '再按 Play：从 Loop 起点开始区间循环（另一 Deck 已静音）'
      : snapshot.isLoopMode
        ? '请用 Set Loop Start / Set Loop End 选择区间'
        : '';

  const play_label =
    snapshot.isLoopMode && snapshot.loopStartSec != null && snapshot.loopEndSec != null && snapshot.loopEndSec > snapshot.loopStartSec + 0.1
      ? snapshot.isLoopCyclePlayback
        ? 'Play（退出循环）'
        : 'Play（开始循环）'
      : 'Play';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-8 space-y-6">
        <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.35em] text-purple-300">HarBeat Demo</p>
            <h1 className="text-3xl md:text-5xl font-black">Online Mix Lab</h1>
            <p className="mt-2 text-slate-400">免登录验证页：双 Deck 在线混音、手动切入下一首、时间轴 EQ / Filter 自动化。</p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-purple-500/30 bg-purple-500/10 px-4 py-3 text-sm text-purple-100">
            <button
              onClick={() => setVoiceEnabled((v) => !v)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${voiceEnabled ? 'bg-green-600 hover:bg-green-500 text-white' : 'bg-slate-700 hover:bg-slate-600 text-slate-200'}`}
            >
              {voiceEnabled ? '语音总开关：ON' : '语音总开关：OFF'}
            </button>
            <VoiceButton enabled={voiceEnabled} onCommand={handleVoiceCommand} />
            <span>State: <span className="font-bold text-white">{snapshot.state}</span></span>
          </div>
        </header>

        {(error || snapshot.error) && (
          <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {error || snapshot.error}
          </div>
        )}

        <section className="grid gap-4 md:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5 shadow-2xl">
            <div className="grid gap-4 md:grid-cols-4">
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Style</span>
                <select value={style} onChange={(e) => setStyle(e.target.value)} className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2">
                  {['hiphop', 'house', 'popping', 'locking', 'breaking', 'waacking'].map((item) => (
                    <option key={item} value={item}>{item}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Duration</span>
                <input type="number" min={1} max={120} value={duration} onChange={(e) => setDuration(Number(e.target.value) || 10)} className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2" />
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Plan Mode</span>
                <select
                  value={planMode}
                  onChange={(e) => {
                    const mode = e.target.value as PlanMode;
                    setPlanMode(mode);
                    controller.setPlanMode(mode);
                  }}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2"
                >
                  <option value="random">Random</option>
                  <option value="camelot">Camelot</option>
                  <option value="energy">Energy</option>
                </select>
              </label>
              <label className="space-y-1 text-sm">
                <span className="text-slate-400">Manual Mix Strategy</span>
                <select
                  value={manualStrategy}
                  onChange={(e) => {
                    const nextStrategy = e.target.value as MixStrategy;
                    setManualStrategy(nextStrategy);
                    controller.setManualStrategy(nextStrategy);
                  }}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2"
                >
                  {MIX_STRATEGIES.map((item) => (
                    <option key={item.value} value={item.value}>{item.label}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-slate-400">Random 模式下一首能量偏好</span>
                <select
                  value={energyPreference}
                  onChange={(e) => {
                    const pref = e.target.value as EnergyPreference;
                    setEnergyPreference(pref);
                    controller.setEnergyPreference(pref);
                  }}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2"
                >
                  <option value="none">不限制</option>
                  <option value="higher">下一首能量更高</option>
                  <option value="lower">下一首能量更低</option>
                </select>
                <span className="block text-xs text-slate-500">仅在 Random 模式生效：按能量方向过滤后，选择 BPM 最接近的下一首。</span>
              </label>
              <button onClick={loadSongs} disabled={loadingSongs} className="rounded-xl bg-slate-700 px-4 py-2 font-semibold hover:bg-slate-600 disabled:opacity-50 md:self-end">
                {loadingSongs ? 'Loading...' : 'Load Songs'}
              </button>
              <button onClick={generatePlan} disabled={generating} className="rounded-xl bg-purple-600 px-4 py-2 font-semibold hover:bg-purple-500 disabled:opacity-50 md:self-end">
                {generating ? 'Generating...' : plan ? 'Regenerate Plan' : 'Generate Plan'}
              </button>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
              <button onClick={() => controller.previous()} disabled={!plan} className="h-14 w-24 rounded-full bg-sky-500 text-sm font-black text-sky-950 hover:bg-sky-400 disabled:opacity-40">Prev</button>
              <button onClick={play} disabled={!plan} className="h-16 w-32 rounded-full bg-emerald-500 text-lg font-black text-emerald-950 hover:bg-emerald-400 disabled:opacity-40">
                {play_label}
              </button>
              <button onClick={next} disabled={!plan || snapshot.currentIndex >= (plan?.playlist.length ?? 0) - 1} className="h-16 w-40 rounded-full bg-pink-500 text-lg font-black text-pink-950 hover:bg-pink-400 disabled:opacity-40">
                MANUAL
              </button>
              <button onClick={() => controller.skipToNextTrack()} disabled={!plan} className="h-14 w-24 rounded-full bg-sky-500 text-sm font-black text-sky-950 hover:bg-sky-400 disabled:opacity-40">Next</button>
              <button onClick={() => controller.stop()} className="h-16 w-28 rounded-full bg-slate-700 text-lg font-bold hover:bg-slate-600">
                Stop
              </button>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
              <button
                onClick={() => controller.toggleLoopMode()}
                disabled={!plan || snapshot.currentIndex < 0}
                className={`h-16 w-16 rounded-full font-black disabled:opacity-40 ${snapshot.isLoopMode ? 'bg-amber-300 text-amber-950 ring-2 ring-amber-200' : 'bg-amber-500 text-amber-950 hover:bg-amber-400'}`}
                title="Loop 编辑：选点后再按主 Play 进入循环"
              >
                LOOP
              </button>
              <button onClick={() => controller.setLoopStartFromCurrent()} disabled={!snapshot.isLoopMode} className="rounded-xl bg-slate-700 px-4 py-2 text-sm font-semibold hover:bg-slate-600 disabled:opacity-40">Set Loop Start</button>
              <button onClick={() => controller.setLoopEndFromCurrent()} disabled={!snapshot.isLoopMode} className="rounded-xl bg-slate-700 px-4 py-2 text-sm font-semibold hover:bg-slate-600 disabled:opacity-40">Set Loop End</button>
            </div>

            {loop_play_hint && (
              <p className="mt-2 text-center text-xs text-amber-200/90">{loop_play_hint}</p>
            )}

            <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
              <input
                type="range"
                min={0}
                max={Math.max(1, snapshot.durationSec || 1)}
                step={0.01}
                value={Math.min(snapshot.currentTimeSec || 0, Math.max(1, snapshot.durationSec || 1))}
                disabled={!plan || snapshot.currentIndex < 0 || !snapshot.isLoopMode}
                onChange={(e) => {
                  if (!snapshot.isLoopMode) return;
                  controller.seekCurrent(Number(e.target.value));
                }}
                className={`w-full ${!snapshot.isLoopMode ? 'cursor-not-allowed opacity-50' : ''}`}
              />
              <div className="mt-2 flex items-center justify-between text-xs text-slate-300">
                <span>{formatTime(snapshot.currentTimeSec)}</span>
                <span>{snapshot.isLoopMode ? `Loop ${snapshot.loopStartSec != null ? formatTime(snapshot.loopStartSec) : '--:--'} → ${snapshot.loopEndSec != null ? formatTime(snapshot.loopEndSec) : '--:--'}${snapshot.isLoopCyclePlayback ? ' · 循环中' : ''}` : 'Loop 关（仅 Loop 模式可拖动进度）'}</span>
                <span>{formatTime(snapshot.durationSec)}</span>
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
            <h2 className="text-lg font-bold">Runtime</h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Active Deck</dt><dd className="text-xl font-bold">{snapshot.activeDeck}</dd></div>
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Transition</dt><dd className="text-xl font-bold">{snapshot.isTransitioning ? 'Active' : 'Idle'}</dd></div>
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Manual Strategy</dt><dd className="text-lg font-bold">{MIX_STRATEGIES.find((item) => item.value === manualStrategy)?.label}</dd></div>
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Fallback</dt><dd className="text-lg font-bold">{snapshot.fallbackMode ? snapshot.fallbackReason ?? 'fade_mode' : 'Ready'}</dd></div>
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Loop 编辑</dt><dd className="text-lg font-bold">{snapshot.isLoopMode ? 'On' : 'Off'}</dd></div>
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">区间循环</dt><dd className="text-lg font-bold">{snapshot.isLoopCyclePlayback ? 'Yes' : 'No'}</dd></div>
              <div className="col-span-2 rounded-xl border border-cyan-500/25 bg-cyan-950/40 p-3">
                <dt className="text-cyan-400/90">上次接歌（含打分）</dt>
                <dd className="mt-1 text-sm text-cyan-100">
                  {snapshot.lastMixPlaybackPath == null
                    ? '尚未完成过接歌过渡'
                    : (
                      <>
                        <span className="font-bold text-white">方案技巧</span> {snapshot.lastMixPlanTechnique ?? '—'}
                        <span className="mx-2 text-slate-500">|</span>
                        <span className="font-bold text-white">实际播放</span> {snapshot.lastMixPlaybackTechnique ?? '—'}
                        <span className="mx-2 text-slate-500">|</span>
                        <span className="font-bold text-white">路径</span> {snapshot.lastMixPlaybackPath ?? '—'}
                        <span className="mx-2 text-slate-500">|</span>
                        <span className="font-bold text-white">score</span> {snapshot.lastMixScore != null ? snapshot.lastMixScore.toFixed(3) : '—'}
                      </>
                      )}
                </dd>
              </div>
              <div className="col-span-2 rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Last Event</dt><dd className="font-mono text-xs text-purple-200">{snapshot.lastEvent}</dd></div>
            </dl>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          {(['A', 'B'] as const).map((deck) => {
            const d = snapshot.decks[deck];
            return (
              <div key={deck} className={`rounded-3xl border p-5 ${snapshot.activeDeck === deck ? 'border-emerald-400/50 bg-emerald-400/10' : 'border-slate-800 bg-slate-900/70'}`}>
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-black">Deck {deck}</h2>
                  <span className="rounded-full bg-slate-950 px-3 py-1 text-xs uppercase tracking-widest text-slate-300">{d.state}</span>
                </div>
                <p className="mt-4 truncate text-xl font-bold">{d.title}</p>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm text-slate-300">
                  <div className="rounded-xl bg-slate-950 p-3">Song ID: {d.songId ?? '-'}</div>
                  <div className="rounded-xl bg-slate-950 p-3">Rate: {d.playbackRate.toFixed(3)}</div>
                </div>
              </div>
            );
          })}
        </section>

        <section className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
          <h2 className="text-lg font-bold">Sound FX（叠加播放，不接进混音时间轴）</h2>
          <p className="mt-1 text-xs text-slate-500">街舞 / Battle 常用短采样；人声提示走系统语音合成。</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('air_horn'))} className="rounded-xl bg-orange-600/90 px-3 py-2 text-xs font-bold hover:bg-orange-500">Air Horn</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('siren'))} className="rounded-xl bg-red-700/90 px-3 py-2 text-xs font-bold hover:bg-red-600">Siren</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('scratch'))} className="rounded-xl bg-amber-700/90 px-3 py-2 text-xs font-bold hover:bg-amber-600">Scratch</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('boom'))} className="rounded-xl bg-stone-700 px-3 py-2 text-xs font-bold hover:bg-stone-600">Impact</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('riser'))} className="rounded-xl bg-violet-700/90 px-3 py-2 text-xs font-bold hover:bg-violet-600">Riser</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('glitch'))} className="rounded-xl bg-fuchsia-700/90 px-3 py-2 text-xs font-bold hover:bg-fuchsia-600">Glitch</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.playBufferId('laser'))} className="rounded-xl bg-cyan-700/90 px-3 py-2 text-xs font-bold hover:bg-cyan-600">Laser</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.speak('3 — 2 — 1 — Go!'))} className="rounded-xl border border-slate-600 px-3 py-2 text-xs font-bold hover:bg-slate-800">3 2 1 Go</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.speak('Round one'))} className="rounded-xl border border-slate-600 px-3 py-2 text-xs font-bold hover:bg-slate-800">Round 1</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.speak('One more time!'))} className="rounded-xl border border-slate-600 px-3 py-2 text-xs font-bold hover:bg-slate-800">One more time</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.speak('Ohhh!'))} className="rounded-xl border border-slate-600 px-3 py-2 text-xs font-bold hover:bg-slate-800">Ohhh!</button>
            <button type="button" onClick={() => void play_sfx(() => sfx_player.speak('Yo! Check it!'))} className="rounded-xl border border-slate-600 px-3 py-2 text-xs font-bold hover:bg-slate-800">Yo Check it</button>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
            <h2 className="text-lg font-bold">Local Songs ({songs.length})</h2>
            <p className="mt-1 text-xs text-slate-500">勾选两首歌后 Generate Plan 会只生成这两首之间的混音。</p>
            <div className="mt-3 max-h-72 overflow-auto space-y-2">
              {songs.map((song) => {
                const checked = selectedSongIds.includes(song.song_id);
                return (
                  <label key={song.library_song_id} className={`block cursor-pointer rounded-xl px-3 py-2 text-sm ${checked ? 'bg-purple-600/30 ring-1 ring-purple-400' : 'bg-slate-950'}`}>
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          setSelectedSongIds((prev) => {
                            if (prev.includes(song.song_id)) return prev.filter((id) => id !== song.song_id);
                            return [...prev, song.song_id].slice(-2);
                          });
                        }}
                        className="mt-1"
                      />
                      <div>
                        <div className="font-semibold">{song.title}</div>
                        <div className="text-slate-500">{song.artist} · {formatTime(song.duration)} · BPM {song.bpm ?? '-'} · {song.camelot_key ?? song.key ?? '-'}</div>
                      </div>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold">Mix Plan ({plan?.playlist.length ?? 0} tracks)</h2>
              <span className="text-xs text-slate-400">Mode: {snapshot.planMode.toUpperCase()}</span>
            </div>
            <div className="mt-3 max-h-72 overflow-auto space-y-2">
              {plan?.playlist.map((track, idx) => (
                <div key={`${track.song_id}-${idx}`} className={`rounded-xl px-3 py-2 text-sm ${track.song_id === snapshot.currentTrack?.song_id ? 'bg-purple-600/30' : 'bg-slate-950'}`}>
                  <div className="font-semibold">{idx + 1}. {track.title}</div>
                  <div className="text-slate-500">{track.artist} · {formatTime(track.duration)} · BPM {track.bpm ?? '-'} · Energy {track.energy ?? '-'} · Key {track.key ?? '-'}</div>
                </div>
              ))}
            </div>
            {transition && (
              <div className="mt-4 rounded-xl border border-purple-500/30 bg-purple-500/10 p-3 text-xs text-purple-100">
                Next transition: {transition.transition_technique} · {transition.crossfade_sec.toFixed(1)}s · tempo ratio {transition.tempo_ratio.toFixed(3)} · events {transition.mix_control_timeline?.events.length ?? 0}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
