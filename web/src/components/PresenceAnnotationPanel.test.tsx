import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import PresenceAnnotationPanel from './PresenceAnnotationPanel'
import type { LibrarySong } from '../types'


const song: LibrarySong = {
  id: 'song-1',
  user_id: 7,
  title: 'Pilot song',
  artist: 'HarBeat',
  duration: 120,
  format: 'wav',
  file_size: 1024,
  source_type: 'upload',
  source_path: '/tmp/song.wav',
  platform_id: null,
  platform_url: null,
  bpm: 120,
  key: null,
  camelot_key: null,
  energy: null,
  analysis_status: 'completed',
  beat_points: [],
  cue_points: [],
  stems: { vocals: 'vocals.wav', drums: 'drums.wav', bass: 'bass.wav', other: 'other.wav' },
  created_at: '2026-08-31T00:00:00Z',
  updated_at: '2026-08-31T00:00:00Z',
}


describe('PresenceAnnotationPanel', () => {
  it('starts with an accessible loading state and the annotation title', () => {
    const html = renderToStaticMarkup(<PresenceAnnotationPanel song={song} />)

    expect(html).toContain('元素出现区间审核')
    expect(html).toContain('正在读取标注')
    expect(html).toContain('aria-label="标注试听播放器"')
  })
})
