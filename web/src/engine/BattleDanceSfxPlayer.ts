import { MixAudioEngine } from './MixAudioEngine';

/**
 * Short battle / DJ-style one-shots: procedural buffers into the mix master bus (no deck timeline).
 * Vocals use Web Speech API (OS-level mix with music).
 */
export class BattleDanceSfxPlayer {
  private _buffer_cache = new Map<string, AudioBuffer>();
  private _prepare_started = false;
  private _prepare_done = false;

  async prepare(): Promise<void> {
    if (this._prepare_done) return;
    if (this._prepare_started) {
      while (!this._prepare_done) {
        await new Promise((r) => setTimeout(r, 20));
      }
      return;
    }
    this._prepare_started = true;
    const engine = MixAudioEngine.getInstance();
    const ctx = engine.getAudioContext();
    const sr = ctx.sampleRate;
    const [airHorn, siren, scratch, boom, riser, glitch, laser] = await Promise.all([
      this.renderAirHorn(sr),
      this.renderSiren(sr),
      this.renderScratch(sr),
      this.renderBoom(sr),
      this.renderRiser(sr),
      this.renderGlitch(sr),
      this.renderLaser(sr),
    ]);
    this._buffer_cache.set('air_horn', airHorn);
    this._buffer_cache.set('siren', siren);
    this._buffer_cache.set('scratch', scratch);
    this._buffer_cache.set('boom', boom);
    this._buffer_cache.set('riser', riser);
    this._buffer_cache.set('glitch', glitch);
    this._buffer_cache.set('laser', laser);
    this._prepare_done = true;
  }

  playBufferId(id: string, gain = 0.55): void {
    const buf = this._buffer_cache.get(id);
    if (!buf) return;
    MixAudioEngine.getInstance().playSfxBuffer(buf, gain);
  }

  speak(text: string, lang = 'en-US'): void {
    if (typeof window === 'undefined' || !window.speechSynthesis) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = lang;
    utter.rate = 1.05;
    utter.pitch = 1;
    utter.volume = 1;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  }

  private async renderAirHorn(sr: number): Promise<AudioBuffer> {
    const dur = 0.75;
    const offline = new OfflineAudioContext(2, Math.ceil(sr * dur), sr);
    const t0 = 0;
    const osc = offline.createOscillator();
    const filt = offline.createBiquadFilter();
    const g = offline.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(160, t0);
    osc.frequency.exponentialRampToValueAtTime(720, t0 + 0.38);
    filt.type = 'bandpass';
    filt.frequency.value = 900;
    filt.Q.value = 1.2;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(0.32, t0 + 0.05);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(filt);
    filt.connect(g);
    g.connect(offline.destination);
    osc.start(t0);
    osc.stop(t0 + dur);
    const dry = await offline.startRendering();

    const echo = new OfflineAudioContext(2, Math.ceil(sr * (dur + 0.35)), sr);
    const src = echo.createBufferSource();
    src.buffer = dry;
    const wet = echo.createGain();
    const delay = echo.createDelay(0.5);
    const fb = echo.createGain();
    const out = echo.createGain();
    delay.delayTime.value = 0.12;
    fb.gain.value = 0.38;
    wet.gain.value = 0.55;
    src.connect(wet);
    wet.connect(out);
    wet.connect(delay);
    delay.connect(fb);
    fb.connect(delay);
    delay.connect(out);
    out.connect(echo.destination);
    src.start(0);
    return echo.startRendering();
  }

  private async renderSiren(sr: number): Promise<AudioBuffer> {
    const dur = 1.1;
    const offline = new OfflineAudioContext(1, Math.ceil(sr * dur), sr);
    const osc = offline.createOscillator();
    const g = offline.createGain();
    osc.type = 'triangle';
    const t0 = 0;
    for (let i = 0; i < 6; i++) {
      const a = t0 + i * 0.16;
      osc.frequency.setValueAtTime(520, a);
      osc.frequency.linearRampToValueAtTime(980, a + 0.08);
      osc.frequency.linearRampToValueAtTime(520, a + 0.16);
    }
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(0.28, t0 + 0.03);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(g);
    g.connect(offline.destination);
    osc.start(t0);
    osc.stop(t0 + dur);
    return offline.startRendering();
  }

