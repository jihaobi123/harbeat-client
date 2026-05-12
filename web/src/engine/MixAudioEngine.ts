/**
 * MixAudioEngine — Web Audio dual-deck playback (djay-style routing).
 *
 * Each deck: AudioBufferSource → high-pass → 3-band EQ → low-pass → fader gain → master.
 * Mix plans drive deck_load / deck_play / deck_stop plus optional param_ramp (gain + EQ + filters).
 *
 * Differences vs apps like djay: no time-stretch key lock (RubberBand-like); playbackRate changes pitch.
 */
import type {
  MixControlEvent,
  MixControlTimeline,
  MixCurve,
  MixParam,
} from '../types/api';
import type { DeckState, PendingCrossfade } from '../types/engine';

const LOOK_AHEAD = 0.15;

const EVENT_ORDER: Record<string, number> = {
  deck_load: 0,
  param_set: 1,
  param_ramp: 2,
  deck_play: 3,
  deck_stop: 4,
};

function linearToDb(linear: number): number {
  const x = Math.max(0.02, Math.min(4, linear));
  return 20 * Math.log10(x);
}

function buildValueCurve(
  from: number,
  to: number,
  samples: number,
  curve: MixCurve | undefined,
): Float32Array {
  const out = new Float32Array(samples);
  for (let i = 0; i < samples; i++) {
    let t = samples <= 1 ? 1 : i / (samples - 1);
    const c = curve ?? 'linear';
    if (c === 'ease_in_out') {
      t = 0.5 - 0.5 * Math.cos(Math.PI * t);
    } else if (c === 'equal_power_in') {
      t = Math.sin((Math.PI / 2) * t);
    } else if (c === 'equal_power_out') {
      t = Math.cos((Math.PI / 2) * t);
    }
    out[i] = from + (to - from) * t;
  }
  return out;
}

export interface ScheduleMixTimelineOpts {
  timeline: MixControlTimeline;
  /** Physical deck currently playing the outgoing track (logical deck A in plan). */
  outgoingDeck: 'A' | 'B';
  /** Physical deck that will play the incoming track (logical deck B). */
  incomingDeck: 'A' | 'B';
  resolveUrlForSongId: (songId: number) => Promise<string>;
}

export class MixAudioEngine {
  private static instance: MixAudioEngine | null = null;

  private ctx: AudioContext | null = null;
  private deckA!: DeckState;
  private deckB!: DeckState;
  private analyser: AnalyserNode | null = null;
  private masterGain: GainNode | null = null;

  private schedulerId: number | null = null;
  private pendingXfade: PendingCrossfade | null = null;

  private loopA: number | null = null;
  private loopB: number | null = null;
  private loopActive = false;
  /** Prevents stacking multiple loop crossfades from RAF bursts near loop end. */
  private loopCrossfadeLock = false;
  private activeDeck: 'A' | 'B' = 'A';

  private timelineTimers: number[] = [];

  private onTimeUpdate: ((time: number, duration: number) => void) | null = null;
  private onTrackEnd: (() => void) | null = null;

  private constructor() {}

  static getInstance(): MixAudioEngine {
    if (!MixAudioEngine.instance) {
      MixAudioEngine.instance = new MixAudioEngine();
    }
    return MixAudioEngine.instance;
  }

  private ensureContext(): AudioContext {
    if (!this.ctx || this.ctx.state === 'closed') {
      this.ctx = new AudioContext({ sampleRate: 44100 });
      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.value = 1.0;
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 256;
      this.analyser.smoothingTimeConstant = 0.8;

      this.masterGain.connect(this.analyser);
      this.analyser.connect(this.ctx.destination);

      this.deckA = this.createDeck();
      this.deckB = this.createDeck();
    }
    if (this.ctx.state === 'suspended') {
      void this.ctx.resume();
    }
    return this.ctx;
  }

  /** Backend timeline uses logical A=outgoing, B=incoming. Map to physical decks. */
  private logicalToPhysical(logical: 'A' | 'B', outgoingPhysical: 'A' | 'B'): 'A' | 'B' {
    if (logical === 'A') return outgoingPhysical;
    return outgoingPhysical === 'A' ? 'B' : 'A';
  }

  private getDeckState(deck: 'A' | 'B'): DeckState {
    return deck === 'A' ? this.deckA : this.deckB;
  }

