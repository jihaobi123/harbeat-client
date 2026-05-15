import { MixAudioEngine } from './MixAudioEngine';
import { getDevLibraryStreamUrl } from '../api/devMix';
import type { DjMixPlanResult, DjTransitionPlanItem, MixControlTimeline, PlaylistSongData } from '../types/api';

export type MixSessionStateName = 'idle' | 'loading' | 'preparing' | 'playing' | 'transitioning' | 'stopped' | 'error';
export type MixStrategy = 'clean_blend' | 'fade' | 'echo_out' | 'riser' | 'cut_swap' | 'hard_cut' | 'triplet_swap' | 'melodic_reset';
export type PlanMode = 'random' | 'camelot' | 'energy';
export type EnergyPreference = 'none' | 'higher' | 'lower';

const MANUAL_SWITCH_WINDOW_MS = 2000;
const MANUAL_SWITCH_THRESHOLD = 3;

export interface DeckRuntimeView {
  deck: 'A' | 'B';
  songId: number | null;
  title: string;
  state: 'empty' | 'loaded' | 'playing' | 'stopped';
  playbackRate: number;
}

export interface MixSessionSnapshot {
  state: MixSessionStateName;
  currentIndex: number;
  activeDeck: 'A' | 'B';
  currentTrack: PlaylistSongData | null;
  nextTrack: PlaylistSongData | null;
  transitionIndex: number;
  isTransitioning: boolean;
  lastEvent: string;
  error: string | null;
  decks: Record<'A' | 'B', DeckRuntimeView>;
  pendingManualStrategy: MixStrategy | null;
  effectiveTransitionStrategy: string | null;
  fallbackMode: boolean;
  fallbackReason: string | null;
  loopBars: 8 | 16 | 32 | null;
  planMode: PlanMode;
  energyPreference: EnergyPreference;
  isLoopMode: boolean;
  /** True when the engine is actually looping the A→B segment (after Play in loop edit mode). */
  isLoopCyclePlayback: boolean;
  currentTimeSec: number;
  durationSec: number;
  loopStartSec: number | null;
  loopEndSec: number | null;
  /** Last completed transition: plan score + technique used for playback. */
  lastMixScore: number | null;
  lastMixPlanTechnique: string | null;
  lastMixPlaybackTechnique: string | null;
  lastMixPlaybackPath: 'timeline' | 'fade_mode' | null;
}

function emptyDeck(deck: 'A' | 'B'): DeckRuntimeView {
  return { deck, songId: null, title: 'Empty', state: 'empty', playbackRate: 1 };
}

export class MixSessionController {
  private engine = MixAudioEngine.getInstance();
  private plan: DjMixPlanResult | null = null;
  private currentIndex = -1;
  private state: MixSessionStateName = 'idle';
  private isTransitioning = false;
  private lastEvent = 'idle';
  private error: string | null = null;
  private decks: Record<'A' | 'B', DeckRuntimeView> = { A: emptyDeck('A'), B: emptyDeck('B') };
  private notify: ((snapshot: MixSessionSnapshot) => void) | null = null;
  private autoTransitionTimer: number | null = null;
  private pendingManualStrategy: MixStrategy | null = null;
  private manualSwitchTimestamps: number[] = [];
  private effectiveTransitionStrategy: string | null = null;
  private fallbackMode = false;
  private fallbackReason: string | null = null;
  private loopBars: 8 | 16 | 32 | null = null;
  private planMode: PlanMode = 'random';
  private energyPreference: EnergyPreference = 'none';
  private playedSongIds = new Set<number>();
  private isLoopMode = false;
  private isLoopCyclePlayback = false;
  private loopStartSec: number | null = null;
  private loopEndSec: number | null = null;
  private currentTimeSec = 0;
  private durationSec = 0;
  private lastMixScore: number | null = null;
  private lastMixPlanTechnique: string | null = null;
  private lastMixPlaybackTechnique: string | null = null;
  private lastMixPlaybackPath: 'timeline' | 'fade_mode' | null = null;

  setOnStateChange(cb: (snapshot: MixSessionSnapshot) => void): void {
    this.notify = cb;
    this.engine.setOnTimeUpdate((time, duration) => {
      this.currentTimeSec = time;
      this.durationSec = duration;
      this.emit();
    });
    this.emit();
  }

  loadPlan(plan: DjMixPlanResult): void {
    this.stop();
    this.plan = plan;
    this.reorderPlanByMode();
    this.currentIndex = -1;
    this.state = 'idle';
    this.error = null;
    this.pendingManualStrategy = null;
    this.manualSwitchTimestamps = [];
    this.effectiveTransitionStrategy = null;
    this.fallbackMode = false;
    this.fallbackReason = null;
    this.playedSongIds = new Set<number>();
    this.lastEvent = `plan loaded: ${this.plan.playlist.length} tracks (${this.planMode})`;
    this.decks = { A: emptyDeck('A'), B: emptyDeck('B') };
    this.isLoopMode = false;
    this.isLoopCyclePlayback = false;
    this.loopStartSec = null;
    this.loopEndSec = null;
    this.lastMixScore = null;
    this.lastMixPlanTechnique = null;
    this.lastMixPlaybackTechnique = null;
    this.lastMixPlaybackPath = null;
    this.emit();
  }

