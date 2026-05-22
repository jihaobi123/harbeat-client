// Client-side synthesizers for the 5 high-frequency DJ live SFX.
// Each call is a one-shot routed through the same AudioContext as the master mix
// when available (so the SFX rides the master bus and can be heard alongside the deck).
// Latency is near-zero (no network, no file decode).

import { MixAudioEngine } from './MixAudioEngine';

export type DjLiveSfxId = 'scratch' | 'airhorn' | 'spinback' | 'siren' | 'whoosh';

export interface DjLiveSfxDescriptor {
  id: DjLiveSfxId;
  label: string;
  hint: string;
}

export const DJ_LIVE_SFX: DjLiveSfxDescriptor[] = [
  { id: 'scratch',  label: '搓碟 Scratch',   hint: '黑胶搓盘 · 短促拨片' },
  { id: 'airhorn',  label: '气笛 Air Horn',  hint: 'BUUUH! 三连鸣' },
  { id: 'spinback', label: '倒带 Spinback',  hint: '黑胶刹车下坠' },
  { id: 'siren',    label: '警报 Siren',     hint: '高低频警笛' },
  { id: 'whoosh',   label: '嗖声 Whoosh',    hint: '过渡扫频' },
];

function getCtxAndBus(): { ctx: AudioContext; bus: AudioNode } {
  const engine = MixAudioEngine.getInstance() as any;
  // Reuse the engine's AudioContext + masterGain so the SFX is on the same bus
  // as the deck output (consistent perceived loudness, single mixdown).
  if (typeof engine.getAudioContext === 'function') {
    const ctx: AudioContext | undefined = engine.getAudioContext();
    const master: AudioNode | undefined = engine.masterGain;
    if (ctx && master) return { ctx, bus: master };
    if (ctx) return { ctx, bus: ctx.destination };
  }
  const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
  const ctx = new Ctx() as AudioContext;
  return { ctx, bus: ctx.destination };
}

function noiseBuffer(ctx: AudioContext, durationSec: number, color: 'white' | 'pink' = 'white'): AudioBuffer {
  const len = Math.floor(ctx.sampleRate * durationSec);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const data = buf.getChannelData(0);
  if (color === 'pink') {
    // Paul Kellet's pink noise approximation.
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < len; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.96900 * b2 + white * 0.1538520;
      b3 = 0.86650 * b3 + white * 0.3104856;
      b4 = 0.55000 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.0168980;
      data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11;
      b6 = white * 0.115926;
    }
  } else {
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
  }
  return buf;
}

// ─── 1. Scratch (搓碟) ────────────────────────────────────────────────
function playScratch(ctx: AudioContext, bus: AudioNode, gain = 0.65) {
  const t0 = ctx.currentTime;
  const dur = 0.32;

  // Tonal core: sawtooth oscillator whose frequency is yanked back-and-forth
  // (the "wikki-wikki" pitch shove of moving a record under the needle).
  const osc = ctx.createOscillator();
  osc.type = 'sawtooth';
  osc.frequency.setValueAtTime(180, t0);
  osc.frequency.linearRampToValueAtTime(620, t0 + 0.05);
  osc.frequency.linearRampToValueAtTime(120, t0 + 0.13);
  osc.frequency.linearRampToValueAtTime(540, t0 + 0.20);
  osc.frequency.linearRampToValueAtTime(160, t0 + 0.28);

  // Bandpass to shape the timbre toward the metallic needle sound.
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.frequency.value = 1400;
  bp.Q.value = 4;

  // Light noise layer for "vinyl grit".
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuffer(ctx, dur, 'pink');
  const noiseHP = ctx.createBiquadFilter();
  noiseHP.type = 'highpass';
  noiseHP.frequency.value = 1500;

  const g = ctx.createGain();
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

  osc.connect(bp).connect(g);
  noise.connect(noiseHP).connect(g);
  g.connect(bus);
  osc.start(t0); osc.stop(t0 + dur + 0.02);
  noise.start(t0); noise.stop(t0 + dur + 0.02);
}

// ─── 2. Air Horn (气笛) ──────────────────────────────────────────────
function playAirHorn(ctx: AudioContext, bus: AudioNode, gain = 0.55) {
  // Reggaeton / hip-hop DJ classic — three short blasts.
  const blastSchedule = [0.0, 0.18, 0.36];
  const blastDur = 0.14;
  blastSchedule.forEach((offset) => {
    const t0 = ctx.currentTime + offset;
    // Two detuned saw oscillators around 700 Hz for a fat fundamental.
    const oscA = ctx.createOscillator();
    const oscB = ctx.createOscillator();
    oscA.type = 'sawtooth'; oscB.type = 'sawtooth';
    oscA.frequency.value = 690;
    oscB.frequency.value = 712;
    // Slight upward bend over the blast — classic stadium horn pitch rise.
    oscA.frequency.linearRampToValueAtTime(740, t0 + blastDur);
    oscB.frequency.linearRampToValueAtTime(760, t0 + blastDur);

    // Resonant peak around 1.4 kHz to imitate the metal cone.
    const peak = ctx.createBiquadFilter();
    peak.type = 'peaking';
    peak.frequency.value = 1400;
    peak.Q.value = 6;
    peak.gain.value = 9;

    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(gain, t0 + 0.012);
    g.gain.setValueAtTime(gain, t0 + blastDur - 0.04);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + blastDur);

    oscA.connect(peak); oscB.connect(peak);
    peak.connect(g).connect(bus);
    oscA.start(t0); oscB.start(t0);
    oscA.stop(t0 + blastDur + 0.02); oscB.stop(t0 + blastDur + 0.02);
  });
}

