import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import PlaylistImportModal from './PlaylistImportModal'
import UploadModal from './UploadModal'

describe('editorial modal flows', () => {
  it('keeps upload inside the numbered dialog shell', () => {
    const html = renderToStaticMarkup(<UploadModal onClose={() => undefined} />)

    expect(html).toContain('editorial-modal-backdrop')
    expect(html).toContain('editorial-modal__heading')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('>07<')
  })

  it('keeps playlist import inside the numbered dialog shell', () => {
    const html = renderToStaticMarkup(<PlaylistImportModal onClose={() => undefined} />)

    expect(html).toContain('editorial-modal-backdrop')
    expect(html).toContain('editorial-modal__heading')
    expect(html).toContain('aria-modal="true"')
    expect(html).toContain('>08<')
  })
})
