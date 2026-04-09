// DJ Processor - Superpowered AudioWorkletProcessor
// This runs on the audio thread. It houses two AdvancedAudioPlayers (Deck A/B),
// per-deck ThreeBandEQ + Filter, shared Echo, and a StereoMixer for crossfading.
//
// Communication with main thread via message port.

import { SuperpoweredWebAudio } from 'https://cdn.jsdelivr.net/npm/@superpoweredsdk/web@2.7.2/dist/Superpowered.js';

class DjProcessor extends SuperpoweredWebAudio.AudioWorkletProcessor {

  onReady() {
    const SP = this.Superpowered;
    const sr = this.samplerate;

    // --- Dual Deck Players ---
    this.playerA = new SP.AdvancedAudioPlayer(sr, 4, 2, 0, 0.501, 2, false);
    this.playerB = new SP.AdvancedAudioPlayer(sr, 4, 2, 0, 0.501, 2, false);

    this.playerA.loopOnEOF = false;
    this.playerB.loopOnEOF = false;
    this.playerA.timeStretching = true;
    this.playerB.timeStretching = true;
    this.playerA.timeStretchingSound = 1; // DJ mode
    this.playerB.timeStretchingSound = 1;

    // --- Per-Deck 3-Band EQ ---
    this.eqA = new SP.ThreeBandEQ(sr);
    this.eqA.enabled = true;
    this.eqB = new SP.ThreeBandEQ(sr);
    this.eqB.enabled = true;

    // --- Per-Deck Filters (lowpass + highpass combined) ---
    this.filterA = new SP.Filter(SP.Filter.Resonant_Lowpass, sr);
    this.filterA.frequency = 20000;
    this.filterA.resonance = 0.1;
    this.filterA.enabled = false;
    this.filterB = new SP.Filter(SP.Filter.Resonant_Lowpass, sr);
    this.filterB.frequency = 20000;
    this.filterB.resonance = 0.1;
    this.filterB.enabled = false;

    this.hpFilterA = new SP.Filter(SP.Filter.Resonant_Highpass, sr);
    this.hpFilterA.frequency = 20;
    this.hpFilterA.resonance = 0.1;
    this.hpFilterA.enabled = false;
    this.hpFilterB = new SP.Filter(SP.Filter.Resonant_Highpass, sr);
    this.hpFilterB.frequency = 20;
    this.hpFilterB.resonance = 0.1;
    this.hpFilterB.enabled = false;

    // --- Shared Echo ---
    this.echo = new SP.Echo(sr);
    this.echo.enabled = false;
    this.echo.mix = 0.3;

    // --- Compressor on master ---
    this.compressor = new SP.Compressor(sr);
    this.compressor.enabled = true;
    this.compressor.inputGainDb = 0;
    this.compressor.outputGainDb = 0;
    this.compressor.wet = 1;
    this.compressor.attackSec = 0.003;
    this.compressor.releaseSec = 0.3;
    this.compressor.ratio = 3;
    this.compressor.thresholdDb = -6;
    this.compressor.hpCutOffHz = 0;

    // --- Limiter on master ---
    this.limiter = new SP.Limiter(sr);
    this.limiter.enabled = true;
    this.limiter.ceilingDb = -0.3;

    // --- Gains ---
    this.gainA = 1.0;
    this.gainB = 0.0;
    this.masterGain = 1.0;

    // --- Scratch Buffers ---
    // stereo interleaved: buffersize * 2 channels * 4 bytes = buffersize * 8
    // plus safety margin
    this.bufferA = new SP.Float32Buffer(4096);
    this.bufferB = new SP.Float32Buffer(4096);
    this.mixBuffer = new SP.Float32Buffer(4096);

    // --- State Tracking ---
    this.activeDeck = 'A';  // which deck is currently "main"
    this.fading = false;
    this.positionTimer = 0;

    this.sendMessageToMainScope({ event: 'ready' });
  }

  onDestruct() {
    this.playerA.destruct();
    this.playerB.destruct();
    this.eqA.destruct();
    this.eqB.destruct();
    this.filterA.destruct();
    this.filterB.destruct();
    this.hpFilterA.destruct();
    this.hpFilterB.destruct();
    this.echo.destruct();
    this.compressor.destruct();
    this.limiter.destruct();
    this.bufferA.free();
    this.bufferB.free();
    this.mixBuffer.free();
  }

  onMessageFromMainScope(message) {
    const SP = this.Superpowered;

    if (message.SuperpoweredLoaded) {
      // Audio file has been downloaded and decoded
      const buffer = message.SuperpoweredLoaded.buffer;
      const url = message.SuperpoweredLoaded.url;
      const pointer = SP.arrayBufferToWASM(buffer);
      const deck = message.SuperpoweredLoaded.__deck || this._pendingLoadDeck || 'A';

      const player = deck === 'A' ? this.playerA : this.playerB;
      player.pause(0, 0);
      player.openMemory(pointer, false, false);

      // Report duration & loaded event
      const durMs = player.getDurationMs();
      this.sendMessageToMainScope({
        event: 'trackLoaded',
        deck: deck,
        durationMs: durMs,
        url: url,
      });
      return;
    }

    switch (message.type) {
      case 'loadTrack': {
        this._pendingLoadDeck = message.deck;
        SP.downloadAndDecode(message.url, this);
        break;
      }

      case 'play': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.play();
        break;
      }

      case 'pause': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.pause(0, 0);
        break;
      }