  setManualStrategy(strategy: MixStrategy): void {
    this.pendingManualStrategy = strategy;
    this.lastEvent = `manual strategy selected: ${strategy}`;
    this.emit();
  }

  setPlanMode(mode: PlanMode): void {
    this.planMode = mode;
    if (this.plan) {
      this.reorderPlanByMode();
      this.currentIndex = -1;
      this.state = 'idle';
      this.decks = { A: emptyDeck('A'), B: emptyDeck('B') };
      this.lastEvent = `plan mode switched: ${mode}`;
    }
    this.emit();
  }

  /** 仅同步 UI 的 Plan Mode（不重置当前 plan），在 Generate 前调用；`loadPlan` 会按该模式对返回的 playlist 再排序。 */
  syncPlanModeFromUi(mode: PlanMode): void {
    this.planMode = mode;
    this.emit();
  }

  setEnergyPreference(preference: EnergyPreference): void {
    this.energyPreference = preference;
    this.lastEvent = `energy preference: ${preference}`;
    this.emit();
  }

  previous(): void {
    if (!this.plan || this.plan.playlist.length === 0) return;
    const target = Math.max(0, this.currentIndex <= 0 ? 0 : this.currentIndex - 1);
    void this.jumpToIndex(target);
  }

  skipToNextTrack(): void {
    if (!this.plan || this.plan.playlist.length === 0) return;
    const target = Math.min(this.plan.playlist.length - 1, this.currentIndex < 0 ? 0 : this.currentIndex + 1);
    void this.jumpToIndex(target);
  }

  setLoopByBars(bars: 8 | 16 | 32): void {
    if (!this.plan || this.currentIndex < 0) return;
    const deck = this.physicalDeckForIndex(this.currentIndex);
    const bpm = Math.max(60, this.plan.playlist[this.currentIndex]?.bpm ?? 120);
    const secPerBeat = 60 / bpm;
    const secPerBar = secPerBeat * 4;
    const start = this.engine.getPosition(deck);
    const end = start + bars * secPerBar;
    this.engine.setLoopPoints(start, end);
    this.engine.setLoopActive(true);
    this.loopBars = bars;
    this.isLoopCyclePlayback = true;
    this.lastEvent = `loop set: ${bars} bars`;
    this.emit();
  }

  clearLoop(): void {
    this.engine.clearLoop();
    this.loopBars = null;
    this.isLoopMode = false;
    this.isLoopCyclePlayback = false;
    this.loopStartSec = null;
    this.loopEndSec = null;
    this.lastEvent = 'loop cleared';
    this.emit();
  }

  toggleLoopMode(): void {
    if (!this.plan || this.currentIndex < 0) return;
    this.isLoopMode = !this.isLoopMode;
    if (this.isLoopMode) {
      this.isLoopCyclePlayback = false;
      this.loopStartSec = null;
      this.loopEndSec = null;
      this.engine.clearLoop();
      this.lastEvent = 'loop 编辑：请 Set Start / Set End，再按 Play 开始区间循环（再按 Play 退出循环）';
    } else {
      this.loopStartSec = null;
      this.loopEndSec = null;
      this.loopBars = null;
      this.isLoopCyclePlayback = false;
      this.clearAutoTransitionTimer();
      this.engine.cancelScheduledTimeline();
      this.engine.clearLoop();

      const deck = this.physicalDeckForIndex(this.currentIndex);
      const other: 'A' | 'B' = deck === 'A' ? 'B' : 'A';
      this.engine.silenceDeckImmediate(other);
      this.engine.seek(deck, 0, true);

      this.state = 'playing';
      this.isTransitioning = false;
      this.decks[deck].state = 'playing';
      if (this.decks[other].state === 'playing') {
        this.decks[other].state = 'stopped';
      }

      this.lastEvent = 'loop 已关：当前曲从头播放，已恢复自动接歌/混音时间轴';
      void this.prepareUpcomingTransition('loop-mode-off');
    }
    this.emit();
  }

  setLoopStartFromCurrent(): void {
    if (!this.plan || this.currentIndex < 0) return;
    const deck = this.physicalDeckForIndex(this.currentIndex);
    const pos = this.engine.getPosition(deck);
    this.loopStartSec = pos;
    if (this.loopEndSec != null && this.loopEndSec <= this.loopStartSec + 0.1) {
      this.loopEndSec = this.loopStartSec + 0.1;
    }
    this.applyLoopPointsIfActive();
    this.lastEvent = `loop start set @ ${pos.toFixed(1)}s`;
    this.emit();
  }

