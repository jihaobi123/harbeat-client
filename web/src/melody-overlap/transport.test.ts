import {afterEach,expect,it,vi} from 'vitest'
import {MelodyPlayer,type MelodyCase} from './transport'
class Param{value=0;setValueAtTime(){}linearRampToValueAtTime(){}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;connect(){}disconnect(){}start(...args:any[]){started.push(args)}stop(){}}
const started:any[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){return new Node()}createBufferSource(){return new Node()}async resume(){}async close(){}}
class Worklet extends Node{port={postMessage:vi.fn(),onmessage:null}}
let player:MelodyPlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():MelodyCase{
 const assets=Object.fromEntries(['a','bEntry','bBody'].flatMap(part=>['Master','Vocal','Drum'].map(layer=>[part+layer,{url:part+layer,sha256:part+layer,duration:part==='a'?12:8,bytes:1}])))
 return {id:'case',aTitle:'a',bTitle:'b',pre:4,post:8,shortStart:6,bpm:[120,120],planSha256:'frozen',assets,plan:{id:'plan',start:10,end:18,duration:8,rate:1,window:{start:20,end:28},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}},sourceVerification:{}} as unknown as MelodyCase
}
async function setup(){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new MelodyPlayer(new URL('https://example.test/'),()=>{});await player.initialize();player.cache!.load=vi.fn(async asset=>({duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as AudioBuffer));return player}
it('retains fixed plan, EQ, drum and vocal curves across arms and restores native B at takeover',async()=>{
 const p=await setup(),c=example(),before=JSON.stringify(c);await p.play(c,'reference');const first=p.logs.find(x=>x.kind==='melody_started')!;await p.play(c,'short');const second=p.logs.filter(x=>x.kind==='melody_started').at(-1)!
 expect(first.plan).toEqual(second.plan);expect(first.plan).toEqual(c.plan)
 for(const side of ['a','b'])for(const layer of ['voice','drums'])expect(first.curves[side][layer]).toEqual(second.curves[side][layer])
 expect(first.curves.a.melody).not.toEqual(second.curves.a.melody)
 expect(started.length).toBe(18);expect(started.slice(-9).filter(x=>x[0]===12.1)).toHaveLength(3)
 expect(JSON.stringify(c)).toBe(before)
})
it('does not schedule obsolete sources after a stop during preparation',async()=>{
 const p=await setup();let resolve!:(b:AudioBuffer)=>void;const waiting=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn(()=>waiting)
 const playing=p.play(example(),'short');await Promise.resolve();await Promise.resolve();p.stop();resolve({} as AudioBuffer);await playing
 expect(started).toHaveLength(0);expect(p.state.status).toBe('idle');expect(p.logs.some(x=>x.kind==='melody_finished')).toBe(false)
})
it('completes exactly once and retains errors for export',async()=>{
 const p=await setup();await p.play(example(),'short');(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(160)
 expect(p.state.status).toBe('complete');expect(p.logs.filter(x=>x.kind==='melody_finished')).toHaveLength(1)
 p.cache!.load=vi.fn(async()=>{throw Error('bad hash')});await p.play(example(),'reference');expect(p.state.status).toBe('error');expect(p.logs.some(x=>x.kind==='melody_failed'&&x.message==='bad hash')).toBe(true)
})
