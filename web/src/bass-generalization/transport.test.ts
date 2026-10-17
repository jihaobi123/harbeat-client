import {afterEach,expect,it,vi} from 'vitest'
import {CoveragePlayer,type CoverageCase} from './transport'
class Param{value=0;setValueAtTime(){}linearRampToValueAtTime(){}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;connect(){}disconnect(){}start(...args:any[]){started.push(args)}stop(){}}
const started:any[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){return new Node()}createBufferSource(){return new Node()}async resume(){}async close(){}}
class Worklet extends Node{port={postMessage:vi.fn(),onmessage:null}}
let player:CoveragePlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():CoverageCase{
 const assets=Object.fromEntries(['a','bEntry','bBody'].flatMap(part=>['Master','Bass'].map(layer=>[part+layer,{url:part+layer,sha256:part+layer,duration:part==='a'?12:8,bytes:1}])))
 return {id:'case',aTitle:'a',bTitle:'b',pre:4,post:8,timing:{duckStart:2,swapStart:3.5,swapEnd:4},bpm:[120,120],planSha256:'frozen',assets,plan:{id:'plan',start:10,end:18,duration:8,rate:1,window:{start:20,end:28},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}},sourceVerification:{}} as unknown as CoverageCase
}
async function setup(){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new CoveragePlayer(new URL('https://example.test/'),()=>{});await player.initialize();player.cache!.load=vi.fn(async asset=>({duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as AudioBuffer));return player}
it('retains fixed plan, EQ, all non-bass reference curves across arms and restores native B at takeover',async()=>{
 const p=await setup(),c=example(),before=JSON.stringify(c);await p.play(c,'reference');const first=p.logs.find(x=>x.kind==='bass_started')!;await p.play(c,'stem');const second=p.logs.filter(x=>x.kind==='bass_started').at(-1)!
 expect(first.plan).toEqual(second.plan);expect(first.plan).toEqual(c.plan)
 for(const side of ['a','b'])expect(first.curves[side].rest).toEqual(second.curves[side].rest)
 expect(first.curves.a.bass).not.toEqual(second.curves.a.bass)
 expect(started.length).toBe(12);expect(started.slice(-6).filter(x=>x[0]===12.1)).toHaveLength(2)
 expect(JSON.stringify(c)).toBe(before)
})
it('does not schedule obsolete sources after a stop during preparation',async()=>{
 const p=await setup();let resolve!:(b:AudioBuffer)=>void;const waiting=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn(()=>waiting)
 const playing=p.play(example(),'stem');await Promise.resolve();await Promise.resolve();p.stop();resolve({} as AudioBuffer);await playing
 expect(started).toHaveLength(0);expect(p.state.status).toBe('idle');expect(p.logs.some(x=>x.kind==='bass_finished')).toBe(false)
})
it('completes exactly once and retains errors for export',async()=>{
 const p=await setup();await p.play(example(),'stem');(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(160)
 expect(p.state.status).toBe('complete');expect(p.logs.filter(x=>x.kind==='bass_finished')).toHaveLength(1)
 p.cache!.load=vi.fn(async()=>{throw Error('bad hash')});await p.play(example(),'reference');expect(p.state.status).toBe('error');expect(p.logs.some(x=>x.kind==='bass_failed'&&x.message==='bad hash')).toBe(true)
})

it('applies the fixed additional shelf only in EQ arm and preserves blind attribution',async()=>{
 const p=await setup(),c=example();await p.play(c,'eq',{roundId:'round1',letter:'C'})
 const log=p.logs.find(x=>x.kind==='bass_started')!
 expect(log.treatment.settings).toEqual({frequency:140,maxCutDb:18})
 expect(log.treatment.low.a.at(-1)[1]).toBe(-18);expect(log.treatment.low.b.at(-1)[1]).toBe(0)
 expect(log.curves.a.bass).toEqual(log.curves.a.rest)
 expect(log.roundId).toBe('round1');expect(log.letter).toBe('C')
 ;(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(160)
 expect(p.state.status).toBe('complete');expect(p.state.roundId).toBe('round1');expect(p.state.letter).toBe('C')
})