  private createDeck(): DeckState {
    const ctx = this.ctx!;
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 20;
    hp.Q.value = 0.707;

    const lowShelf = ctx.createBiquadFilter();
    lowShelf.type = 'lowshelf';
    lowShelf.frequency.value = 250;
    lowShelf.gain.value = 0;

    const midPeaking = ctx.createBiquadFilter();
    midPeaking.type = 'peaking';
    midPeaking.frequency.value = 1000;
    midPeaking.Q.value = 1;
    midPeaking.gain.value = 0;

    const highShelf = ctx.createBiquadFilter();
    highShelf.type = 'highshelf';
    highShelf.frequency.value = 4000;
    highShelf.gain.value = 0;

    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 20000;
    lp.Q.value = 0.707;

    const gainNode = ctx.createGain();
    gainNode.gain.value = 0;

    hp.connect(lowShelf);
    lowShelf.connect(midPeaking);
    midPeaking.connect(highShelf);
    highShelf.connect(lp);
    lp.connect(gainNode);
    gainNode.connect(this.masterGain!);

    return {
      buffer: null,
      loadedSongId: null,
      sourceNode: null,
      eqInput: hp,
      hp,
      lowShelf,
      midPeaking,
      highShelf,
      lp,
      gainNode,
      isPlaying: false,
      startTime: 0,
      startOffset: 0,
      nextLoopSource: null,
      nextLoopGain: null,
    };
  }

  cancelScheduledTimeline(): void {
    for (const id of this.timelineTimers) {
      window.clearTimeout(id);
    }
    this.timelineTimers = [];
  }

