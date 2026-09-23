import {afterEach,it,expect,vi} from 'vitest'
import {readEncoded,storeEncoded,deleteEncoded,AUDIO_CACHE_NAME} from './encodedCache'
const saved=new Map<string,Response>()
function setup(){
 saved.clear()
 vi.stubGlobal('caches',{open:vi.fn(async()=>({
  match:async(k:string|Request)=>saved.get(typeof k==='string'?k:k.url)?.clone(),
  keys:async()=>[...saved.keys()].map(url=>new Request(url)),
  delete:async(k:string|Request)=>saved.delete(typeof k==='string'?k:k.url),
  put:async(k:string,r:Response)=>{saved.set(k,r.clone())}
 }))})
}
afterEach(()=>vi.unstubAllGlobals())
it('stores exact encoded bytes independently of the browser HTTP cache',async()=>{setup();const bytes=new Uint8Array([5,6,7]).buffer;await storeEncoded('https://a.test/a',bytes);expect(new Uint8Array((await readEncoded('https://a.test/a'))!)).toEqual(new Uint8Array(bytes));expect(caches.open).toHaveBeenCalledWith(AUDIO_CACHE_NAME);await deleteEncoded('https://a.test/a');expect(await readEncoded('https://a.test/a')).toBeNull()})
it('evicts only oldest entries inside the audio cache to enforce the byte budget',async()=>{setup();await storeEncoded('https://a.test/a',new ArrayBuffer(8),16);await storeEncoded('https://a.test/b',new ArrayBuffer(8),16);await storeEncoded('https://a.test/c',new ArrayBuffer(8),16);expect([...saved.keys()]).toEqual(['https://a.test/b','https://a.test/c'])})
it('continues playback when persistent caching is unavailable or full',async()=>{vi.stubGlobal('caches',{open:async()=>{throw Error('quota')}});expect(await readEncoded('https://a.test/a')).toBeNull();await expect(storeEncoded('https://a.test/a',new ArrayBuffer(1))).resolves.toBeUndefined()})
