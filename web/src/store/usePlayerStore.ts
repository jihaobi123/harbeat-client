import { create } from 'zustand';
import { MixAudioEngine } from '../engine/MixAudioEngine';
import { mixApi, getProcessedStreamUrl, getLibraryStreamUrl } from '../api/mix';
import type {
  PlaylistSongData,
  DjMixPlanRequest,
  DjMixPlanResult,
  DjOfflineMixRequest,
  DjOfflineMixResult,
  DjTransitionPlanItem,
  MixLoopRegion,
} from '../types/api';

interface PlayerState {
  // Playback
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  activeDeck: 'A' | 'B';

  // Loop
  loopA: number | null;
  loopB: number | null;
  loopActive: boolean;

  // Mix plan
  mixPlan: DjMixPlanResult | null;
  playlist: PlaylistSongData[];
  currentTrackIndex: number;
  transitions: DjTransitionPlanItem[];

  // Offline mix
  offlineMix: DjOfflineMixResult | null;

  // Loading
  isGeneratingPlan: boolean;
  isRenderingMix: boolean;
  error: string | null;

  // Engine access
  getEngine: () => MixAudioEngine;

  // Loop actions
  setLoopA: (time: number) => void;
  setLoopB: (time: number) => void;
  toggleLoop: () => void;
  clearLoop: () => void;

  // Playback actions
  play: () => void;
  pause: () => void;
  next: () => void;
  prev: () => void;
  seek: (time: number) => void;
  setVolume: (v: number) => void;
  onTimeUpdate: (time: number, dur: number) => void;

  // Mix plan actions
  generateMixPlan: (userId: number, params: DjMixPlanRequest) => Promise<void>;
  generateOfflineMix: (userId: number, params: DjOfflineMixRequest) => Promise<void>;
  loadTrackFromPlan: (index: number) => Promise<void>;
  loadProcessedTrack: (filename: string) => Promise<void>;

  clearError: () => void;
  reset: () => void;
}