  setLoopEndFromCurrent(): void {
    if (!this.plan || this.currentIndex < 0) return;
    const deck = this.physicalDeckForIndex(this.currentIndex);
    const pos = this.engine.getPosition(deck);
    this.loopEndSec = pos;
    if (this.loopStartSec == null) {
      this.loopStartSec = Math.max(0, pos - 8);
    }
    if (this.loopEndSec <= this.loopStartSec + 0.1) {
      this.loopEndSec = this.loopStartSec + 0.1;
    }
    this.applyLoopPointsIfActive();
    this.lastEvent = `loop end set @ ${this.loopEndSec.toFixed(1)}s`;
    this.emit();
  }

  async loopLastSeconds(seconds = 30): Promise<void> {
    if (!this.plan || this.currentIndex < 0) return;
    const deck = this.physicalDeckForIndex(this.currentIndex);
    const pos = Math.max(0, this.engine.getPosition(deck));
    const span = Math.max(2, seconds);
    if (!this.isLoopMode) this.toggleLoopMode();
    this.loopStartSec = Math.max(0, pos - span);
    this.loopEndSec = Math.max(this.loopStartSec + 0.5, pos);
    this.lastEvent = `quick loop: last ${span.toFixed(0)}s @ ${this.loopStartSec.toFixed(1)}→${this.loopEndSec.toFixed(1)}`;
    this.emit();
    await this.play();
  }

  private applyLoopPointsIfActive(): void {
    if (!this.isLoopCyclePlayback || !this.isLoopMode || this.loopStartSec == null || this.loopEndSec == null) return;
    this.engine.clearLoop();
    this.engine.setLoopPoints(this.loopStartSec, this.loopEndSec);
    this.engine.setLoopActive(true);
  }

  seekCurrent(timeSec: number): void {
    if (!this.plan || this.currentIndex < 0 || !this.isLoopMode) return;
    const deck = this.physicalDeckForIndex(this.currentIndex);
    this.engine.seek(deck, timeSec, true);
    this.currentTimeSec = timeSec;
    this.lastEvent = `seek @ ${timeSec.toFixed(1)}s`;
    this.emit();
  }

  async play(): Promise<void> {
    if (!this.plan || this.plan.playlist.length === 0) {
      this.setError('No mix plan loaded.');
      return;
    }

    if (this.currentIndex < 0) {
      await this.loadTrackAt(0, 'A');
      this.engine.play('A', 0, 0);
      this.currentIndex = 0;
      const firstSongId = this.plan.playlist[0]?.song_id;
      if (firstSongId != null) this.playedSongIds.add(firstSongId);
      this.state = 'playing';
      this.decks.A.state = 'playing';
      this.lastEvent = 'deck_play A @ 0.000s';
      void this.prepareUpcomingTransition('play-start');
      this.emit();
      return;
    }

    const deck = this.physicalDeckForIndex(this.currentIndex);
    const loop_range_ready =
      this.isLoopMode &&
      this.loopStartSec != null &&
      this.loopEndSec != null &&
      this.loopEndSec > this.loopStartSec + 0.1;

    if (loop_range_ready) {
      if (this.isLoopCyclePlayback) {
        this.engine.clearLoop();
        this.isLoopCyclePlayback = false;
        this.clearAutoTransitionTimer();
        void this.prepareUpcomingTransition('loop-exit');
        this.lastEvent = '已退出区间循环，恢复正常接歌时间轴';
      } else {
        this.clearAutoTransitionTimer();
        this.engine.cancelScheduledTimeline();
        this.engine.clearLoop();
        const other: 'A' | 'B' = deck === 'A' ? 'B' : 'A';
        this.engine.silenceDeckImmediate(other);
        const loop_a = this.loopStartSec!;
        const loop_b = this.loopEndSec!;
        this.engine.seek(deck, loop_a);
        this.engine.setLoopPoints(loop_a, loop_b);
        this.engine.setLoopActive(true);
        this.isLoopCyclePlayback = true;
        this.lastEvent = `区间循环播放：${loop_a.toFixed(1)}s → ${loop_b.toFixed(1)}s（仅 Deck ${deck}）`;
      }
      this.state = 'playing';
      this.decks[deck].state = 'playing';
      this.emit();
      return;
    }

    this.engine.play(deck, this.engine.getPosition(deck), 0);
    this.state = 'playing';
    this.decks[deck].state = 'playing';
    this.lastEvent = `resume deck ${deck}`;
    void this.prepareUpcomingTransition('resume');
    this.emit();
  }

  pause(): void {
    const deck = this.physicalDeckForIndex(this.currentIndex);
    this.engine.pause(deck);
    this.state = 'stopped';
    if (deck) this.decks[deck].state = 'stopped';
    this.lastEvent = `pause deck ${deck}`;
    this.emit();
  }