  /**
   * Schedule backend mix_control_timeline relative to when the outgoing deck reaches
   * start_at_from_time_sec on its buffer timeline.
   */
  async scheduleMixControlTimeline(opts: ScheduleMixTimelineOpts): Promise<void> {
    const ctx = this.ensureContext();
    this.cancelScheduledTimeline();

    const { timeline, outgoingDeck, incomingDeck, resolveUrlForSongId } = opts;
    const outgoingPhy = outgoingDeck;

    const loads = timeline.events.filter(
      (e): e is Extract<MixControlEvent, { type: 'deck_load' }> => e.type === 'deck_load',
    );
    await Promise.all(
      loads.map(async (ld) => {
        const physical = this.logicalToPhysical(ld.deck, outgoingPhy);
        const d = this.getDeckState(physical);
        if (d.loadedSongId === ld.song_id && d.buffer) return;
        const url = await resolveUrlForSongId(ld.song_id);
        await this.loadTrack(url, physical, ld.song_id);
      }),
    );

    const outgoing = this.getDeckState(outgoingPhy);
    const startAt = timeline.start_at_from_time_sec ?? 0;
    const anchorWall = this.computeAnchorAudioTime(outgoingPhy, startAt);

    const events = [...timeline.events].sort((a, b) => {
      const dt = a.time_sec - b.time_sec;
      if (dt !== 0) return dt;
      return (EVENT_ORDER[a.type] ?? 99) - (EVENT_ORDER[b.type] ?? 99);
    });

    const eps = 0.002;
    const primeT = anchorWall - eps;
    const incoming = this.getDeckState(incomingDeck);

    /* Neutral EQ baseline at transition start */
    for (const d of [outgoing, incoming]) {
      this.resetDeckEqAutomation(d, primeT);
    }

    outgoing.gainNode.gain.cancelScheduledValues(primeT);
    incoming.gainNode.gain.cancelScheduledValues(primeT);
    outgoing.gainNode.gain.setValueAtTime(outgoing.gainNode.gain.value, primeT);
    incoming.gainNode.gain.setValueAtTime(0, primeT);

    if (timeline.mode === 'hard_cut') {
      incoming.gainNode.gain.setValueAtTime(1, anchorWall);
    }

    const scheduleAudioCallback = (whenWall: number, fn: () => void) => {
      const delayMs = Math.max(0, (whenWall - ctx.currentTime) * 1000);
      if (delayMs < 5) {
        fn();
      } else {
        this.timelineTimers.push(window.setTimeout(fn, delayMs));
      }
    };

    for (const raw of events) {
      const ev = raw as MixControlEvent;
      const whenWall = anchorWall + ev.time_sec;

      switch (ev.type) {
        case 'deck_load':
          /* Buffers prefetched before anchor math — timing only matters for DJ prep hints */
          break;
        case 'deck_play': {
          const physical = this.logicalToPhysical(ev.deck, outgoingPhy);
          const d = this.getDeckState(physical);
          const offset = Math.max(0, ev.position_sec ?? 0);
          const rate = ev.playback_rate ?? 1;
          const startWall = Math.max(whenWall, ctx.currentTime + 0.02);

          const runPlay = () => {
            if (!d.buffer) return;
            this.stopDeckSource(d);
            const src = ctx.createBufferSource();
            src.buffer = d.buffer;
            src.playbackRate.value = rate;
            src.connect(d.eqInput);
            const remain = Math.max(0.01, d.buffer.duration - offset);
            const wallDur = remain / rate;
            try {
              src.stop(startWall + wallDur + 0.05);
            } catch {
              /* ignore */
            }
            src.start(startWall, offset);
            d.sourceNode = src;
            d.startTime = startWall;
            d.startOffset = offset;
            d.isPlaying = true;
            if (physical === incomingDeck) {
              this.activeDeck = incomingDeck;
            }
          };
          scheduleAudioCallback(whenWall, runPlay);
          break;
        }
        case 'deck_stop': {
          const physical = this.logicalToPhysical(ev.deck, outgoingPhy);
          const d = this.getDeckState(physical);
          const stopWall = Math.max(whenWall, ctx.currentTime + 0.05);
          // Fade-out ramp: 4s from current gain to 0 then stop source
          const fadeStart = Math.max(ctx.currentTime, stopWall - 4.0);
          d.gainNode.gain.cancelScheduledValues(fadeStart);
          d.gainNode.gain.setValueAtTime(d.gainNode.gain.value, fadeStart);
          d.gainNode.gain.linearRampToValueAtTime(0, stopWall);
          try {
            if (d.sourceNode) {
              d.sourceNode.stop(stopWall + 0.05);
            }
          } catch {
            /* ignore */
          }
          this.timelineTimers.push(
            window.setTimeout(() => {
              d.sourceNode = null;
              d.isPlaying = false;
            }, Math.max(0, (stopWall - ctx.currentTime) * 1000) + 80),
          );
          break;
        }
        case 'param_ramp': {
          const physical = this.logicalToPhysical(ev.deck, outgoingPhy);
          const d = this.getDeckState(physical);
          const t0 = Math.max(whenWall, ctx.currentTime + 0.02);
          this.scheduleParamRamp(d, ev.param, t0, ev.duration_sec, ev.from ?? ev.from_, ev.to, ev.curve);
          break;
        }
        case 'param_set': {
          const physical = this.logicalToPhysical(ev.deck, outgoingPhy);
          const d = this.getDeckState(physical);
          const t0 = Math.max(whenWall, ctx.currentTime + 0.02);
          this.applyParamAt(d, ev.param, ev.value, t0);
          break;
        }
        default:
          break;
      }
    }

    this.startScheduler();
  }

  private computeAnchorAudioTime(outgoingDeck: 'A' | 'B', startAtFromSongSec: number): number {
    const ctx = this.ensureContext();
    const d = this.getDeckState(outgoingDeck);
    const rate = d.sourceNode?.playbackRate.value ?? 1;
    if (!d.isPlaying || !d.sourceNode) {
      return ctx.currentTime + 0.05;
    }
    const target = Math.max(0, startAtFromSongSec);
    const anchor = d.startTime + (target - d.startOffset) / rate;
    return Math.max(ctx.currentTime + 0.05, anchor);
  }

  private resetDeckEqAutomation(d: DeckState, at: number): void {
    d.hp.frequency.cancelScheduledValues(at);
    d.lp.frequency.cancelScheduledValues(at);
    d.lowShelf.gain.cancelScheduledValues(at);
    d.midPeaking.gain.cancelScheduledValues(at);
    d.highShelf.gain.cancelScheduledValues(at);
    d.hp.frequency.setValueAtTime(20, at);
    d.lp.frequency.setValueAtTime(20000, at);
    d.lowShelf.gain.setValueAtTime(0, at);
    d.midPeaking.gain.setValueAtTime(0, at);
    d.highShelf.gain.setValueAtTime(0, at);
  }

