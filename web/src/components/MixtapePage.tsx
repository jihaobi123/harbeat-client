import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { mixtapeApi } from '../api/mixtape';
import { getStreamUrl, mixApi } from '../api/mix';
import type {
  DjOfflineMixResult,
  FangpiSearchSong,
  MixtapeImportedItem,
  MixtapeImportSong,
  MixtapeSearchItem,
  OfflineTransitionMode,
  ParsedPlaylistTrack,
  TrackSegmentName,
} from '../types/api';

const SEGMENTS: TrackSegmentName[] = ['all', 'intro', 'build', 'verse', 'drop', 'bridge', 'outro'];
const STYLE_TAGS = ['hiphop', 'breaking', 'popping', 'locking', 'krump', 'waacking', 'vogue', 'house', 'urban', 'commercial', 'jazzfunk', 'contemporary'];
const TRANSITION_MODES: OfflineTransitionMode[] = ['clean_blend', 'hard_cut', 'echo_out', 'riser', 'cut_swap', 'triplet_swap', 'melodic_reset'];

type QueueSong = MixtapeImportSong & {
  key: string;
  title: string;
  artist: string;
  segment: TrackSegmentName;
};

function errorMessage(err: unknown): string {
  const maybe = err as { response?: { data?: { message?: string; detail?: string } }; message?: string };
  return maybe.response?.data?.message ?? maybe.response?.data?.detail ?? maybe.message ?? 'Request failed';
}

