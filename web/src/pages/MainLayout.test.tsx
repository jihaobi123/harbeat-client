import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import MainLayout from './MainLayout'

describe('MainLayout editorial shell', () => {
  it('keeps desktop navigation and exposes the grouped mobile navigation', () => {
    const html = renderToStaticMarkup(<MainLayout />)

    expect(html).toContain('editorial-app')
    expect(html).toContain('editorial-workspace')
    expect(html).toContain('editorial-mobile-nav')
    expect(html).toContain('音乐')
    expect(html).toContain('发现')
    expect(html).toContain('DJ')
    expect(html).toContain('标注')
    expect(html).toContain('我的')
  })
})