  stop(): void {
    this.clearAutoTransitionTimer();
    this.engine.cancelScheduledTimeline();
    this.engine.clearLoop();
    this.isLoopCyclePlayback = false;
    this.engine.pause('A');
    this.engine.pause('B');
    this.state = 'stopped';
    this.isTransitioning = false;
    for (const deck of ['A', 'B'] as const) {
      if (this.decks[deck].state === 'playing') this.decks[deck].state = 'stopped';
    }
    this.lastEvent = 'stop session';
    this.emit();
  }

  async next(manual = true, strategy?: MixStrategy): Promise<void> {
    if (!this.plan) {
      this.setError('No mix plan loaded.');
      return;
    }
    if (this.isTransitioning) {
      this.lastEvent = 'manual pressure detected during transition: keeping current audio and using fallback if needed';
      if (manual) this.recordManualSwitch();
      this.emit();
      return;
    }
    if (this.currentIndex < 0) {
      await this.play();
      return;
    }
    if (this.currentIndex >= this.plan.playlist.length - 1 && this.planMode !== 'random') {
      this.lastEvent = 'end of playlist';
      this.emit();
      return;
    }

    if (this.isLoopCyclePlayback) {
      this.engine.clearLoop();
      this.isLoopCyclePlayback = false;
    }

    if (manual) {
      this.recordManualSwitch();
      this.pendingManualStrategy = strategy ?? this.pendingManualStrategy;
    }

    const nextIndex = this.resolveNextIndex();
    if (nextIndex === null || nextIndex === this.currentIndex) {
      this.lastEvent = 'no valid next track under current mode/preference';
      this.emit();
      return;
    }

    const transition = this.findTransitionForPair(this.currentIndex, nextIndex);
    const selectedStrategy = manual ? this.pendingManualStrategy : null;
    const shouldUseTimeline = this.shouldUsePlannedTimeline(transition, manual, selectedStrategy);
    const outgoingDeck = this.physicalDeckForIndex(this.currentIndex);
    const incomingDeck = this.physicalDeckForIndex(nextIndex);
    const planScore = transition?.score ?? null;
    const planTechnique = transition?.transition_technique ?? null;

    this.clearAutoTransitionTimer();
    this.state = 'transitioning';
    this.isTransitioning = true;
    this.effectiveTransitionStrategy = shouldUseTimeline
      ? selectedStrategy ?? transition?.transition_technique ?? 'auto'
      : 'fade_mode';
    this.lastEvent = manual
      ? `manual next: ${selectedStrategy ?? 'auto'}${shouldUseTimeline ? '' : ' → fade_mode'}`
      : `auto transition${shouldUseTimeline ? '' : ' → fade_mode'}`;
    this.emit();

    try {
      await this.ensureTrackAt(nextIndex, incomingDeck);
      if (shouldUseTimeline && transition?.mix_control_timeline?.events?.length) {
        const timeline = manual
          ? this.buildManualTimeline(transition, selectedStrategy ?? 'clean_blend', this.engine.getPosition(outgoingDeck))
          : transition.mix_control_timeline;
        await this.engine.scheduleMixControlTimeline({
          timeline,
          outgoingDeck,
          incomingDeck,
          resolveUrlForSongId: this.resolveUrlForSongId,
        });
        this.lastEvent = `timeline scheduled: ${outgoingDeck} → ${incomingDeck} (${this.effectiveTransitionStrategy})`;
      } else {
        const entrySec = Math.max(0, transition?.entry_time_sec ?? 0);
        this.engine.play(incomingDeck, entrySec, 4);
        this.lastEvent = `fade_mode crossfade: ${outgoingDeck} → ${incomingDeck} (${this.fallbackReason ?? 'safe fallback'})`;
      }

      const crossfade = shouldUseTimeline
        ? manual && transition
          ? this.strategyDuration(selectedStrategy ?? 'clean_blend', transition.crossfade_sec ?? transition.mix_control_timeline?.duration_sec ?? 6)
          : Math.max(2, transition?.crossfade_sec ?? transition?.mix_control_timeline?.duration_sec ?? 6)
        : 4;
      window.setTimeout(() => {
        this.currentIndex = nextIndex;
        const nextSongId = this.plan?.playlist[nextIndex]?.song_id;
        if (nextSongId != null) this.playedSongIds.add(nextSongId);
        this.state = 'playing';
        this.isTransitioning = false;
        this.decks[outgoingDeck].state = 'stopped';
        this.decks[incomingDeck].state = 'playing';
        this.pendingManualStrategy = null;
        this.decks[incomingDeck].playbackRate = shouldUseTimeline ? transition?.tempo_ratio ?? 1 : 1;
        this.lastMixScore = planScore;
        this.lastMixPlanTechnique = planTechnique;
        this.lastMixPlaybackPath = shouldUseTimeline ? 'timeline' : 'fade_mode';
        this.lastMixPlaybackTechnique = this.effectiveTransitionStrategy;
        this.lastEvent = `transition complete: active deck ${incomingDeck}`;
        void this.prepareUpcomingTransition('handoff');
        this.emit();
      }, crossfade * 1000 + 250);
    } catch (err) {
      this.setError(err instanceof Error ? err.message : String(err));
    }
  }