function formatTime(sec?: number | null): string {
  if (!sec || sec <= 0) return '-';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function MixtapePage() {
  const [searchMode, setSearchMode] = useState<'style' | 'vibe'>('style');
  const [selectedTags, setSelectedTags] = useState<string[]>(['hiphop']);
  const [vibe, setVibe] = useState('');
  const [externalQuery, setExternalQuery] = useState('');
  const [localResults, setLocalResults] = useState<MixtapeSearchItem[]>([]);
  const [externalResults, setExternalResults] = useState<FangpiSearchSong[]>([]);
  const [queue, setQueue] = useState<QueueSong[]>([]);
  const [playlistUrl, setPlaylistUrl] = useState('');
  const [parsedTracks, setParsedTracks] = useState<ParsedPlaylistTrack[]>([]);
  const [playlistId, setPlaylistId] = useState<number | undefined>();
  const [imported, setImported] = useState<MixtapeImportedItem[]>([]);
  const [style, setStyle] = useState('hiphop');
  const [duration, setDuration] = useState(30);
  const [transitionMode, setTransitionMode] = useState<OfflineTransitionMode>('clean_blend');
  const [drumBoost, setDrumBoost] = useState(false);
  const [mixResult, setMixResult] = useState<DjOfflineMixResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const token = useMemo(() => localStorage.getItem('harbeat_token'), []);
  const canRender = !!playlistId && imported.filter((item) => item.song_id).length >= 2;

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => (prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag]));
  };

  const addToQueue = (item: MixtapeSearchItem | FangpiSearchSong) => {
    const source = item.source ?? 'fangpi';
    const librarySongId = 'library_song_id' in item ? item.library_song_id : undefined;
    const catalogSongId = 'song_id' in item ? item.song_id : undefined;
    const musicId = 'id' in item ? item.id : ('music_id' in item ? item.music_id : undefined);
    const key = `${source}:${librarySongId ?? catalogSongId ?? musicId ?? item.title}`;
    setQueue((prev) => {
      if (prev.some((song) => song.key === key)) return prev;
      return [
        ...prev,
        {
          key,
          title: item.title,
          artist: item.artist || 'Unknown Artist',
          library_song_id: librarySongId,
          song_id: catalogSongId,
          music_id: musicId,
          source,
          segment: 'all',
          tags: selectedTags,
        },
      ];
    });
  };

  const updateQueueSegment = (key: string, segment: TrackSegmentName) => {
    setQueue((prev) => prev.map((song) => (song.key === key ? { ...song, segment } : song)));
  };

  const updateParsedSegment = (index: number, segment: TrackSegmentName) => {
    setParsedTracks((prev) => prev.map((track, i) => (i === index ? { ...track, segment } : track)));
  };

  const searchLocal = async () => {
    setBusy('search');
    setMessage(null);
    try {
      const res = await mixtapeApi.vibeSearch({
        mode: searchMode,
        vibe: searchMode === 'vibe' ? vibe : '',
        tags: searchMode === 'style' ? selectedTags : [],
        limit: 30,
      });
      setLocalResults(res.data.data.local_results);
      setExternalResults(res.data.data.external_results);
      setMessage(`Found ${res.data.data.local_results.length} local results.`);
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const searchExternal = async () => {
    if (!externalQuery.trim()) return;
    setBusy('external');
    setMessage(null);
    try {
      const res = await mixtapeApi.search(externalQuery.trim());
      setExternalResults(res.data.data.songs);
      setMessage(`Found ${res.data.data.songs.length} downloadable candidates.`);
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const parsePlaylist = async () => {
    if (!playlistUrl.trim()) return;
    setBusy('parse');
    setMessage(null);
    try {
      const res = await mixtapeApi.parsePlaylist(playlistUrl.trim());
      setParsedTracks(res.data.data.tracks.map((track: ParsedPlaylistTrack) => ({ ...track, segment: 'all' })));
      setMessage(`Parsed ${res.data.data.platform}: ${res.data.data.tracks.length} tracks.`);
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const importQueue = async () => {
    if (!queue.length) return;
    setBusy('import');
    setMessage(null);
    try {
      const res = await mixtapeApi.importSongs({
        playlist_id: playlistId,
        playlist_name: `Mixtape_${Date.now()}`,
        songs: queue,
      });
      setPlaylistId(res.data.data.playlist_id);
      setImported((prev) => [...prev, ...res.data.data.imported]);
      setQueue([]);
      setMessage(`Imported ${res.data.data.imported.length} songs, failed ${res.data.data.failed.length}.`);
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const importParsedPlaylist = async () => {
    if (!playlistUrl.trim() || !parsedTracks.length) return;
    setBusy('playlist-import');
    setMessage(null);
    try {
      const res = await mixtapeApi.importPlaylist({
        url: playlistUrl.trim(),
        playlist_id: playlistId,
        playlist_name: `Mixtape_${Date.now()}`,
        track_segments: parsedTracks.map((track, index) => ({
          index,
          title: track.title,
          artist: track.artist,
          segment: track.segment ?? 'all',
        })),
        limit: parsedTracks.length,
      });
      setPlaylistId(res.data.data.playlist_id);
      setImported((prev) => [...prev, ...res.data.data.imported]);
      setMessage(`Playlist import: ${res.data.data.imported.length} imported, ${res.data.data.failed.length} failed.`);
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const renderMix = async () => {
    if (!playlistId) return;
    setBusy('render');
    setMessage(null);
    try {
      const res = await mixApi.generateOfflineMix({
        style,
        duration_minutes: duration,
        playlist_id: playlistId,
        output_format: 'both',
        output_name: `mixtape_${transitionMode}_${Date.now()}`,
        transition_mode: transitionMode,
        drum_boost: drumBoost,
        track_segments: imported
          .filter((item) => item.song_id)
          .map((item) => ({ song_id: item.song_id as number, segment: item.segment })),
        stem_aware: true,
        auto_separate_stems: false,
      });
      setMixResult(res.data.data);
      setMessage(`Rendered ${formatTime(res.data.data.duration_sec)}.`);
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-7xl px-6 py-8 space-y-5">
        <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.28em] text-cyan-300">HarBeat Jetson</p>
            <h1 className="text-4xl font-black">Mixtape Import</h1>
            <p className="mt-2 text-sm text-slate-400">Search, import songs, select track segments, then render through the Jetson mix backend.</p>
          </div>
          <div className="flex flex-wrap gap-2 text-sm">
            <Link to="/mix-lab" className="rounded-lg border border-slate-700 px-3 py-2 text-slate-200 hover:bg-slate-800">Mix Lab</Link>
            {!token && <Link to="/login" className="rounded-lg bg-cyan-500 px-3 py-2 font-bold text-cyan-950 hover:bg-cyan-400">Login</Link>}
          </div>
        </header>

        {message && (
          <div className="rounded-lg border border-slate-800 bg-slate-900 px-4 py-3 text-sm text-slate-200">{message}</div>
        )}

        <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={() => setSearchMode('style')} className={`rounded-lg px-3 py-2 text-sm font-bold ${searchMode === 'style' ? 'bg-cyan-500 text-cyan-950' : 'bg-slate-800 text-slate-300'}`}>Style tags</button>
              <button onClick={() => setSearchMode('vibe')} className={`rounded-lg px-3 py-2 text-sm font-bold ${searchMode === 'vibe' ? 'bg-cyan-500 text-cyan-950' : 'bg-slate-800 text-slate-300'}`}>Vibe text</button>
            </div>

            {searchMode === 'style' ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {STYLE_TAGS.map((tag) => (
                  <button
                    key={tag}
                    onClick={() => toggleTag(tag)}
                    className={`rounded-lg border px-3 py-2 text-xs font-bold ${selectedTags.includes(tag) ? 'border-cyan-400 bg-cyan-500/20 text-cyan-100' : 'border-slate-700 bg-slate-950 text-slate-400'}`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            ) : (
              <textarea
                value={vibe}
                onChange={(event) => setVibe(event.target.value)}
                placeholder="rainy night drive, battle energy, warm old-school groove..."
                className="mt-4 min-h-24 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
              />
            )}

            <div className="mt-4 flex gap-2">
              <button onClick={searchLocal} disabled={busy === 'search'} className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-bold text-cyan-950 hover:bg-cyan-400 disabled:opacity-50">
                {busy === 'search' ? 'Searching...' : 'Search library'}
              </button>
            </div>

            <div className="mt-4 grid gap-2">
              {localResults.map((item) => (
                <div key={item.library_song_id ?? item.id ?? `${item.title}-${item.artist}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-bold">{item.title}</div>
                      <div className="text-sm text-slate-500">{item.artist} | BPM {item.bpm ?? '-'} | {item.key ?? '-'}</div>
                    </div>
                    <button onClick={() => addToQueue(item)} className="rounded-lg bg-slate-700 px-3 py-2 text-xs font-bold hover:bg-slate-600">Add</button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(item.tags ?? []).slice(0, 8).map((tag) => <span key={tag} className="rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-300">{tag}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
            <h2 className="font-bold">Downloadable search</h2>
            <div className="mt-3 flex gap-2">
              <input value={externalQuery} onChange={(event) => setExternalQuery(event.target.value)} placeholder="song title artist" className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400" />
              <button onClick={searchExternal} disabled={busy === 'external'} className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-bold hover:bg-slate-600 disabled:opacity-50">Search</button>
            </div>
            <div className="mt-4 max-h-96 space-y-2 overflow-auto">
              {externalResults.map((item) => (
                <div key={`${item.source}-${item.id}`} className="rounded-lg border border-slate-800 bg-slate-950 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-bold">{item.title}</div>
                      <div className="text-sm text-slate-500">{item.artist} | {item.source ?? 'fangpi'}</div>
                    </div>
                    <button onClick={() => addToQueue(item)} className="rounded-lg bg-slate-700 px-3 py-2 text-xs font-bold hover:bg-slate-600">Add</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-bold">Import queue ({queue.length})</h2>
              <button onClick={importQueue} disabled={!queue.length || busy === 'import'} className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-bold text-emerald-950 hover:bg-emerald-400 disabled:opacity-50">Import queue</button>
            </div>
            <div className="mt-3 space-y-2">
              {queue.map((song) => (
                <div key={song.key} className="grid gap-2 rounded-lg border border-slate-800 bg-slate-950 p-3 md:grid-cols-[1fr_140px_auto] md:items-center">
                  <div>
                    <div className="font-bold">{song.title}</div>
                    <div className="text-sm text-slate-500">{song.artist} | {song.source ?? 'local'}</div>
                  </div>
                  <select value={song.segment} onChange={(event) => updateQueueSegment(song.key, event.target.value as TrackSegmentName)} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm">
                    {SEGMENTS.map((segment) => <option key={segment} value={segment}>{segment}</option>)}
                  </select>
                  <button onClick={() => setQueue((prev) => prev.filter((item) => item.key !== song.key))} className="rounded-lg border border-slate-700 px-3 py-2 text-xs font-bold hover:bg-slate-800">Remove</button>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
            <h2 className="font-bold">Playlist URL import</h2>
            <div className="mt-3 flex gap-2">
              <input value={playlistUrl} onChange={(event) => setPlaylistUrl(event.target.value)} placeholder="NetEase or QQ Music playlist URL" className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400" />
              <button onClick={parsePlaylist} disabled={busy === 'parse'} className="rounded-lg bg-slate-700 px-4 py-2 text-sm font-bold hover:bg-slate-600 disabled:opacity-50">Parse</button>
            </div>
            <div className="mt-3 max-h-72 space-y-2 overflow-auto">
              {parsedTracks.map((track, index) => (
                <div key={`${track.title}-${index}`} className="grid gap-2 rounded-lg border border-slate-800 bg-slate-950 p-3 md:grid-cols-[1fr_140px] md:items-center">
                  <div>
                    <div className="font-bold">{index + 1}. {track.title}</div>
                    <div className="text-sm text-slate-500">{track.artist} | {formatTime(track.duration)}</div>
                  </div>
                  <select value={track.segment ?? 'all'} onChange={(event) => updateParsedSegment(index, event.target.value as TrackSegmentName)} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm">
                    {SEGMENTS.map((segment) => <option key={segment} value={segment}>{segment}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <button onClick={importParsedPlaylist} disabled={!parsedTracks.length || busy === 'playlist-import'} className="mt-3 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-bold text-emerald-950 hover:bg-emerald-400 disabled:opacity-50">Import parsed playlist</button>
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900/70 p-4">
          <div className="grid gap-3 md:grid-cols-5">
            <label className="space-y-1 text-sm">
              <span className="text-slate-400">Style</span>
              <input value={style} onChange={(event) => setStyle(event.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-slate-400">Duration min</span>
              <input type="number" min={1} max={180} value={duration} onChange={(event) => setDuration(Number(event.target.value) || 30)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2" />
            </label>
            <label className="space-y-1 text-sm">
              <span className="text-slate-400">Transition</span>
              <select value={transitionMode} onChange={(event) => setTransitionMode(event.target.value as OfflineTransitionMode)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2">
                {TRANSITION_MODES.map((mode) => <option key={mode} value={mode}>{mode}</option>)}
              </select>
            </label>
            <label className="flex items-end gap-2 rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm">
              <input type="checkbox" checked={drumBoost} onChange={(event) => setDrumBoost(event.target.checked)} />
              <span>Drum boost</span>
            </label>
            <button onClick={renderMix} disabled={!canRender || busy === 'render'} className="rounded-lg bg-pink-500 px-4 py-2 font-black text-pink-950 hover:bg-pink-400 disabled:opacity-50 md:self-end">Render mix</button>
          </div>

          <div className="mt-4 grid gap-2 md:grid-cols-2">
            <div className="rounded-lg bg-slate-950 p-3 text-sm">
              <div className="font-bold">Imported tracks: {imported.length}</div>
              <div className="mt-2 max-h-48 space-y-1 overflow-auto text-slate-400">
                {imported.map((item) => <div key={`${item.library_song_id}-${item.index}`}>{item.title} | {item.segment} | song_id {item.song_id ?? '-'}</div>)}
              </div>
            </div>
            <div className="rounded-lg bg-slate-950 p-3 text-sm">
              <div className="font-bold">Render output</div>
              {mixResult ? (
                <div className="mt-2 space-y-2">
                  <div className="text-slate-400">Duration {formatTime(mixResult.duration_sec)}</div>
                  <div className="flex gap-3">
                    {mixResult.stream_files.wav && <a className="text-cyan-300 hover:text-cyan-200" href={getStreamUrl(mixResult.stream_files.wav)} target="_blank" rel="noreferrer">WAV</a>}
                    {mixResult.stream_files.mp3 && <a className="text-cyan-300 hover:text-cyan-200" href={getStreamUrl(mixResult.stream_files.mp3)} target="_blank" rel="noreferrer">MP3</a>}
                  </div>
                  {mixResult.warnings.length > 0 && <div className="text-amber-300">{mixResult.warnings.join(' | ')}</div>}
                </div>
              ) : (
                <div className="mt-2 text-slate-500">No mix rendered yet.</div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
