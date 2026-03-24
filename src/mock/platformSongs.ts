import { Song } from '../types'

function generateBeatPoints(bpm: number, duration: number): number[] {
  const interval = 60 / bpm
  const points: number[] = []
  for (let t = 0; t < duration; t += interval) {
    points.push(Math.round(t * 1000) / 1000)
  }
  return points
}

export const platformSongs: Song[] = [
  {
    id: 'platform-1',
    title: 'Midnight Groove',
    artist: 'ChillBeats Studio',
    duration: 245,
    format: 'mp3',
    fileSize: 5876000,
    sourceType: 'internal_catalog',
    sourcePath: '',
    importStatus: 'ready',
    analysisStatus: 'completed',
    bpm: 98,
    beatPoints: generateBeatPoints(98, 245),
    cuePoints: [
      { id: 'cue-p1-1', time: 0, label: 'Intro', color: '#22c55e' },
      { id: 'cue-p1-2', time: 32, label: 'Verse 1', color: '#3b82f6' },
      { id: 'cue-p1-3', time: 96, label: 'Chorus', color: '#ef4444' },
      { id: 'cue-p1-4', time: 180, label: 'Outro', color: '#64748b' },
    ],
    createdAt: Date.now() - 86400000 * 7,
  },
  {
    id: 'platform-2',
    title: 'Electric Dreams',
    artist: 'Synthwave Lab',
    duration: 312,
    format: 'aac',
    fileSize: 7234000,
    sourceType: 'internal_catalog',
    sourcePath: '',
    importStatus: 'ready',
    analysisStatus: 'completed',
    bpm: 128,
    beatPoints: generateBeatPoints(128, 312),
    cuePoints: [
      { id: 'cue-p2-1', time: 0, label: 'Intro', color: '#22c55e' },
      { id: 'cue-p2-2', time: 16, label: 'Build Up', color: '#f59e0b' },
      { id: 'cue-p2-3', time: 48, label: 'Drop', color: '#ef4444' },
    ],
    createdAt: Date.now() - 86400000 * 3,
  },
  {
    id: 'platform-3',
    title: 'Acoustic Morning',
    artist: 'Lo-Fi Collective',
    duration: 198,
    format: 'mp3',
    fileSize: 4567000,
    sourceType: 'internal_catalog',
    sourcePath: '',
    importStatus: 'ready',
    analysisStatus: 'completed',
    bpm: 85,
    beatPoints: generateBeatPoints(85, 198),
    cuePoints: [
      { id: 'cue-p3-1', time: 0, label: 'Intro', color: '#22c55e' },
      { id: 'cue-p3-2', time: 24, label: 'Main Theme', color: '#3b82f6' },
    ],
    createdAt: Date.now() - 86400000,
  },
  {
    id: 'platform-4',
    title: 'Urban Pulse',
    artist: 'Beat Factory',
    duration: 275,
    format: 'm4a',
    fileSize: 6890000,
    sourceType: 'internal_catalog',
    sourcePath: '',
    importStatus: 'ready',
    analysisStatus: 'completed',
    bpm: 110,
    beatPoints: generateBeatPoints(110, 275),
    cuePoints: [
      { id: 'cue-p4-1', time: 0, label: 'Intro', color: '#22c55e' },
      { id: 'cue-p4-2', time: 20, label: 'Groove', color: '#a855f7' },
      { id: 'cue-p4-3', time: 80, label: 'Bridge', color: '#f59e0b' },
      { id: 'cue-p4-4', time: 200, label: 'Outro', color: '#64748b' },
    ],
    createdAt: Date.now() - 86400000 * 5,
  },
  {
    id: 'platform-5',
    title: 'Neon Lights',
    artist: 'Future Sound',
    duration: 220,
    format: 'mp3',
    fileSize: 5234000,
    sourceType: 'internal_catalog',
    sourcePath: '',
    importStatus: 'ready',
    analysisStatus: 'none',
    bpm: null,
    beatPoints: [],
    cuePoints: [],
    createdAt: Date.now() - 86400000 * 2,
  },
]