// ─── 3. Spinback (倒带) ──────────────────────────────────────────────
function playSpinback(ctx: AudioContext, bus: AudioNode, gain = 0.7) {
  const t0 = ctx.currentTime;
  const dur = 0.85;
  // Pitched body sweeping from high to near-silence (vinyl slowing down).
  const osc = ctx.createOscillator();
  osc.type = 'sawtooth';
  osc.frequency.setValueAtTime(420, t0);
  osc.frequency.exponentialRampToValueAtTime(40, t0 + dur);

  // Lowpass that closes down as the spin slows — simulates losing brightness.
  const lp = ctx.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.setValueAtTime(4500, t0);
  lp.frequency.exponentialRampToValueAtTime(200, t0 + dur);
  lp.Q.value = 1.2;

  // Vinyl crackle layer.
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuffer(ctx, dur, 'pink');
  const noiseBP = ctx.createBiquadFilter();
  noiseBP.type = 'bandpass';
  noiseBP.frequency.setValueAtTime(2800, t0);
  noiseBP.frequency.exponentialRampToValueAtTime(300, t0 + dur);
  noiseBP.Q.value = 2;

  const g = ctx.createGain();
  g.gain.setValueAtTime(gain, t0);
  g.gain.linearRampToValueAtTime(gain * 0.7, t0 + dur * 0.6);
  g.gain.linearRampToValueAtTime(0.0001, t0 + dur);

  const noiseGain = ctx.createGain();
  noiseGain.gain.value = 0.4;

  osc.connect(lp).connect(g);
  noise.connect(noiseBP).connect(noiseGain).connect(g);
  g.connect(bus);

  osc.start(t0); osc.stop(t0 + dur + 0.02);
  noise.start(t0); noise.stop(t0 + dur + 0.02);
}

// ─── 4. Siren (警报) ─────────────────────────────────────────────────
function playSiren(ctx: AudioContext, bus: AudioNode, gain = 0.5) {
  const t0 = ctx.currentTime;
  const dur = 0.9;
  // LFO sweeps the oscillator pitch between 600 ↔ 1200 Hz at ~5 Hz (siren wail).
  const osc = ctx.createOscillator();
  osc.type = 'square';

  // Build pitch automation manually so we don't need an LFO graph.
  const lfoHz = 5;
  const steps = Math.floor(dur * 60); // 60 fps
  for (let i = 0; i <= steps; i++) {
    const t = i / 60;
    const phase = Math.sin(2 * Math.PI * lfoHz * t);
    const freq = 900 + 300 * phase;
    osc.frequency.setValueAtTime(freq, t0 + t);
  }

  // Tame the square wave with a lowpass so it doesn't sound abrasive.
  const lp = ctx.createBiquadFilter();
  lp.type = 'lowpass';
  lp.frequency.value = 3000;

  const g = ctx.createGain();
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.02);
  g.gain.setValueAtTime(gain, t0 + dur - 0.08);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

  osc.connect(lp).connect(g).connect(bus);
  osc.start(t0); osc.stop(t0 + dur + 0.02);
}

// ─── 5. Whoosh (嗖声) ────────────────────────────────────────────────
function playWhoosh(ctx: AudioContext, bus: AudioNode, gain = 0.6) {
  const t0 = ctx.currentTime;
  const dur = 0.55;
  const noise = ctx.createBufferSource();
  noise.buffer = noiseBuffer(ctx, dur, 'pink');

  // Sweep a resonant bandpass low→high→low for the "WOOSH" arc.
  const bp = ctx.createBiquadFilter();
  bp.type = 'bandpass';
  bp.frequency.setValueAtTime(300, t0);
  bp.frequency.exponentialRampToValueAtTime(6000, t0 + dur * 0.6);
  bp.frequency.exponentialRampToValueAtTime(800, t0 + dur);
  bp.Q.value = 1.8;

  const g = ctx.createGain();
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.05);
  g.gain.setValueAtTime(gain, t0 + dur * 0.6);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

  noise.connect(bp).connect(g).connect(bus);
  noise.start(t0); noise.stop(t0 + dur + 0.02);
}

const DISPATCH: Record<DjLiveSfxId, (ctx: AudioContext, bus: AudioNode) => void> = {
  scratch: playScratch,
  airhorn: playAirHorn,
  spinback: playSpinback,
  siren: playSiren,
  whoosh: playWhoosh,
};

/** Fire-and-forget one-shot. Safe to spam-click; each call is independent. */
export function playDjLiveSfx(id: DjLiveSfxId): void {
  const { ctx, bus } = getCtxAndBus();
  if (ctx.state === 'suspended') {
    void ctx.resume();
  }
  const fn = DISPATCH[id];
  if (fn) fn(ctx, bus);
}
