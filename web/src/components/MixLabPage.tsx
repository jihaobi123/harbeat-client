import { useMemo, useState } from 'react';
import { devMixApi, type DevSongItem } from '../api/devMix';
import { MixSessionController, type MixSessionSnapshot } from '../engine/MixSessionController';
import type { DjMixPlanResult } from '../types/api';

function formatTime(sec?: number | null): string {
  if (!sec || sec <= 0) return '0:00';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function createInitialSnapshot(controller: MixSessionController): MixSessionSnapshot {
  return controller.getSnapshot();
}

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
  const [selectedSongIds, setSelectedSongIds] = useState<number[]>([]);

  useMemo(() => {
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

  const next = async () => {
    setError(null);
    try {
      await controller.next(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Next failed');
    }
  };

  const transition = plan?.transition_plan[Math.max(0, snapshot.currentIndex)] ?? null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-8 space-y-6">
        <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.35em] text-purple-300">HarBeat Demo</p>
            <h1 className="text-3xl md:text-5xl font-black">Online Mix Lab</h1>
            <p className="mt-2 text-slate-400">免登录验证页：双 Deck 在线混音、手动切入下一首、时间轴 EQ / Filter 自动化。</p>
          </div>
          <div className="rounded-2xl border border-purple-500/30 bg-purple-500/10 px-4 py-3 text-sm text-purple-100">
            State: <span className="font-bold text-white">{snapshot.state}</span>
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
              <button onClick={loadSongs} disabled={loadingSongs} className="rounded-xl bg-slate-700 px-4 py-2 font-semibold hover:bg-slate-600 disabled:opacity-50 md:self-end">
                {loadingSongs ? 'Loading...' : 'Load Songs'}
              </button>
              <button onClick={generatePlan} disabled={generating} className="rounded-xl bg-purple-600 px-4 py-2 font-semibold hover:bg-purple-500 disabled:opacity-50 md:self-end">
                {generating ? 'Generating...' : 'Generate Plan'}
              </button>
            </div>

            <div className="mt-5 flex items-center justify-center gap-4">
              <button onClick={play} disabled={!plan} className="h-16 w-32 rounded-full bg-emerald-500 text-lg font-black text-emerald-950 hover:bg-emerald-400 disabled:opacity-40">
                Play
              </button>
              <button onClick={next} disabled={!plan || snapshot.currentIndex >= (plan?.playlist.length ?? 0) - 1} className="h-16 w-40 rounded-full bg-pink-500 text-lg font-black text-pink-950 hover:bg-pink-400 disabled:opacity-40">
                Manual Next
              </button>
              <button onClick={() => controller.stop()} className="h-16 w-28 rounded-full bg-slate-700 text-lg font-bold hover:bg-slate-600">
                Stop
              </button>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
            <h2 className="text-lg font-bold">Runtime</h2>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Active Deck</dt><dd className="text-xl font-bold">{snapshot.activeDeck}</dd></div>
              <div className="rounded-xl bg-slate-950 p-3"><dt className="text-slate-500">Transition</dt><dd className="text-xl font-bold">{snapshot.isTransitioning ? 'Active' : 'Idle'}</dd></div>
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
            <h2 className="text-lg font-bold">Mix Plan ({plan?.playlist.length ?? 0} tracks)</h2>
            <div className="mt-3 max-h-72 overflow-auto space-y-2">
              {plan?.playlist.map((track, idx) => (
                <div key={`${track.song_id}-${idx}`} className={`rounded-xl px-3 py-2 text-sm ${idx === snapshot.currentIndex ? 'bg-purple-600/30' : 'bg-slate-950'}`}>
                  <div className="font-semibold">{idx + 1}. {track.title}</div>
                  <div className="text-slate-500">{track.artist} · {formatTime(track.duration)} · BPM {track.bpm ?? '-'}</div>
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