      case 'togglePlayback': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.togglePlayback();
        break;
      }

      case 'seek': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.seek(message.percent);
        break;
      }

      case 'setPosition': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.setPosition(message.ms, false, false, false, false);
        break;
      }

      case 'setGain': {
        if (message.deck === 'A') this.gainA = message.value;
        else this.gainB = message.value;
        break;
      }

      case 'setMasterGain': {
        this.masterGain = message.value;
        break;
      }

      case 'setPlaybackRate': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.playbackRate = message.value;
        break;
      }

      case 'setPitch': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.pitchShiftCents = message.cents;
        break;
      }

      case 'setTimeStretching': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.timeStretching = message.enabled;
        break;
      }

      case 'setBpm': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.originalBPM = message.bpm;
        if (message.firstBeatMs != null) player.firstBeatMs = message.firstBeatMs;
        break;
      }

      case 'syncToBpm': {
        const player = message.deck === 'A' ? this.playerA : this.playerB;
        player.syncMode = SP.AdvancedAudioPlayer.SyncMode_TempoAndBeat;
        player.syncToBpm = message.bpm;
        break;
      }

      case 'setEq': {
        const eq = message.deck === 'A' ? this.eqA : this.eqB;
        if (message.low != null) eq.low = message.low;
        if (message.mid != null) eq.mid = message.mid;
        if (message.high != null) eq.high = message.high;
        break;
      }

      case 'setFilter': {
        const lpFilter = message.deck === 'A' ? this.filterA : this.filterB;
        const hpFilter = message.deck === 'A' ? this.hpFilterA : this.hpFilterB;
        if (message.lowpassHz != null) {
          lpFilter.frequency = message.lowpassHz;
          lpFilter.enabled = message.lowpassHz < 19500;
        }
        if (message.highpassHz != null) {
          hpFilter.frequency = message.highpassHz;
          hpFilter.enabled = message.highpassHz > 25;
        }
        break;
      }

      case 'setEcho': {
        this.echo.enabled = !!message.enabled;
        if (message.mix != null) this.echo.mix = message.mix;
        if (message.decay != null) this.echo.decay = message.decay;
        break;
      }

      case 'setCompressor': {
        if (message.enabled != null) this.compressor.enabled = message.enabled;
        if (message.thresholdDb != null) this.compressor.thresholdDb = message.thresholdDb;
        if (message.ratio != null) this.compressor.ratio = message.ratio;
        break;
      }

      case 'crossfade': {
        // Crossfade: 0 = full A, 1 = full B
        const pos = Math.max(0, Math.min(1, message.position));
        this.gainA = Math.cos(pos * Math.PI * 0.5);
        this.gainB = Math.sin(pos * Math.PI * 0.5);
        break;
      }

      case 'transitionAutomation': {
        // Apply a batch of automation points as immediate settings
        const pt = message.point;
        if (!pt) break;
        const fromEq = pt.target === 'from'
          ? (this.activeDeck === 'A' ? this.eqA : this.eqB)
          : (this.activeDeck === 'A' ? this.eqB : this.eqA);
        const fromFilter = pt.target === 'from'
          ? (this.activeDeck === 'A' ? this.filterA : this.filterB)
          : (this.activeDeck === 'A' ? this.filterB : this.filterA);
        const fromHpFilter = pt.target === 'from'
          ? (this.activeDeck === 'A' ? this.hpFilterA : this.hpFilterB)
          : (this.activeDeck === 'A' ? this.hpFilterB : this.hpFilterA);

        // Gain
        if (pt.target === 'from') {
          if (this.activeDeck === 'A') this.gainA = Math.pow(10, pt.gain_db / 20);
          else this.gainB = Math.pow(10, pt.gain_db / 20);
        } else {
          if (this.activeDeck === 'A') this.gainB = Math.pow(10, pt.gain_db / 20);
          else this.gainA = Math.pow(10, pt.gain_db / 20);
        }
        // Filter
        fromFilter.frequency = pt.lowpass_hz;
        fromFilter.enabled = pt.lowpass_hz < 19500;
        fromHpFilter.frequency = pt.highpass_hz;
        fromHpFilter.enabled = pt.highpass_hz > 25;
        // EQ (convert dB to linear ratio for ThreeBandEQ)
        fromEq.low = Math.pow(10, pt.eq_low_db / 20);
        fromEq.mid = Math.pow(10, pt.eq_mid_db / 20);
        fromEq.high = Math.pow(10, pt.eq_high_db / 20);
        break;
      }

      case 'setActiveDeck': {
        this.activeDeck = message.deck;
        break;
      }

      case 'getPositions': {
        // Return current positions for UI updates
        this.sendMessageToMainScope({
          event: 'positions',
          aPosMs: this.playerA.getDisplayPositionMs(),
          aDurMs: this.playerA.getDurationMs(),
          aPlaying: this.playerA.isPlaying(),
          aBpm: this.playerA.getCurrentBpm(),
          aEof: this.playerA.eofRecently(),
          bPosMs: this.playerB.getDisplayPositionMs(),
          bDurMs: this.playerB.getDurationMs(),
          bPlaying: this.playerB.isPlaying(),
          bBpm: this.playerB.getCurrentBpm(),
          bEof: this.playerB.eofRecently(),
        });
        break;
      }
    }
  }

  processAudio(inputBuffer, outputBuffer, buffersize, parameters) {
    const SP = this.Superpowered;

    // Update sample rates
    this.playerA.outputSamplerate = this.samplerate;
    this.playerB.outputSamplerate = this.samplerate;
    this.eqA.samplerate = this.samplerate;
    this.eqB.samplerate = this.samplerate;
    this.filterA.samplerate = this.samplerate;
    this.filterB.samplerate = this.samplerate;
    this.hpFilterA.samplerate = this.samplerate;
    this.hpFilterB.samplerate = this.samplerate;
    this.echo.samplerate = this.samplerate;
    this.compressor.samplerate = this.samplerate;
    this.limiter.samplerate = this.samplerate;

    // Process Deck A: Player -> EQ -> Filters
    const hasA = this.playerA.processStereo(this.bufferA.pointer, false, buffersize, this.gainA);
    if (hasA) {
      this.eqA.process(this.bufferA.pointer, this.bufferA.pointer, buffersize);
      if (this.filterA.enabled) {
        this.filterA.process(this.bufferA.pointer, this.bufferA.pointer, buffersize);
      }
      if (this.hpFilterA.enabled) {
        this.hpFilterA.process(this.bufferA.pointer, this.bufferA.pointer, buffersize);
      }
    }

    // Process Deck B: Player -> EQ -> Filters
    const hasB = this.playerB.processStereo(this.bufferB.pointer, false, buffersize, this.gainB);
    if (hasB) {
      this.eqB.process(this.bufferB.pointer, this.bufferB.pointer, buffersize);
      if (this.filterB.enabled) {
        this.filterB.process(this.bufferB.pointer, this.bufferB.pointer, buffersize);
      }
      if (this.hpFilterB.enabled) {
        this.hpFilterB.process(this.bufferB.pointer, this.bufferB.pointer, buffersize);
      }
    }

    // Mix A + B
    if (hasA && hasB) {
      // Add B into A buffer
      SP.Add2(this.bufferA.pointer, this.bufferB.pointer, outputBuffer.pointer, buffersize);
    } else if (hasA) {
      SP.Copy(this.bufferA.pointer, outputBuffer.pointer, buffersize * 2);
    } else if (hasB) {
      SP.Copy(this.bufferB.pointer, outputBuffer.pointer, buffersize * 2);
    } else {
      SP.memorySet(outputBuffer.pointer, 0, buffersize * 8);
      return;
    }

    // Apply Echo
    if (this.echo.enabled) {
      this.echo.process(outputBuffer.pointer, outputBuffer.pointer, buffersize);
    }

    // Apply Compressor
    if (this.compressor.enabled) {
      this.compressor.process(outputBuffer.pointer, outputBuffer.pointer, buffersize);
    }

    // Apply Limiter
    if (this.limiter.enabled) {
      this.limiter.process(outputBuffer.pointer, outputBuffer.pointer, buffersize);
    }

    // Apply master volume
    if (this.masterGain !== 1.0) {
      SP.Volume(outputBuffer.pointer, outputBuffer.pointer, this.masterGain, this.masterGain, buffersize);
    }

    // Periodic position reporting (every ~50ms = about every 2nd callback at 128 frames/44100 Hz)
    this.positionTimer++;
    if (this.positionTimer >= 17) {
      this.positionTimer = 0;
      this.sendMessageToMainScope({
        event: 'positions',
        aPosMs: this.playerA.getDisplayPositionMs(),
        aDurMs: this.playerA.getDurationMs(),
        aPlaying: this.playerA.isPlaying(),
        aEof: this.playerA.eofRecently(),
        bPosMs: this.playerB.getDisplayPositionMs(),
        bDurMs: this.playerB.getDurationMs(),
        bPlaying: this.playerB.isPlaying(),
        bEof: this.playerB.eofRecently(),
      });
    }
  }
}

if (typeof AudioWorkletProcessor !== 'undefined') {
  registerProcessor('DjProcessor', DjProcessor);
}
export default DjProcessor;
