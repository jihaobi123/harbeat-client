import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  getBarAnnotationAudioUrl,
  getBarAnnotationStemUrl,
  getPilotAnnotationTracks,
  getPresenceAnnotations,
} from './client'


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


describe('public annotation API', () => {
  it('loads the shared Pilot catalog with the current login token', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'pilot-token' })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ code: 0, message: 'ok', data: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getPilotAnnotationTracks()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/bar-annotations/pilot/tracks',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer pilot-token' }),
      }),
    )
  })

  it('builds an allowlisted audio URL instead of the private stream URL', () => {
    vi.stubGlobal('localStorage', { getItem: () => 'pilot-token' })
    expect(getBarAnnotationAudioUrl('song 1')).toBe(
      '/api/bar-annotations/tracks/song%201/audio?token=pilot-token',
    )
  })

  it('builds an allowlisted Stem URL with encoded path segments', () => {
    vi.stubGlobal('localStorage', { getItem: () => 'pilot-token' })
    expect(getBarAnnotationStemUrl('song 1', 'vocals')).toBe(
      '/api/bar-annotations/tracks/song%201/stems/vocals?token=pilot-token',
    )
  })
})