export const usePlayerStore = create<PlayerState>((set, get) => {
  const engine = MixAudioEngine.getInstance();

  // Register engine callbacks once
  engine.setOnTimeUpdate((time, dur) => {
    set({ currentTime: time, duration: dur });
  });
  engine.setOnTrackEnd(() => {
    const state = get();
    if (state.currentTrackIndex < state.playlist.length - 1) {
      state.next();
    }
  });

  return {
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    activeDeck: 'A',
    loopA: null,
    loopB: null,
    loopActive: false,
    mixPlan: null,
    playlist: [],
    currentTrackIndex: -1,
    transitions: [],
    offlineMix: null,
    isGeneratingPlan: false,
    isRenderingMix: false,
    error: null,

    getEngine: () => engine,

    // ── Loop ──
    setLoopA: (time) => {
      const state = get();
      engine.setLoopPoints(time, state.loopB ?? time + 4);
      set({ loopA: time });
    },

    setLoopB: (time) => {
      const state = get();
      if (state.loopA !== null && time > state.loopA) {
        engine.setLoopPoints(state.loopA, time);
        set({ loopB: time });
      }
    },

    toggleLoop: () => {
      const active = engine.toggleLoop();
      set({ loopActive: active });
    },

    clearLoop: () => {
      engine.clearLoop();
      set({ loopA: null, loopB: null, loopActive: false });
    },

    // ── Playback ──
    play: () => {
      const state = get();
      if (state.currentTrackIndex < 0 && state.playlist.length > 0) {
        get().loadTrackFromPlan(0).then(() => {
          const deck = engine.getActiveDeck();
          engine.play(deck);
          set({ isPlaying: true });
        });
      } else {
        const deck = engine.getActiveDeck();
        engine.play(deck);
        set({ isPlaying: true });
      }
    },

    pause: () => {
      engine.pause();
      set({ isPlaying: false });
    },

    next: async () => {
      const state = get();
      if (state.currentTrackIndex >= state.playlist.length - 1) return;

      const nextIdx = state.currentTrackIndex + 1;
      const outgoingDeck = state.currentTrackIndex % 2 === 0 ? 'A' : 'B';
      const incomingDeck = nextIdx % 2 === 0 ? 'A' : 'B';
      const transition = state.transitions[nextIdx - 1];
      const timeline = transition?.mix_control_timeline;

      const resolveUrlForSongId = async (songId: number): Promise<string> => {
        const processed = state.mixPlan?.processed_files[songId];
        if (processed) {
          const filename = processed.split('/').pop() ?? processed;
          return getProcessedStreamUrl(filename);
        }
        const tr = state.playlist.find((t) => t.song_id === songId);
        if (tr?.library_song_id) return getLibraryStreamUrl(tr.library_song_id);
        throw new Error(`No stream URL for song_id=${songId}`);
      };

      if (timeline?.events?.length) {
        try {
          await engine.scheduleMixControlTimeline({
            timeline,
            outgoingDeck,
            incomingDeck,
            resolveUrlForSongId,
          });
          set({
            currentTrackIndex: nextIdx,
            activeDeck: incomingDeck,
            isPlaying: true,
            error: null,
          });
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : String(err);
          set({ error: msg });
        }
        return;
      }

      const incomingTrack = state.playlist[nextIdx];
      if (!incomingTrack) return;

      try {
        let url: string | null = null;
        const processedFile = state.mixPlan?.processed_files[incomingTrack.song_id];
        if (processedFile) {
          const filename = processedFile.split('/').pop() ?? processedFile;
          url = getProcessedStreamUrl(filename);
        } else if (incomingTrack.library_song_id) {
          url = getLibraryStreamUrl(incomingTrack.library_song_id);
        }
        if (!url) {
          set({
            error:
              'No stream URL for next track (missing processed file and library_song_id).',
          });
          return;
        }
        await engine.loadTrack(url, incomingDeck, incomingTrack.song_id);
        const crossfade = transition?.crossfade_sec ?? 4;
        const entrySec = transition?.entry_time_sec ?? 0;
        engine.triggerNextTrack(entrySec, crossfade);
        set({
          currentTrackIndex: nextIdx,
          activeDeck: engine.getActiveDeck(),
          isPlaying: true,
          error: null,
        });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        set({ error: msg });
      }
    },

    prev: () => {
      const state = get();
      if (state.currentTrackIndex > 0) {
        const prevIdx = state.currentTrackIndex - 1;
        get().loadTrackFromPlan(prevIdx).then(() => {
          engine.play(engine.getActiveDeck() === 'A' ? 'B' : 'A');
          set({ currentTrackIndex: prevIdx, isPlaying: true });
        });
      }
    },

    seek: (time) => {
      engine.seek(engine.getActiveDeck(), time);
    },

    setVolume: (v) => engine.setMasterVolume(v),

    onTimeUpdate: (time, dur) => {
      set({ currentTime: time, duration: dur });
    },

    // ── Mix Plan ──
    generateMixPlan: async (userId, params) => {
      set({ isGeneratingPlan: true, error: null });
      try {
        const res = await mixApi.generateDjMixPlan({ ...params, user_id: userId });
        const plan = res.data.data;
        set({
          mixPlan: plan,
          playlist: plan.playlist,
          transitions: plan.transition_plan,
          currentTrackIndex: -1,
          isGeneratingPlan: false,
        });
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          ?? 'Failed to generate mix plan';
        set({ isGeneratingPlan: false, error: msg });
      }
    },

    generateOfflineMix: async (userId, params) => {
      set({ isRenderingMix: true, error: null });
      try {
        const res = await mixApi.generateOfflineMix({ ...params, user_id: userId });
        const result = res.data.data;
        set({ offlineMix: result, mixPlan: result.mix_plan, isRenderingMix: false });
      } catch (err: unknown) {
        const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          ?? 'Failed to render mix';
        set({ isRenderingMix: false, error: msg });
      }
    },

    loadTrackFromPlan: async (index) => {
      const state = get();
      const track = state.playlist[index];
      if (!track) return;

      const processedFile = state.mixPlan?.processed_files[track.song_id];
      let url: string | null = null;
      if (processedFile) {
        const filename = processedFile.split('/').pop() ?? processedFile;
        url = getProcessedStreamUrl(filename);
      } else if (track.library_song_id) {
        url = getLibraryStreamUrl(track.library_song_id);
      }
      if (!url) {
        set({
          error:
            'No stream URL for this track (missing processed file and library_song_id). Re-generate the mix plan or re-import from library.',
        });
        return;
      }
      const deck: 'A' | 'B' = index % 2 === 0 ? 'A' : 'B';
      await engine.loadTrack(url, deck, track.song_id);
      set({ currentTrackIndex: index, activeDeck: deck, error: null });
    },

    loadProcessedTrack: async (filename) => {
      const url = getProcessedStreamUrl(filename);
      await engine.loadTrack(url, 'A', null);
      set({ currentTrackIndex: 0, activeDeck: 'A' });
    },

    clearError: () => set({ error: null }),
    reset: () => {
      engine.destroy();
      set({
        isPlaying: false,
        currentTime: 0,
        duration: 0,
        loopA: null,
        loopB: null,
        loopActive: false,
        mixPlan: null,
        playlist: [],
        currentTrackIndex: -1,
        transitions: [],
        offlineMix: null,
      });
    },
  };
});
