export interface DeckState {
  buffer: AudioBuffer | null;
  /** Last library/catalog song id loaded into this deck (for skipping redundant loads). */
  loadedSongId: number | null;
  sourceNode: AudioBufferSourceNode | null;
  /** First node in the FX chain — connect AudioBufferSource here. */
  eqInput: BiquadFilterNode;
  /** DJ-style strip: high-pass → low shelf → mid → high shelf → low-pass → fader gain. */
  hp: BiquadFilterNode;
  lowShelf: BiquadFilterNode;
  midPeaking: BiquadFilterNode;
  highShelf: BiquadFilterNode;
  lp: BiquadFilterNode;
  gainNode: GainNode;
  isPlaying: boolean;
  startTime: number;
  startOffset: number;
  nextLoopSource: AudioBufferSourceNode | null;
  nextLoopGain: GainNode | null;
}

export interface PendingCrossfade {
  fromDeck: 'A' | 'B';
  toDeck: 'A' | 'B';
  durationSec: number;
  triggered: boolean;
}
