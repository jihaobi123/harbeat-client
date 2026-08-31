import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import DjControlPanel from './DjControlPanel'
import PlatformSearch from './PlatformSearch'
import ProfilePanel from './ProfilePanel'
import RecommendPanel from './RecommendPanel'
import SessionPanel from './SessionPanel'
import SongList, { SongRow } from './SongList'
import type { LibrarySong } from '../types'

describe('editorial feature panels', () => {
  it.each([
    ['library', <SongList />, '01'],
    ['search', <PlatformSearch />, '02'],
    ['discover', <RecommendPanel />, '03'],
    ['session', <SessionPanel />, '04'],
    ['dj', <DjControlPanel />, '05'],
    ['profile', <ProfilePanel />, '06'],
  ])('wraps %s in the numbered feature hierarchy', (name, panel, number) => {
    const html = renderToStaticMarkup(panel)

    expect(html).toContain(`feature-panel--${name}`)
    expect(html).toContain('feature-panel__heading')
    expect(html).toContain(`>${number}<`)
  })

  it('keeps song selection and row actions as separate visible-focus controls', () => {
    const song: LibrarySong = {
      id: 'song-1', user_id: 1, title: 'After Midnight', artist: 'HarBeat',
      duration: 180, format: 'mp3', file_size: 1024, source_type: 'upload',
      source_path: '/music/after-midnight.mp3', platform_id: null, platform_url: null,
      bpm: 96, key: 'Am', camelot_key: '8A', energy: 0.7,
      analysis_status: 'completed', beat_points: [], cue_points: [], stems: null,
      created_at: '2026-08-31T00:00:00Z', updated_at: '2026-08-31T00:00:00Z',
    }
    const html = renderToStaticMarkup(<SongRow song={song} />)

    expect(html).toContain('role="listitem"')
    expect(html).toContain('aria-pressed="false"')
    expect(html).toContain('class="song-list-row__select')
    expect(html).toContain('class="song-row-action')
    expect(html).toContain('aria-label="将 After Midnight 添加到歌单"')
  })
})
