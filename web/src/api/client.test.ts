import { afterEach, describe, expect, it, vi } from 'vitest'

import { getPresenceAnnotations } from './client'


afterEach(() => vi.unstubAllGlobals())


describe('API errors', () => {
  it('preserves HTTP status so the annotation UI only generates after a 404', async () => {
    vi.stubGlobal('localStorage', { getItem: () => null })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'no presence annotations' }),
    }))

    await expect(getPresenceAnnotations('song-1')).rejects.toEqual(
      expect.objectContaining({
        status: 404,
        message: 'no presence annotations',
      }),
    )
  })
})