  private async renderScratch(sr: number): Promise<AudioBuffer> {
    const dur = 0.35;
    const len = Math.ceil(sr * dur);
    const scratch_ctx = new OfflineAudioContext(1, len, sr);
    const noiseBuf = scratch_ctx.createBuffer(1, len, sr);
    const data = noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) {
      data[i] = (Math.random() * 2 - 1) * (1 - i / len);
    }
    const noise = scratch_ctx.createBufferSource();
    noise.buffer = noiseBuf;
    const f = scratch_ctx.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.setValueAtTime(2800, 0);
    f.frequency.exponentialRampToValueAtTime(400, dur);
    f.Q.value = 0.9;
    const g = scratch_ctx.createGain();
    g.gain.setValueAtTime(0.45, 0);
    g.gain.exponentialRampToValueAtTime(0.0001, dur);
    noise.connect(f);
    f.connect(g);
    g.connect(scratch_ctx.destination);
    noise.start(0);
    noise.stop(dur);
    return scratch_ctx.startRendering();
  }

  private async renderBoom(sr: number): Promise<AudioBuffer> {
    const dur = 0.55;
    const offline = new OfflineAudioContext(1, Math.ceil(sr * dur), sr);
    const osc = offline.createOscillator();
    const g = offline.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(58, 0);
    osc.frequency.exponentialRampToValueAtTime(28, 0.45);
    g.gain.setValueAtTime(0.0001, 0);
    g.gain.exponentialRampToValueAtTime(0.9, 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, dur);
    osc.connect(g);
    g.connect(offline.destination);
    osc.start(0);
    osc.stop(dur);
    return offline.startRendering();
  }

  private async renderRiser(sr: number): Promise<AudioBuffer> {
    const dur = 1.25;
    const offline = new OfflineAudioContext(1, Math.ceil(sr * dur), sr);
    const len = offline.length;
    const buf = offline.createBuffer(1, len, sr);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) {
      d[i] = (Math.random() * 2 - 1) * 0.85;
    }
    const src = offline.createBufferSource();
    src.buffer = buf;
    const f = offline.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.setValueAtTime(180, 0);
    f.frequency.exponentialRampToValueAtTime(12000, dur);
    const g = offline.createGain();
    g.gain.setValueAtTime(0.0001, 0);
    g.gain.exponentialRampToValueAtTime(0.22, 0.08);
    g.gain.exponentialRampToValueAtTime(0.0001, dur);
    src.connect(f);
    f.connect(g);
    g.connect(offline.destination);
    src.start(0);
    src.stop(dur);
    return offline.startRendering();
  }

  private async renderGlitch(sr: number): Promise<AudioBuffer> {
    const dur = 0.28;
    const offline = new OfflineAudioContext(1, Math.ceil(sr * dur), sr);
    const osc = offline.createOscillator();
    const g = offline.createGain();
    osc.type = 'square';
    osc.frequency.setValueAtTime(440, 0);
    osc.frequency.setValueAtTime(1320, 0.05);
    osc.frequency.setValueAtTime(220, 0.11);
    osc.frequency.setValueAtTime(880, 0.18);
    g.gain.setValueAtTime(0.12, 0);
    g.gain.setValueAtTime(0.22, 0.07);
    g.gain.exponentialRampToValueAtTime(0.0001, dur);
    osc.connect(g);
    g.connect(offline.destination);
    osc.start(0);
    osc.stop(dur);
    return offline.startRendering();
  }

  private async renderLaser(sr: number): Promise<AudioBuffer> {
    const dur = 0.4;
    const offline = new OfflineAudioContext(1, Math.ceil(sr * dur), sr);
    const osc = offline.createOscillator();
    const g = offline.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(2200, 0);
    osc.frequency.exponentialRampToValueAtTime(180, dur);
    g.gain.setValueAtTime(0.0001, 0);
    g.gain.exponentialRampToValueAtTime(0.2, 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, dur);
    osc.connect(g);
    g.connect(offline.destination);
    osc.start(0);
    osc.stop(dur);
    return offline.startRendering();
  }
}
