import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import AnnotationPortal from './AnnotationPortal'

describe('AnnotationPortal editorial shell', () => {
  it('keeps the shared pilot workflow inside the numbered online workspace', () => {
    const html = renderToStaticMarkup(<AnnotationPortal />)

    expect(html).toContain('annotation-portal')
    expect(html).toContain('annotation-header')
    expect(html).toContain('>03<')
    expect(html).toContain('ONLINE')
    expect(html).toContain('annotation-workbench')
  })
})
