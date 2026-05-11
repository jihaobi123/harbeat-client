import { MixAudioEngine } from './MixAudioEngine';
import { getDevLibraryStreamUrl } from '../api/devMix';
import type { DjMixPlanResult, DjTransitionPlanItem, PlaylistSongData } from '../types/api';

export type MixSessionStateName = 'idle' | 'loading' | 'playing' | 'transitioning' | 'stopped' | 'error';

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

  setOnStateChange(cb: (snapshot: MixSessionSnapshot) => void): void {
    this.notify = cb;
    this.emit();
  }

  loadPlan(plan: DjMixPlanResult): void {
    this.stop();
    this.plan = plan;
    this.currentIndex = -1;
    this.state = 'idle';
    this.error = null;
    this.lastEvent = `plan loaded: ${plan.playlist.length} tracks`;
    this.decks = { A: emptyDeck('A'), B: emptyDeck('B') };
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
      this.state = 'playing';
      this.decks.A.state = 'playing';
      this.lastEvent = 'deck_play A @ 0.000s';
      await this.preloadNext();
      this.scheduleAutoTransition();
      this.emit();
      return;
    }

    const deck = this.physicalDeckForIndex(this.currentIndex);
    this.engine.play(deck, this.engine.getPosition(deck), 0);
    this.state = 'playing';
    this.decks[deck].state = 'playing';
    this.lastEvent = `resume deck ${deck}`;
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

  async next(manual = true): Promise<void> {
    if (!this.plan) {
      this.setError('No mix plan loaded.');
      return;
    }
    if (this.isTransitioning) {
      this.lastEvent = 'ignored next: already transitioning';
      this.emit();
      return;
    }
    if (this.currentIndex < 0) {
      await this.play();
      return;
    }
    if (this.currentIndex >= this.plan.playlist.length - 1) {
      this.lastEvent = 'end of playlist';
      this.emit();
      return;
    }

    const transition = this.findTransitionForCurrentPair();
    const nextIndex = this.currentIndex + 1;
    const outgoingDeck = this.physicalDeckForIndex(this.currentIndex);
    const incomingDeck = this.physicalDeckForIndex(nextIndex);

    this.clearAutoTransitionTimer();
    this.state = 'transitioning';
    this.isTransitioning = true;
    this.lastEvent = manual ? 'manual next: scheduling transition now' : 'auto transition';
    this.emit();

    try {
      await this.ensureTrackAt(nextIndex, incomingDeck);
      if (transition?.mix_control_timeline?.events?.length) {
        const timeline = manual
          ? { ...transition.mix_control_timeline, start_at_from_time_sec: this.engine.getPosition(outgoingDeck) }
          : transition.mix_control_timeline;
        await this.engine.scheduleMixControlTimeline({
          timeline,
          outgoingDeck,
          incomingDeck,
          resolveUrlForSongId: this.resolveUrlForSongId,
        });
        this.lastEvent = `timeline scheduled: ${outgoingDeck} → ${incomingDeck}`;
      } else {
        const entrySec = Math.max(0, transition?.entry_time_sec ?? 0);
        const crossfade = Math.max(2, transition?.crossfade_sec ?? 6);
        this.engine.play(incomingDeck, entrySec, crossfade);
        this.lastEvent = `fallback crossfade: ${outgoingDeck} → ${incomingDeck}`;
      }

      const crossfade = Math.max(2, transition?.crossfade_sec ?? transition?.mix_control_timeline?.duration_sec ?? 6);
      window.setTimeout(() => {
        this.currentIndex = nextIndex;
        this.state = 'playing';
        this.isTransitioning = false;
        this.decks[outgoingDeck].state = 'stopped';
        this.decks[incomingDeck].state = 'playing';
        this.decks[incomingDeck].playbackRate = transition?.tempo_ratio ?? 1;
        this.lastEvent = `transition complete: active deck ${incomingDeck}`;
        void this.preloadNext().then(() => this.scheduleAutoTransition());
        this.emit();
      }, crossfade * 1000 + 250);
    } catch (err) {
      this.setError(err instanceof Error ? err.message : String(err));
    }
  }

  getSnapshot(): MixSessionSnapshot {
    const currentTrack = this.plan?.playlist[this.currentIndex] ?? null;
    const nextTrack = this.plan?.playlist[this.currentIndex + 1] ?? null;
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
    };
  }

  private async preloadNext(): Promise<void> {
    if (!this.plan) return;
    const nextIndex = this.currentIndex + 1;
    if (nextIndex >= this.plan.playlist.length) return;
    await this.ensureTrackAt(nextIndex, this.physicalDeckForIndex(nextIndex));
  }

  private async ensureTrackAt(index: number, deck: 'A' | 'B'): Promise<void> {
    const track = this.plan?.playlist[index];
    if (!track) throw new Error(`No track at index ${index}`);
    if (this.decks[deck].songId === track.song_id && this.decks[deck].state !== 'empty') return;
    await this.loadTrackAt(index, deck);
  }

  private async loadTrackAt(index: number, deck: 'A' | 'B'): Promise<void> {
    const track = this.plan?.playlist[index];
    if (!track) throw new Error(`No track at index ${index}`);
    this.state = 'loading';
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

  private scheduleAutoTransition(): void {
    this.clearAutoTransitionTimer();
    if (!this.plan || this.currentIndex < 0 || this.currentIndex >= this.plan.playlist.length - 1) return;
    if (this.state !== 'playing') return;

    const transition = this.findTransitionForCurrentPair();
    const startAt = transition?.mix_control_timeline?.start_at_from_time_sec ?? transition?.exit_time_sec;
    if (startAt == null) return;

    const deck = this.physicalDeckForIndex(this.currentIndex);
    const currentPos = this.engine.getPosition(deck);
    const secondsUntil = Math.max(0.25, startAt - currentPos);
    this.autoTransitionTimer = window.setTimeout(() => {
      this.autoTransitionTimer = null;
      void this.next(false);
    }, secondsUntil * 1000);
    this.lastEvent = `auto transition armed in ${secondsUntil.toFixed(1)}s`;
    this.emit();
  }

  private findTransitionForCurrentPair(): DjTransitionPlanItem | null {
    if (!this.plan) return null;
    const from = this.plan.playlist[this.currentIndex];
    const to = this.plan.playlist[this.currentIndex + 1];
    if (!from || !to) return null;
    return this.plan.transition_plan.find((tr) => tr.from_song_id === from.song_id && tr.to_song_id === to.song_id)
      ?? this.plan.transition_plan[this.currentIndex]
      ?? null;
  }

  private physicalDeckForIndex(index: number): 'A' | 'B' {
    return index % 2 === 0 ? 'A' : 'B';
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
