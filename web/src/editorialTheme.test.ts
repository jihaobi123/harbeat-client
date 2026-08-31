import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const css = readFileSync(fileURLToPath(new URL('./index.css', import.meta.url)), 'utf8')

describe('editorial theme contract', () => {
  it('bundles typography without a runtime font request', () => {
    expect(css).not.toContain('fonts.googleapis.com')
    expect(css).toContain("--editorial-font-display: 'Oswald'")
  })

  it('defines the approved palette and hard-edge components', () => {
    expect(css).toContain('--editorial-acid: #c9f400')
    expect(css).toContain('.editorial-section__heading')
    expect(css).toContain('.status-tag--online')
  })

  it('supports mobile layouts and reduced motion', () => {
    expect(css).toContain('@media (max-width: 767px)')
    expect(css).toContain('@media (prefers-reduced-motion: reduce)')
  })
})
