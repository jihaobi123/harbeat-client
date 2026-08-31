import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import SeamlessPlayer from './SeamlessPlayer'
import WaveformPlayer from './WaveformPlayer'
import type { LibrarySong } from '../types'

const song: LibrarySong = {
  id: 'song-1',
  user_id: 1,
  title: 'After Midnight',
  artist: 'HarBeat',
  duration: 180,
  format: 'mp3',
  file_size: 1024,
  source_type: 'upload',
  source_path: '/music/after-midnight.mp3',
  platform_id: null,
  platform_url: null,
  bpm: 96,
  key: 'Am',
  camelot_key: '8A',
  energy: 0.7,
  analysis_status: 'completed',
  beat_points: [],
  cue_points: [],
  stems: null,
  created_at: '2026-08-31T00:00:00Z',
  updated_at: '2026-08-31T00:00:00Z',
}

describe('playback accessibility contracts', () => {
  it('names transport, seek, and DJ controls', () => {
    const html = renderToStaticMarkup(
      <SeamlessPlayer tracks={[{
        songId: 1,
        title: song.title,
        artist: song.artist,
        filePath: song.source_path,
        duration: song.duration,
      }]} />,
    )

    expect(html).toContain('aria-label="上一首"')
    expect(html).toContain('aria-label="播放连续混音"')
    expect(html).toContain('aria-label="连续混音播放位置"')
    expect(html).toContain('aria-label="交叉淡化强度"')
    expect(html).toContain('aria-pressed="true"')
  })

  it('exposes waveform playback, seeking, mute, and volume controls', () => {
    const html = renderToStaticMarkup(<WaveformPlayer song={song} />)

    expect(html).toContain('aria-label="后退 5 秒"')
    expect(html).toContain('aria-label="播放波形音频"')
    expect(html).toContain('aria-label="波形播放位置"')
    expect(html).toContain('aria-label="静音"')
    expect(html).toContain('aria-label="音量"')
  })
})