  private scheduleParamRamp(
    d: DeckState,
    param: MixParam,
    t0: number,
    dur: number,
    from: number,
    to: number,
    curve?: MixCurve,
  ): void {
    const ctx = this.ctx!;
    const samples = Math.max(16, Math.ceil(dur * ctx.sampleRate / 256));

    if (param === 'gain') {
      d.gainNode.gain.cancelScheduledValues(t0);
      d.gainNode.gain.setValueAtTime(from, t0);
      const curveArr = buildValueCurve(from, to, samples, curve);
      d.gainNode.gain.setValueCurveAtTime(curveArr, t0, dur);
      return;
    }

    if (param === 'low_eq') {
      d.lowShelf.gain.cancelScheduledValues(t0);
      const fDb = linearToDb(from);
      const tDb = linearToDb(to);
      const curveArr = buildValueCurve(fDb, tDb, samples, curve);
      d.lowShelf.gain.setValueCurveAtTime(curveArr, t0, dur);
      return;
    }
    if (param === 'mid_eq') {
      d.midPeaking.gain.cancelScheduledValues(t0);
      const fDb = linearToDb(from);
      const tDb = linearToDb(to);
      const curveArr = buildValueCurve(fDb, tDb, samples, curve);
      d.midPeaking.gain.setValueCurveAtTime(curveArr, t0, dur);
      return;
    }
    if (param === 'high_eq') {
      d.highShelf.gain.cancelScheduledValues(t0);
      const fDb = linearToDb(from);
      const tDb = linearToDb(to);
      const curveArr = buildValueCurve(fDb, tDb, samples, curve);
      d.highShelf.gain.setValueCurveAtTime(curveArr, t0, dur);
      return;
    }
    if (param === 'highpass_hz') {
      d.hp.frequency.cancelScheduledValues(t0);
      const curveArr = buildValueCurve(from, to, samples, curve);
      d.hp.frequency.setValueCurveAtTime(curveArr, t0, dur);
      return;
    }
    if (param === 'lowpass_hz') {
      d.lp.frequency.cancelScheduledValues(t0);
      const curveArr = buildValueCurve(from, to, samples, curve);
      d.lp.frequency.setValueCurveAtTime(curveArr, t0, dur);
      return;
    }
    if (param === 'playback_rate' && d.sourceNode) {
      d.sourceNode.playbackRate.cancelScheduledValues(t0);
      d.sourceNode.playbackRate.setValueAtTime(from, t0);
      const curveArr = buildValueCurve(from, to, samples, curve);
      d.sourceNode.playbackRate.setValueCurveAtTime(curveArr, t0, dur);
    }
  }

  private applyParamAt(d: DeckState, param: MixParam, value: number, t0: number): void {
    if (param === 'gain') {
      d.gainNode.gain.setValueAtTime(value, t0);
      return;
    }
    if (param === 'low_eq') {
      d.lowShelf.gain.setValueAtTime(linearToDb(value), t0);
      return;
    }
    if (param === 'mid_eq') {
      d.midPeaking.gain.setValueAtTime(linearToDb(value), t0);
      return;
    }
    if (param === 'high_eq') {
      d.highShelf.gain.setValueAtTime(linearToDb(value), t0);
      return;
    }
    if (param === 'highpass_hz') {
      d.hp.frequency.setValueAtTime(value, t0);
      return;
    }
    if (param === 'lowpass_hz') {
      d.lp.frequency.setValueAtTime(value, t0);
      return;
    }
    if (param === 'playback_rate' && d.sourceNode) {
      d.sourceNode.playbackRate.setValueAtTime(value, t0);
    }
  }

  async loadTrack(url: string, deck: 'A' | 'B', songId?: number | null): Promise<void> {
    const ctx = this.ensureContext();
    const headers: HeadersInit = {};
    try {
      const token = typeof localStorage !== 'undefined' ? localStorage.getItem('harbeat_token') : null;
      if (token) headers.Authorization = `Bearer ${token}`;
    } catch {
      /* ignore */
    }
    const resp = await fetch(url, { headers });
    const arrayBuffer = await resp.arrayBuffer();
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

    const d = deck === 'A' ? this.deckA : this.deckB;
    d.buffer = audioBuffer;
    d.loadedSongId = songId ?? null;
  }

