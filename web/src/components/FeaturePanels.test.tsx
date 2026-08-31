import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import DjControlPanel from './DjControlPanel'
import PlatformSearch from './PlatformSearch'
import ProfilePanel from './ProfilePanel'
import RecommendPanel from './RecommendPanel'
import SessionPanel from './SessionPanel'
import SongList from './SongList'

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
})
