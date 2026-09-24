import {afterEach,describe,expect,it,vi} from 'vitest'
import {AudioCache,AudioBufferPool} from './cache'
const base=new URL('https://example.test/audio/'),body=new Uint8Array([1,2,3]).buffer
const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',body))).map(x=>x.toString(16).padStart(2,'0')).join('')
const asset={url:'song.flac',sha256:hash,duration:10,bytes:3}
function ctx(size=80){return {sampleRate:44100,decodeAudioData:vi.fn(async()=>({duration:10,length:size/8,numberOfChannels:2}))} as unknown as AudioContext}
afterEach(()=>vi.unstubAllGlobals())
describe('bounded audio pool across player recreation',()=>{
 it('reuses verified PCM after disposing the first player without another fetch or decode',async()=>{
  const fetcher=vi.fn(async(_url?:unknown)=>new Response(body));vi.stubGlobal('fetch',fetcher)
  const pool=new AudioBufferPool(),c1=ctx(),c2=ctx(),one=new AudioCache(c1,base,()=>{},pool)
  const original=await one.load(asset);one.dispose()
  const two=new AudioCache(c2,base,()=>{},pool)
  expect(await two.load(asset)).toBe(original);expect(fetcher).toHaveBeenCalledTimes(1);expect(c2.decodeAudioData).not.toHaveBeenCalled();two.dispose()
 })
 it('coalesces installed PCM when two owners finish the same asset concurrently',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(_url?:unknown)=>new Response(body)));const pool=new AudioBufferPool(80),one=new AudioCache(ctx(),base,()=>{},pool),two=new AudioCache(ctx(),base,()=>{},pool)
  one.protected.add(asset.url);two.protected.add(asset.url)
  const [a,b]=await Promise.all([one.load(asset),two.load(asset)]);expect(a).toBe(b);expect(pool.bytes).toBe(80);one.dispose();two.dispose()
 })
 it('rejects a different hash at the same URL rather than using stale PCM',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(_url?:unknown)=>new Response(body)));const pool=new AudioBufferPool(),one=new AudioCache(ctx(),base,()=>{},pool)
  await one.load(asset);one.dispose();const two=new AudioCache(ctx(),base,()=>{},pool)
  await expect(two.load({...asset,sha256:'0'.repeat(64)})).rejects.toThrow('校验失败');expect(two.ready.has(asset.url)).toBe(false)
 })
 it('evicts unprotected PCM, enforces one shared budget and keeps active audio',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(_url?:unknown)=>new Response(body)));const pool=new AudioBufferPool(160),one=new AudioCache(ctx(),base,()=>{},pool)
  one.protected.add(asset.url);const a=await one.load(asset);await one.load({...asset,url:'b.flac'})
  const two=new AudioCache(ctx(),base,()=>{},pool);await two.load({...asset,url:'c.flac'})
  expect(one.buffers.get(asset.url)).toBe(a);expect(one.buffers.has('b.flac')).toBe(false);expect(pool.bytes).toBe(160)
  two.protected.add('c.flac');await expect(two.load({...asset,url:'d.flac'})).rejects.toThrow('内存不足');one.dispose();two.dispose()
 })
 it('does not wait for a stalled disk write before making audio playable',async()=>{
  let release!:()=>void;const disk=new Promise<void>(r=>release=r)
  vi.stubGlobal('caches',{open:async()=>({match:async()=>undefined,keys:async()=>[],put:async()=>disk})})
  vi.stubGlobal('fetch',vi.fn(async(_url?:unknown)=>new Response(body)))
  const cache=new AudioCache(ctx(),base,()=>{});let timer:ReturnType<typeof setTimeout>|undefined
  try{const result=await Promise.race([cache.load(asset),new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('disk blocked playback')),1000)})]);expect(result.duration).toBe(10)}finally{release();clearTimeout(timer);cache.dispose()}
 })
 it('uses a fingerprint in the HTTP cache URL, checks duration and fails closed after disposal',async()=>{
  const fetcher=vi.fn(async(_url?:unknown)=>new Response(body));vi.stubGlobal('fetch',fetcher);const cache=new AudioCache(ctx(),base,()=>{})
  await expect(cache.load({...asset,duration:11})).rejects.toThrow('时长');expect(String(fetcher.mock.calls[0][0])).toContain('sha256='+hash)
  cache.dispose();await expect(cache.load(asset)).rejects.toThrow('播放器已关闭')
 })
})


it('aborts an abandoned sole load and never installs its decoded result',async()=>{
 let release!:(value:AudioBuffer)=>void
 const decoder=ctx();(decoder.decodeAudioData as any)=vi.fn(()=>new Promise<AudioBuffer>(r=>release=r))
 vi.stubGlobal('fetch',vi.fn(async()=>new Response(body)))
 const cache=new AudioCache(decoder,base,()=>{}),controller=new AbortController()
 const work=cache.load(asset,controller.signal);const rejected=expect(work).rejects.toMatchObject({name:'AbortError'})
 for(let i=0;i<20&&!release;i++)await new Promise(r=>setTimeout(r,0))
 controller.abort();release({duration:10,length:10,numberOfChannels:2} as AudioBuffer)
 await rejected;await Promise.resolve();expect(cache.ready.size).toBe(0);cache.dispose()
})
it('cancelling one coalesced waiter does not cancel another owner of that load',async()=>{
 let release!:()=>void;const hold=new Promise<void>(r=>release=r)
 vi.stubGlobal('fetch',vi.fn(async()=>{await hold;return new Response(body)}))
 const cache=new AudioCache(ctx(),base,()=>{}),controller=new AbortController()
 const abandoned=cache.load(asset,controller.signal),retained=cache.load(asset)
 const rejected=expect(abandoned).rejects.toMatchObject({name:'AbortError'});controller.abort();release()
 await rejected;expect((await retained).duration).toBe(10);expect(cache.ready.has(asset.url)).toBe(true);cache.dispose()
})