  play(deck: 'A' | 'B' = 'A', offsetSec = 0, dualCrossfadeSec = 4.0): void {
    const ctx = this.ensureContext();
    const d = deck === 'A' ? this.deckA : this.deckB;
    if (!d.buffer) return;

    this.stopDeckSource(d);

    const now = ctx.currentTime;
    const source = ctx.createBufferSource();
    source.buffer = d.buffer;
    source.playbackRate.value = 1;

    let effectiveOffset = offsetSec;
    if (this.loopActive && this.loopA !== null && this.loopB !== null) {
      const hi = Math.max(this.loopA + 0.01, this.loopB - 0.01);
      effectiveOffset = Math.min(hi, Math.max(this.loopA, offsetSec));
    }

    source.connect(d.eqInput);
    d.gainNode.gain.cancelScheduledValues(now);
    d.gainNode.gain.setValueAtTime(0, now);
    d.gainNode.gain.linearRampToValueAtTime(1, now + 0.01);
    source.start(now, effectiveOffset);

    d.sourceNode = source;
    d.startTime = now;
    d.startOffset = effectiveOffset;
    d.isPlaying = true;
    this.activeDeck = deck;

    const stopTime = this.loopActive && this.loopB !== null ? this.loopB : d.buffer.duration;
    const wallStop = now + Math.max(0.05, stopTime - effectiveOffset);
    try {
      source.stop(wallStop);
    } catch {
      /* ignore */
    }

    const other = deck === 'A' ? this.deckB : this.deckA;
    if (other.isPlaying && other.sourceNode) {
      const xfadeSec = Math.max(4.0, dualCrossfadeSec);
      this.crossfadeTo(deck, xfadeSec);
    }

    this.startScheduler();
  }

  /** Hard stop one deck (gain 0 + stop source). Used so loop mode never overlaps the idle deck. */
  silenceDeckImmediate(deck: 'A' | 'B'): void {
    const ctx = this.ctx;
    if (!ctx) return;
    const d = deck === 'A' ? this.deckA : this.deckB;
    const now = ctx.currentTime;
    d.gainNode.gain.cancelScheduledValues(now);
    d.gainNode.gain.setValueAtTime(0, now);
    this.stopDeckSource(d, now + 0.01);
    d.isPlaying = false;
  }

  pause(deck?: 'A' | 'B'): void {
    const ctx = this.ctx;
    if (!ctx) return;

    const targetDeck = deck ?? this.activeDeck;
    const d = targetDeck === 'A' ? this.deckA : this.deckB;
    if (!d.isPlaying) return;

    const now = ctx.currentTime;
    d.gainNode.gain.cancelScheduledValues(now);
    d.gainNode.gain.setValueAtTime(d.gainNode.gain.value, now);
    d.gainNode.gain.linearRampToValueAtTime(0, now + 4.0);

    this.stopDeckSource(d, now + 4.05);
    d.isPlaying = false;
  }

  /**
   * @param silence_other_deck 为 true 时先静音另一 Deck，避免误判「双 Deck 同时在播」而触发 4s crossfade 把当前 scrub 的 deck 增益曲线冲掉导致无声。Mix Lab 进度条 scrub 应传 true。
   */
  seek(deck: 'A' | 'B', timeSec: number, silence_other_deck = false): void {
    const d = deck === 'A' ? this.deckA : this.deckB;
    if (!d.buffer) return;
    const clamped = Math.max(0, Math.min(timeSec, d.buffer.duration));

    this.cancelScheduledTimeline();
    this.pendingXfade = null;
    this.clearScheduledLoops();

    const ctx = this.ensureContext();
    const now = ctx.currentTime;

    if (silence_other_deck) {
      const other: 'A' | 'B' = deck === 'A' ? 'B' : 'A';
      this.silenceDeckImmediate(other);
    }

    /* 只要还有 source 就硬切（含 isPlaying 未同步或已播完但未清节点），避免只走 play 时 crossfade 分支异常 */
    if (d.sourceNode) {
      d.gainNode.gain.cancelScheduledValues(now);
      d.gainNode.gain.setValueAtTime(0, now);
      this.stopDeckSource(d, now + 0.01);
    }
    d.isPlaying = false;

    this.play(deck, clamped, 0);
  }

  getPosition(deck?: 'A' | 'B'): number {
    const targetDeck = deck ?? this.activeDeck;
    return this.computePosition(targetDeck);
  }