  getSnapshot(): MixSessionSnapshot {
    const currentTrack = this.plan?.playlist[this.currentIndex] ?? null;
    const nextIndex = this.resolveNextIndex();
    const nextTrack = nextIndex == null ? null : (this.plan?.playlist[nextIndex] ?? null);
    return {
      state: this.state,
      currentIndex: this.currentIndex,
      activeDeck: this.engine.getActiveDeck(),
      currentTrack,
      nextTrack,
      transitionIndex: Math.max(0, this.currentIndex),
      isTransitioning: this.isTransitioning,
      lastEvent: this.lastEvent,
      error: this.error,
      decks: this.decks,
      pendingManualStrategy: this.pendingManualStrategy,
      effectiveTransitionStrategy: this.effectiveTransitionStrategy,
      fallbackMode: this.fallbackMode,
      fallbackReason: this.fallbackReason,
      loopBars: this.loopBars,
      planMode: this.planMode,
      energyPreference: this.energyPreference,
      isLoopMode: this.isLoopMode,
      isLoopCyclePlayback: this.isLoopCyclePlayback,
      currentTimeSec: this.currentTimeSec,
      durationSec: this.durationSec,
      loopStartSec: this.loopStartSec,
      loopEndSec: this.loopEndSec,
      lastMixScore: this.lastMixScore,
      lastMixPlanTechnique: this.lastMixPlanTechnique,
      lastMixPlaybackTechnique: this.lastMixPlaybackTechnique,
      lastMixPlaybackPath: this.lastMixPlaybackPath,
    };
  }

  private async prepareUpcomingTransition(reason: string): Promise<void> {
    if (this.isLoopCyclePlayback) return;
    if (!this.plan || this.currentIndex < 0 || this.currentIndex >= this.plan.playlist.length - 1) return;
    const keepState = this.state;
    try {
      await this.preloadNext(false);
      if (this.state === 'loading' || this.state === 'preparing') this.state = keepState;
      this.scheduleAutoTransition(reason);
    } catch (err) {
      if (this.state === 'loading' || this.state === 'preparing') this.state = keepState;
      this.fallbackMode = true;
      this.fallbackReason = 'render_not_ready';
      this.lastEvent = `prepare next failed: ${err instanceof Error ? err.message : String(err)}; fade_mode will be used`;
      this.scheduleAutoTransition(reason);
      this.emit();
    }
  }

  private async preloadNext(affectState = true): Promise<void> {
    if (!this.plan) return;
    const nextIndex = this.currentIndex + 1;
    if (nextIndex >= this.plan.playlist.length) return;
    await this.ensureTrackAt(nextIndex, this.physicalDeckForIndex(nextIndex), affectState);
  }

  private async ensureTrackAt(index: number, deck: 'A' | 'B', affectState = true): Promise<void> {
    const track = this.plan?.playlist[index];
    if (!track) throw new Error(`No track at index ${index}`);
    if (this.decks[deck].songId === track.song_id && this.decks[deck].state !== 'empty') return;
    await this.loadTrackAt(index, deck, affectState);
  }

  private async loadTrackAt(index: number, deck: 'A' | 'B', affectState = true): Promise<void> {
    const track = this.plan?.playlist[index];
    if (!track) throw new Error(`No track at index ${index}`);
    const previousState = this.state;
    if (affectState) this.state = 'loading';
    else if (this.state !== 'playing') this.state = 'preparing';
    this.lastEvent = `deck_load ${deck}: ${track.title}`;
    this.emit();
    const url = this.resolveTrackUrl(track);
    await this.engine.loadTrack(url, deck, track.song_id);
    this.decks[deck] = {
      deck,
      songId: track.song_id,
      title: track.title,
      state: 'loaded',
      playbackRate: 1,
    };
    if (!affectState) this.state = previousState;
    this.lastEvent = `deck_loaded ${deck}: ${track.title}`;
    this.emit();
  }

  private resolveTrackUrl(track: PlaylistSongData): string {
    if (track.library_song_id) return getDevLibraryStreamUrl(track.library_song_id);
    const source = this.plan?.playlist.find((item) => item.song_id === track.song_id);
    if (source?.library_song_id) return getDevLibraryStreamUrl(source.library_song_id);
    throw new Error(`Missing library stream URL for song_id=${track.song_id}`);
  }

