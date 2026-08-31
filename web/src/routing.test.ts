import { describe, expect, it } from 'vitest'

import { isAnnotationRoute } from './routing'


describe('top-level route selection', () => {
  it('keeps the old site at root and selects only the annotation path', () => {
    expect(isAnnotationRoute('/')).toBe(false)
    expect(isAnnotationRoute('/library')).toBe(false)
    expect(isAnnotationRoute('/annotate')).toBe(true)
    expect(isAnnotationRoute('/annotate/')).toBe(true)
  })
})