  getDuration(deck?: 'A' | 'B'): number {
    const targetDeck = deck ?? this.activeDeck;
    const d = targetDeck === 'A' ? this.deckA : this.deckB;
    return d.buffer?.duration ?? 0;
  }

  getActiveDeck(): 'A' | 'B' {
    return this.activeDeck;
  }

  getAudioContext(): AudioContext {
    return this.ensureContext();
  }

  getAnalyserData(): Uint8Array {
    if (!this.analyser) return new Uint8Array(0);
    const data = new Uint8Array(this.analyser.frequencyBinCount);
    this.analyser.getByteFrequencyData(data);
    return data;
  }

  setMasterVolume(value: number): void {
    if (this.masterGain) {
      this.masterGain.gain.value = Math.max(0, Math.min(1, value));
    }
  }

  /** One-shot SFX on the same master bus as decks (does not touch deck buffers or timelines). */
  playSfxBuffer(buffer: AudioBuffer, gain_linear = 0.62): void {
    const ctx = this.ensureContext();
    if (!this.masterGain) return;
    const g = ctx.createGain();
    g.gain.value = Math.max(0, Math.min(1, gain_linear));
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(g);
    g.connect(this.masterGain);
    const t0 = ctx.currentTime;
    src.start(t0);
    try {
      src.stop(t0 + buffer.duration + 0.02);
    } catch {
      /* ignore */
    }
  }

  crossfadeTo(toDeck: 'A' | 'B', durationSec: number): void {
    const ctx = this.ctx;
    if (!ctx) return;

    const fromDeck = toDeck === 'A' ? 'B' : 'A';
    const from = fromDeck === 'A' ? this.deckA : this.deckB;
    const to = toDeck === 'A' ? this.deckA : this.deckB;

    if (!from.isPlaying || !to.isPlaying) return;

    const now = ctx.currentTime;
    this.pendingXfade = { fromDeck, toDeck, durationSec, triggered: true };

    const resolution = 128;
    const curveLen = Math.ceil(durationSec * ctx.sampleRate / resolution);
    const fadeOut = new Float32Array(curveLen);
    const fadeIn = new Float32Array(curveLen);
    for (let i = 0; i < curveLen; i++) {
      const t = curveLen <= 1 ? 1 : i / (curveLen - 1);
      fadeOut[i] = Math.cos(t * Math.PI / 2);
      fadeIn[i] = Math.sin(t * Math.PI / 2);
    }

    from.gainNode.gain.cancelScheduledValues(now);
    from.gainNode.gain.setValueCurveAtTime(fadeOut, now, durationSec);

    to.gainNode.gain.cancelScheduledValues(now);
    to.gainNode.gain.setValueCurveAtTime(fadeIn, now, durationSec);

    window.setTimeout(() => {
      if (from.sourceNode) {
        this.stopDeckSource(from);
      }
      from.isPlaying = false;
      this.activeDeck = toDeck;
      this.pendingXfade = null;
    }, durationSec * 1000 + 50);
  }

  async prepareNextTrack(url: string): Promise<void> {
    const idleDeck: 'A' | 'B' = this.activeDeck === 'A' ? 'B' : 'A';
    await this.loadTrack(url, idleDeck);
  }

  triggerNextTrack(entrySec = 0, crossfadeSec = 4.0): void {
    const nextDeck: 'A' | 'B' = this.activeDeck === 'A' ? 'B' : 'A';
    this.play(nextDeck, entrySec, crossfadeSec);
  }

  setLoopPoints(start: number, end: number): void {
    this.loopA = Math.max(0, start);
    this.loopB = Math.max(this.loopA + 0.1, end);
  }

  toggleLoop(): boolean {
    this.loopActive = !this.loopActive;
    if (!this.loopActive) {
      this.clearScheduledLoops();
    }
    return this.loopActive;
  }

  /** Set loop region active without flipping (caller must pair with setLoopPoints / clearLoop). */
  setLoopActive(active: boolean): void {
    this.loopActive = active;
    if (!active) {
      this.loopCrossfadeLock = false;
      this.clearScheduledLoops();
    }
  }

  clearLoop(): void {
    this.loopActive = false;
    this.loopCrossfadeLock = false;
    this.loopA = null;
    this.loopB = null;
    this.clearScheduledLoops();
  }