  private resolveUrlForSongId = async (songId: number): Promise<string> => {
    const track = this.plan?.playlist.find((item) => item.song_id === songId);
    if (!track) throw new Error(`song_id=${songId} not in current plan`);
    return this.resolveTrackUrl(track);
  };

  private clearAutoTransitionTimer(): void {
    if (this.autoTransitionTimer !== null) {
      window.clearTimeout(this.autoTransitionTimer);
      this.autoTransitionTimer = null;
    }
  }

  private scheduleAutoTransition(reason = 'auto'): void {
    this.clearAutoTransitionTimer();
    if (this.isLoopCyclePlayback) return;
    if (!this.plan || this.currentIndex < 0 || this.currentIndex >= this.plan.playlist.length - 1) return;
    if (this.state !== 'playing') return;

    const transition = this.findTransitionForCurrentPair();
    const fallbackStart = this.engine.getDuration(this.physicalDeckForIndex(this.currentIndex)) - Math.max(4, transition?.crossfade_sec ?? 6);
    const startAt = transition?.mix_control_timeline?.start_at_from_time_sec ?? transition?.exit_time_sec ?? fallbackStart;
    if (startAt == null || Number.isNaN(startAt)) return;

    const deck = this.physicalDeckForIndex(this.currentIndex);
    const currentPos = this.engine.getPosition(deck);
    const secondsUntil = Math.max(0.25, startAt - currentPos);
    this.autoTransitionTimer = window.setTimeout(() => {
      this.autoTransitionTimer = null;
      void this.next(false);
    }, secondsUntil * 1000);
    this.lastEvent = `cue prepared (${reason}): auto transition in ${secondsUntil.toFixed(1)}s`;
    this.emit();
  }

  private findTransitionForCurrentPair(): DjTransitionPlanItem | null {
    const nextIndex = this.resolveNextIndex();
    if (nextIndex == null) return null;
    return this.findTransitionForPair(this.currentIndex, nextIndex);
  }

  private findTransitionForPair(fromIndex: number, toIndex: number): DjTransitionPlanItem | null {
    if (!this.plan) return null;
    const from = this.plan.playlist[fromIndex];
    const to = this.plan.playlist[toIndex];
    if (!from || !to) return null;
    return this.plan.transition_plan.find((tr) => tr.from_song_id === from.song_id && tr.to_song_id === to.song_id)
      ?? this.plan.transition_plan[Math.max(0, fromIndex)]
      ?? null;
  }

  private resolveNextIndex(): number | null {
    if (!this.plan || this.currentIndex < 0) return null;
    if (this.planMode !== 'random') {
      const i = this.currentIndex + 1;
      return i < this.plan.playlist.length ? i : null;
    }

    const current = this.plan.playlist[this.currentIndex];
    if (!current) return null;
    const curBpm = current.bpm ?? 120;
    const curEnergy = Number(current.energy ?? 0.5);

    let candidates = this.plan.playlist
      .map((track, idx) => ({ track, idx }))
      .filter(({ idx }) => idx !== this.currentIndex)
      .filter(({ track }) => {
        if (this.energyPreference === 'higher') return Number(track.energy ?? 0.5) > curEnergy;
        if (this.energyPreference === 'lower') return Number(track.energy ?? 0.5) < curEnergy;
        return true;
      })
      .filter(({ track }) => !this.playedSongIds.has(track.song_id));

    if (!candidates.length) {
      // 若全部播放过，则重置一轮（保留当前曲，避免立即重复）
      this.playedSongIds.clear();
      this.playedSongIds.add(current.song_id);
      candidates = this.plan.playlist
        .map((track, idx) => ({ track, idx }))
        .filter(({ idx }) => idx !== this.currentIndex)
        .filter(({ track }) => {
          if (this.energyPreference === 'higher') return Number(track.energy ?? 0.5) > curEnergy;
          if (this.energyPreference === 'lower') return Number(track.energy ?? 0.5) < curEnergy;
          return true;
        })
        .filter(({ track }) => !this.playedSongIds.has(track.song_id));
    }

    if (!candidates.length) return null;

    candidates.sort((a, b) => Math.abs((a.track.bpm ?? 120) - curBpm) - Math.abs((b.track.bpm ?? 120) - curBpm));
    return candidates[0]?.idx ?? null;
  }

  private reorderPlanByMode(): void {
    if (!this.plan) return;
    if (this.planMode === 'random') return;

    const playlist = [...this.plan.playlist];
    if (this.planMode === 'camelot') {
      const parseCamelot = (track: PlaylistSongData) => {
        const key = (track.key ?? '').toUpperCase();
        const m = key.match(/(\d+)([AB])/);
        return m ? { n: Number(m[1]), l: m[2] } : { n: 99, l: 'Z' };
      };
      playlist.sort((a, b) => {
        const ka = parseCamelot(a);
        const kb = parseCamelot(b);
        if (ka.n !== kb.n) return ka.n - kb.n;
        return ka.l.localeCompare(kb.l);
      });
    } else if (this.planMode === 'energy') {
      playlist.sort((a, b) => Number(a.energy ?? 0) - Number(b.energy ?? 0));
    }

    this.plan = { ...this.plan, playlist };
  }

