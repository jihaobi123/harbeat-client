import { describe, expect, it, vi } from 'vitest'
import { StemTransport } from './StemTransport'

function harness() {
  const sources:any[] = [], gains:any[] = []
  const context:any = {
    currentTime:10, sampleRate:48000, destination:{}, state:'running',
    resume:vi.fn(async()=>{}), close:vi.fn(async()=>{}),
    decodeAudioData:vi.fn(async()=>({duration:120,length:120*48000,numberOfChannels:2})),
    createBufferSource:()=>{const s={buffer:null,connect:vi.fn(),disconnect:vi.fn(),start:vi.fn(),stop:vi.fn()};sources.push(s);return s},
    createGain:()=>{const g={gain:{value:0,cancelAndHoldAtTime:vi.fn(),setValueAtTime:vi.fn(),linearRampToValueAtTime:vi.fn()},connect:vi.fn(),disconnect:vi.fn()};gains.push(g);return g},
  }
  const fetcher=vi.fn(async()=>new Response(new Uint8Array([1,2,3])))
  const engine=new StemTransport(context,fetcher as typeof fetch)
  const tracks=['master','vocals','drums','bass','other'].map(name=>({name,url:`/${name}`,duration:120,channels:2}))
  return {engine,context,sources,gains,fetcher,tracks}
}

describe('shared stem transport',()=>{
  it('calls the browser fetch function without binding it to the player instance',async()=>{
    const h=harness();let receiver:unknown
    const fetcher=async function(this:unknown){receiver=this;return new Response(new Uint8Array([1]))}
    const e=new StemTransport(h.context,fetcher as typeof fetch)
    await e.prepare([h.tracks[0]]);expect(receiver).toBeUndefined()
  })
  it('keeps playing after rapid consecutive seeks during asynchronous resume',async()=>{
    const h=harness();await h.engine.prepare(h.tracks);await h.engine.play()
    await Promise.all([h.engine.seek(10),h.engine.seek(20),h.engine.seek(30)])
    expect(h.engine.playing).toBe(true);expect(h.engine.position).toBe(30)
  })
  it('starts every prepared track at exactly the same clock time and offset; solo only changes gain',async()=>{
    const h=harness();await h.engine.prepare(h.tracks);h.engine.seek(24);await h.engine.play()
    expect(h.sources).toHaveLength(5)
    for(const s of h.sources)expect(s.start).toHaveBeenCalledWith(10.03,24)
    h.context.currentTime=12.03
    h.engine.select('drums');h.engine.select('bass');h.engine.select('master')
    expect(h.engine.position).toBeCloseTo(26)
    expect(h.fetcher).toHaveBeenCalledTimes(5)
    expect(h.sources).toHaveLength(5)
    expect(h.sources.every(s=>s.stop.mock.calls.length===0)).toBe(true)
    expect(h.gains[0].gain.linearRampToValueAtTime.mock.lastCall[0]).toBe(1)
    expect(h.gains[2].gain.linearRampToValueAtTime.mock.lastCall[0]).toBe(0)
    expect(h.gains[0].gain.linearRampToValueAtTime.mock.lastCall[1]).toBeCloseTo(12.05)
  })
  it('seeks, pauses and resumes all tracks together without downloading again',async()=>{
    const h=harness();await h.engine.prepare(h.tracks);await h.engine.play()
    h.context.currentTime=20.03;h.engine.pause();expect(h.engine.position).toBeCloseTo(10)
    h.engine.seek(48);await h.engine.play()
    for(const s of h.sources.slice(5)){expect(s.start.mock.calls[0][0]).toBeCloseTo(20.06);expect(s.start.mock.calls[0][1]).toBe(48)}
    expect(h.fetcher).toHaveBeenCalledTimes(5)
  })
  it('joins an additional drum track at the running position without restarting the other tracks',async()=>{
    const h=harness();await h.engine.prepare(h.tracks);await h.engine.play();h.context.currentTime=15
    await h.engine.prepare([{name:'drum_kick',url:'/kick'}]);h.engine.select('drum_kick')
    expect(h.sources[5].start.mock.calls[0][1]).toBeCloseTo(5)
    expect(h.sources.slice(0,5).every(s=>s.stop.mock.calls.length===0)).toBe(true)
    await h.engine.prepare(h.tracks);expect(h.fetcher).toHaveBeenCalledTimes(6)
  })
  it('does not replace the audible selection with an unavailable track',async()=>{
    const h=harness();await h.engine.prepare(h.tracks)
    expect(()=>h.engine.select('drum_missing')).toThrow()
    expect(h.engine.selection).toBe('master')
  })
  it('releases decoded audio and stops playback when leaving the song',async()=>{
    const h=harness();await h.engine.prepare(h.tracks);await h.engine.play();h.engine.dispose()
    expect(h.context.close).toHaveBeenCalledOnce();expect(h.engine.readyNames).toEqual([])
    expect(h.sources.every(s=>s.stop.mock.calls.length===1)).toBe(true)
  })
  it('rejects oversized preparation before downloading and leaves failed tracks retryable',async()=>{
    const h=harness()
    await expect(h.engine.prepare([{name:'huge',url:'/huge',duration:7200,channels:2}])).rejects.toThrow('内存')
    expect(h.fetcher).not.toHaveBeenCalled()
    h.fetcher.mockResolvedValueOnce(new Response('missing',{status:404}))
    await expect(h.engine.prepare([h.tracks[0]])).rejects.toThrow('404')
    expect(h.engine.readyNames).toEqual([])
    await h.engine.prepare([h.tracks[0]]);expect(h.engine.readyNames).toEqual(['master'])
  })
  it('does not restart after pause or disposal while browser audio activation is pending',async()=>{
    const h=harness();await h.engine.prepare(h.tracks)
    let resolve!:()=>void;h.context.resume.mockImplementation(()=>new Promise<void>(r=>resolve=r))
    const starting=h.engine.play();h.engine.pause();resolve();await starting
    expect(h.sources).toHaveLength(0)
  })
  it('discards an in-flight decode after changing songs',async()=>{
    const h=harness();let finish!:(buffer:any)=>void
    let entered!:()=>void;const started=new Promise<void>(resolve=>entered=resolve)
    h.context.decodeAudioData.mockImplementation(()=>{entered();return new Promise(resolve=>finish=resolve)})
    const pending=h.engine.prepare([h.tracks[0]])
    const outcome=expect(pending).rejects.toThrow('已离开当前歌曲')
    await started;h.engine.dispose();finish({duration:120,length:5760000,numberOfChannels:2})
    await outcome;expect(h.engine.readyNames).toEqual([]);expect(h.sources).toHaveLength(0)
  })
})