  getLoopState(): { a: number | null; b: number | null; active: boolean } {
    return { a: this.loopA, b: this.loopB, active: this.loopActive };
  }

  setOnTimeUpdate(cb: (time: number, duration: number) => void): void {
    this.onTimeUpdate = cb;
  }

  setOnTrackEnd(cb: () => void): void {
    this.onTrackEnd = cb;
  }

  private startScheduler(): void {
    if (this.schedulerId !== null) return;
    const tick = () => {
      this.schedulerTick();
      this.schedulerId = requestAnimationFrame(tick);
    };
    this.schedulerId = requestAnimationFrame(tick);
  }

  private stopScheduler(): void {
    if (this.schedulerId !== null) {
      cancelAnimationFrame(this.schedulerId);
      this.schedulerId = null;
    }
  }

  private schedulerTick(): void {
    const ctx = this.ctx;
    if (!ctx) return;

    const deck = this.activeDeck === 'A' ? this.deckA : this.deckB;
    const currentTime = this.computePosition(this.activeDeck);

    if (this.onTimeUpdate && deck.buffer) {
      this.onTimeUpdate(currentTime, deck.buffer.duration);
    }

    if (this.loopActive && this.loopA !== null && this.loopB !== null && !this.loopCrossfadeLock) {
      const time_to_loop_end = this.loopB - currentTime;
      /* 含略过终点的漏帧（后台标签等），避免永远不触发重启 */
      if (time_to_loop_end <= LOOK_AHEAD && time_to_loop_end > -1.0) {
        this.restartLoopSegment();
      }
    }

    if (deck.buffer && currentTime >= deck.buffer.duration - 0.1) {
      if (!this.loopActive) {
        this.onTrackEnd?.();
      }
    }

    if (!this.deckA.isPlaying && !this.deckB.isPlaying) {
      this.stopScheduler();
    }
  }

  /** 从 loop 起点重新起一段 BufferSource（仍受 loopEnd 的 stop 约束），实现自动循环。 */
  private restartLoopSegment(): void {
    const ctx = this.ctx;
    if (!ctx) return;
    if (!this.loopActive || this.loopA == null || this.loopB == null) return;
    if (this.loopCrossfadeLock) return;

    const deck_key = this.activeDeck;
    const d = this.getDeckState(deck_key);
    if (!d.buffer || !d.sourceNode) return;

    this.loopCrossfadeLock = true;
    this.play(deck_key, this.loopA, 0);

    const seg_sec = Math.max(0.05, this.loopB - this.loopA);
    const hold_ms = Math.min(220, Math.max(28, seg_sec * 90));
    window.setTimeout(() => {
      this.loopCrossfadeLock = false;
    }, hold_ms);
  }

  private clearScheduledLoops(): void {
    this.loopCrossfadeLock = false;
  }

  private computePosition(deck: 'A' | 'B'): number {
    const ctx = this.ctx;
    if (!ctx) return 0;

    const d = deck === 'A' ? this.deckA : this.deckB;
    if (!d.isPlaying || !d.sourceNode) return d.startOffset;

    const elapsed = ctx.currentTime - d.startTime;
    const rate = d.sourceNode.playbackRate.value;
    return d.startOffset + elapsed * rate;
  }

  private stopDeckSource(d: DeckState, when?: number): void {
    const ctx = this.ctx;
    if (!ctx) return;
    if (d.sourceNode) {
      try {
        d.sourceNode.stop(when ?? ctx.currentTime + 0.01);
      } catch { /* noop */ }
      d.sourceNode = null;
    }
    if (d.nextLoopSource) {
      try { d.nextLoopSource.stop(); } catch { /* noop */ }
      d.nextLoopSource = null;
    }
    if (d.nextLoopGain) {
      try { d.nextLoopGain.disconnect(); } catch { /* noop */ }
      d.nextLoopGain = null;
    }
  }

  destroy(): void {
    this.cancelScheduledTimeline();
    this.stopScheduler();
    this.clearScheduledLoops();
    this.stopDeckSource(this.deckA);
    this.stopDeckSource(this.deckB);
    if (this.ctx && this.ctx.state !== 'closed') {
      void this.ctx.close();
    }
    this.ctx = null;
    this.masterGain = null;
    this.analyser = null;
    MixAudioEngine.instance = null;
  }
}