  private shouldUsePlannedTimeline(
    transition: DjTransitionPlanItem | null,
    manual: boolean,
    selectedStrategy: MixStrategy | null,
  ): boolean {
    this.fallbackMode = false;
    this.fallbackReason = null;

    if (!transition?.mix_control_timeline?.events?.length) {
      if (manual) {
        this.lastEvent = 'manual requested before render was ready; fade_mode will be used';
      }
      this.fallbackMode = true;
      this.fallbackReason = 'render_not_ready';
      return false;
    }

    if (manual && this.isRapidManualSwitching()) {
      this.fallbackMode = true;
      this.fallbackReason = 'rapid_manual_switch';
      return false;
    }

    if (!manual && transition.transition_technique) {
      this.effectiveTransitionStrategy = transition.transition_technique;
    }

    if (manual && selectedStrategy && transition.transition_technique !== selectedStrategy) {
      this.lastEvent = `manual strategy ${selectedStrategy} will be rendered from base timeline`;
    }

    return true;
  }

  private buildManualTimeline(
    transition: DjTransitionPlanItem,
    strategy: MixStrategy,
    startAtFromTimeSec: number,
  ): MixControlTimeline {
    const base = transition.mix_control_timeline;
    if (!base) throw new Error('Missing base mix timeline');

    const duration = this.strategyDuration(strategy, transition.crossfade_sec ?? base.duration_sec ?? 6);
    const entry = Math.max(0, transition.entry_time_sec ?? this.findIncomingEntry(base));
    const rate = Math.max(0.85, Math.min(1.15, transition.tempo_ratio ?? 1));
    return {
      ...base,
      transition_id: `${base.transition_id ?? 'manual'}-${strategy}`,
      mode: strategy === 'cut_swap' || strategy === 'hard_cut' || strategy === 'melodic_reset' ? 'hard_cut' : 'normal_crossfade',
      start_at_from_time_sec: startAtFromTimeSec,
      duration_sec: duration,
      events: this.strategyEvents(strategy, duration, transition.to_song_id, entry, rate),
    };
  }

  private strategyDuration(strategy: MixStrategy, baseDuration: number): number {
    const base = Math.max(2, baseDuration || 6);
    if (strategy === 'cut_swap' || strategy === 'hard_cut') return 2;
    if (strategy === 'triplet_swap') return Math.max(3, Math.min(5, base * 0.65));
    if (strategy === 'echo_out' || strategy === 'melodic_reset') return Math.max(4, Math.min(6, base));
    if (strategy === 'riser') return Math.max(6, Math.min(10, base));
    if (strategy === 'fade') return Math.max(8, Math.min(12, base * 1.3));
    return Math.max(6, Math.min(10, base));
  }

  private findIncomingEntry(timeline: MixControlTimeline): number {
    const deckPlay = timeline.events.find((ev) => ev.type === 'deck_play' && ev.deck === 'B');
    return Math.max(0, deckPlay && deckPlay.type === 'deck_play' ? deckPlay.position_sec ?? 0 : 0);
  }

