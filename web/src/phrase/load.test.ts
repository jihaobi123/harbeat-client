import {it,expect,vi,afterEach} from 'vitest'
import {gzipSync} from 'node:zlib'
import {loadJson} from './load'
afterEach(()=>vi.unstubAllGlobals())
it('decodes the compressed evidence without changing source data',async()=>{const value={sha256:'a'.repeat(64),phrases:[{end:14.812}]};const compressed=gzipSync(JSON.stringify(value));vi.stubGlobal('fetch',vi.fn(async()=>new Response(compressed)));expect(await loadJson('catalog.json',new URL('https://example.test/'))).toEqual(value);expect(fetch).toHaveBeenCalledWith(new URL('https://example.test/catalog.json.gz'))})
it('falls back to full JSON if a precompressed snapshot has not been published',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(new Response('',{status:404})).mockResolvedValueOnce(new Response('{"tracks":[]}')));expect(await loadJson('catalog.json',new URL('https://example.test/'))).toEqual({tracks:[]})})
