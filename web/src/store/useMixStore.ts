import { create } from 'zustand';
import type { QualityMode, RenderEngine, OutputFormat } from '../types/api';

interface MixState {
  style: string;
  durationMinutes: number;
  sceneType: string | null;
  styleRatios: Record<string, number>;
  qualityMode: QualityMode;
  renderEngine: RenderEngine;
  diversity: number;
  outputFormat: OutputFormat;
  bpm: number | null;
  energy: string | null;

  setStyle: (s: string) => void;
  setDuration: (m: number) => void;
  setSceneType: (s: string | null) => void;
  setStyleRatio: (style: string, ratio: number) => void;
  setQualityMode: (m: QualityMode) => void;
  setRenderEngine: (e: RenderEngine) => void;
  setDiversity: (d: number) => void;
  setOutputFormat: (f: OutputFormat) => void;
  setBpm: (b: number | null) => void;
  setEnergy: (e: string | null) => void;
  reset: () => void;
}

const DEFAULTS = {
  style: 'hiphop',
  durationMinutes: 15,
  sceneType: null as string | null,
  styleRatios: {} as Record<string, number>,
  qualityMode: 'fast' as QualityMode,
  renderEngine: 'groove' as RenderEngine,
  diversity: 0.35,
  outputFormat: 'both' as OutputFormat,
  bpm: null as number | null,
  energy: null as string | null,
};

export const useMixStore = create<MixState>((set) => ({
  ...DEFAULTS,

  setStyle: (s) => set({ style: s }),
  setDuration: (m) => set({ durationMinutes: m }),
  setSceneType: (s) => set({ sceneType: s }),
  setStyleRatio: (style, ratio) =>
    set((state) => ({
      styleRatios: { ...state.styleRatios, [style]: ratio },
    })),
  setQualityMode: (m) => set({ qualityMode: m }),
  setRenderEngine: (e) => set({ renderEngine: e }),
  setDiversity: (d) => set({ diversity: d }),
  setOutputFormat: (f) => set({ outputFormat: f }),
  setBpm: (b) => set({ bpm: b }),
  setEnergy: (e) => set({ energy: e }),
  reset: () => set(DEFAULTS),
}));