  private strategyEvents(strategy: MixStrategy, duration: number, toSongId: number, entry: number, rate: number): MixControlTimeline['events'] {
    const play = [
      { type: 'deck_load' as const, deck: 'B' as const, time_sec: -4, song_id: toSongId, position_sec: entry },
      { type: 'param_set' as const, deck: 'A' as const, time_sec: -0.02, param: 'gain' as const, value: 1 },
      { type: 'param_set' as const, deck: 'B' as const, time_sec: -0.02, param: 'gain' as const, value: 0 },
      { type: 'deck_play' as const, deck: 'B' as const, time_sec: 0, position_sec: entry, playback_rate: rate, key_lock: false },
    ];
    const stop = { type: 'deck_stop' as const, deck: 'A' as const, time_sec: duration + 0.1 };

    if (strategy === 'cut_swap' || strategy === 'hard_cut') {
      return [
        ...play,
        { type: 'param_set' as const, deck: 'A' as const, time_sec: 0, param: 'gain' as const, value: 0 },
        { type: 'param_set' as const, deck: 'B' as const, time_sec: 0, param: 'gain' as const, value: 1 },
        stop,
      ];
    }

    if (strategy === 'echo_out') {
      return [
        ...play,
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: duration, param: 'gain' as const, from: 1, to: 0, curve: 'equal_power_out' as const },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: duration, param: 'gain' as const, from: 0, to: 1, curve: 'equal_power_in' as const },
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: duration, param: 'lowpass_hz' as const, from: 20000, to: 1800, curve: 'ease_in_out' as const },
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: duration * 0.35, duration_sec: duration * 0.65, param: 'high_eq' as const, from: 1, to: 0.25, curve: 'ease_in_out' as const },
        stop,
      ];
    }

    if (strategy === 'riser') {
      return [
        ...play,
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: duration, param: 'gain' as const, from: 1, to: 0, curve: 'equal_power_out' as const },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: duration, param: 'gain' as const, from: 0, to: 1, curve: 'equal_power_in' as const },
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: duration, param: 'highpass_hz' as const, from: 20, to: 1200, curve: 'ease_in_out' as const },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: duration, param: 'lowpass_hz' as const, from: 3500, to: 20000, curve: 'ease_in_out' as const },
        stop,
      ];
    }

    if (strategy === 'triplet_swap') {
      const step = duration / 3;
      return [
        ...play,
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: step, param: 'gain' as const, from: 1, to: 0.62, curve: 'linear' as const },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: step, param: 'gain' as const, from: 0, to: 0.45, curve: 'linear' as const },
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: step, duration_sec: step, param: 'gain' as const, from: 0.62, to: 0.25, curve: 'linear' as const },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: step, duration_sec: step, param: 'gain' as const, from: 0.45, to: 0.8, curve: 'linear' as const },
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: step * 2, duration_sec: step, param: 'gain' as const, from: 0.25, to: 0, curve: 'linear' as const },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: step * 2, duration_sec: step, param: 'gain' as const, from: 0.8, to: 1, curve: 'linear' as const },
        stop,
      ];
    }

    if (strategy === 'melodic_reset') {
      return [
        ...play,
        { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: Math.max(0.6, duration * 0.35), param: 'gain' as const, from: 1, to: 0, curve: 'ease_in_out' as const },
        { type: 'param_set' as const, deck: 'B' as const, time_sec: Math.max(0.6, duration * 0.35), param: 'gain' as const, value: 1 },
        { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: Math.max(0.6, duration * 0.35), param: 'lowpass_hz' as const, from: 2400, to: 20000, curve: 'ease_in_out' as const },
        stop,
      ];
    }

    return [
      ...play,
      { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: duration, param: 'gain' as const, from: 1, to: 0, curve: 'equal_power_out' as const },
      { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: duration, param: 'gain' as const, from: 0, to: 1, curve: 'equal_power_in' as const },
      { type: 'param_ramp' as const, deck: 'A' as const, time_sec: 0, duration_sec: duration, param: 'low_eq' as const, from: 1, to: 0.35, curve: 'ease_in_out' as const },
      { type: 'param_ramp' as const, deck: 'B' as const, time_sec: 0, duration_sec: duration, param: 'low_eq' as const, from: 0.45, to: 1, curve: 'ease_in_out' as const },
      stop,
    ];
  }

  private recordManualSwitch(): void {
    const now = Date.now();
    const cutoff = now - MANUAL_SWITCH_WINDOW_MS;
    this.manualSwitchTimestamps = [...this.manualSwitchTimestamps, now].filter((ts) => ts >= cutoff);
  }

  private isRapidManualSwitching(): boolean {
    const cutoff = Date.now() - MANUAL_SWITCH_WINDOW_MS;
    this.manualSwitchTimestamps = this.manualSwitchTimestamps.filter((ts) => ts >= cutoff);
    return this.manualSwitchTimestamps.length >= MANUAL_SWITCH_THRESHOLD;
  }

  private physicalDeckForIndex(index: number): 'A' | 'B' {
    return index % 2 === 0 ? 'A' : 'B';
  }

  private async jumpToIndex(index: number): Promise<void> {
    if (!this.plan) return;
    if (index < 0 || index >= this.plan.playlist.length) return;
    this.clearAutoTransitionTimer();
    this.engine.cancelScheduledTimeline();
    this.engine.pause('A');
    this.engine.pause('B');
    this.engine.clearLoop();
    this.loopBars = null;
    this.isLoopCyclePlayback = false;

    const deck = this.physicalDeckForIndex(index);
    await this.loadTrackAt(index, deck, false);
    this.engine.play(deck, 0, 0);
    this.currentIndex = index;
    this.state = 'playing';
    this.isTransitioning = false;
    this.decks.A.state = deck === 'A' ? 'playing' : 'stopped';
    this.decks.B.state = deck === 'B' ? 'playing' : 'stopped';
    this.lastEvent = `jump to ${index + 1}: ${this.plan.playlist[index].title}`;
    void this.prepareUpcomingTransition('jump');
    this.emit();
  }

  private setError(message: string): void {
    this.error = message;
    this.state = 'error';
    this.isTransitioning = false;
    this.lastEvent = `error: ${message}`;
    this.emit();
  }

  private emit(): void {
    this.notify?.(this.getSnapshot());
  }
}
