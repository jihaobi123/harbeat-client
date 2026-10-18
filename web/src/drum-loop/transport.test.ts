import {afterEach,expect,it,vi} from 'vitest'
import {DrumLoopPlayer,type DrumLoopCase,type State} from './transport'
class Param{value=0;points:any[]=[];setValueAtTime(...x:any[]){this.points.push(x)}linearRampToValueAtTime(...x:any[]){this.points.push(x)}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;type='';targets:Node[]=[];connect(n:Node){this.targets.push(n)}disconnect(){}start(...args:any[]){started.push({args,node:this})}stop(){stopped.push(this)}}
const started:{args:any[];node:Node}[]=[],stopped:Node[]=[],filters:Node[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){const n=new Node();filters.push(n);return n}createBufferSource(){return new Node()}async resume(){}async close(){}}
const worklets:Worklet[]=[]
class Worklet extends Node{port:{postMessage:ReturnType<typeof vi.fn>;onmessage:null|((e:{data:any})=>void)}={postMessage:vi.fn(),onmessage:null};constructor(){super();worklets.push(this)}}
let player:DrumLoopPlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;stopped.length=0;filters.length=0;worklets.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():DrumLoopCase{
 const keys=['aMaster','aBass','aDrum','aLoopDrum','bEntryMaster','bEntryBass','bBodyMaster','bBodyBass']
 const assets=Object.fromEntries(keys.map(key=>[key,{url:key,sha256:key,duration:key.startsWith('a')?12:8,bytes:1}]))
 return {id:'case',anchor:false,slot:{id:'rhythm',label:'rhythm'},aTitle:'a',bTitle:'b',pre:4,post:8,timing:{duckStart:2,swapStart:3.5,swapEnd:4},bpm:[120,120],planSha256:'frozen',assets,baselineBass:'stem',loop:{sourceStart:8,sourceEnd:10,applyStart:4,applyEnd:8,targetBars:[{start:4,end:6},{start:6,end:8}],category:'stable',metrics:{}},plan:{id:'plan',start:10,end:18,duration:8,rate:1,window:{start:20,end:28},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}},sourceVerification:{},levels:{}} as unknown as DrumLoopCase
}
async function setup(change:(s:State)=>void=()=>{}){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new DrumLoopPlayer(new URL('https://example.test/'),change);await player.initialize();player.cache!.load=vi.fn(async asset=>({key:asset.url,duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as unknown as AudioBuffer));return player}
function onsetEvent(){const message=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0];return {...message.events.find((e:any)=>e.name==='试听开始'),observedFrame:4480,quantumStart:4352,quantumFrames:128,late:0}}
function observe(data:any){worklets.at(-1)!.port.onmessage!({data})}
it('decodes the same eight assets, freezes bass/cues/EQ and restores native B at the same takeover',async()=>{
 const p=await setup(),c=example(),before=JSON.stringify(c);await p.play(c,'natural');const first=p.logs.find(x=>x.kind==='bass_started')!;await p.play(c,'loop');const second=p.logs.filter(x=>x.kind==='bass_started').at(-1)!
 expect(first.plan).toEqual(c.plan);expect(first.plan).toEqual(second.plan);expect(first.eq).toEqual(second.eq);expect(first.curves).toEqual(second.curves)
 expect(first.baselineBass).toBe('stem');expect(second.loop).toEqual(c.loop);expect(first.assets).toEqual(second.assets)
 expect(p.cache!.load).toHaveBeenCalledTimes(16);expect(started).toHaveLength(16)
 expect(started.slice(-8).filter(x=>x.args[0]===12.1)).toHaveLength(2)
 const outgoing=started.slice(-8).filter(x=>x.args[0]===.1);expect(outgoing).toHaveLength(4);expect(outgoing.every(x=>x.args[2]===12)).toBe(true)
 expect(filters).toHaveLength(36);expect(filters.filter(x=>x.type==='lowshelf').every(x=>x.gain.points.some(p=>p[0]===-9||p[0]===-7))).toBe(true)
 expect(second.drumCorrection.natural.at(-1)).toEqual([12,0]);expect(second.actualStartContext).toBe(.1)
 expect(JSON.stringify(c)).toBe(before)
})
it('aborts preparation on stop without scheduling obsolete sources or completion',async()=>{
 const p=await setup();let resolve!:(b:AudioBuffer)=>void;let signal:AbortSignal|undefined
 const waiting=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn((_asset,s)=>{signal=s;return waiting})
 const playing=p.play(example(),'loop');await Promise.resolve();await Promise.resolve();p.stop();expect(signal?.aborted).toBe(true);resolve({} as AudioBuffer);await playing
 expect(started).toHaveLength(0);expect(p.state.status).toBe('idle');expect(p.logs.some(x=>x.kind==='bass_finished')).toBe(false)
})
it('replacement stops every old source and completion retains immutable blind attribution once',async()=>{
 const p=await setup();await p.play(example(),'loop',{roundId:'old',letter:'B'});await p.play(example(),'natural',{roundId:'new',letter:'A'})
 expect(stopped).toHaveLength(8);expect(p.logs.find(x=>x.kind==='bass_stopped')?.roundId).toBe('old')
 observe(onsetEvent())
 ;(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(240)
 expect(p.logs.filter(x=>x.kind==='bass_finished')).toHaveLength(1);expect(p.logs.find(x=>x.kind==='bass_finished')).toMatchObject({roundId:'new',letter:'A',mode:'natural'})
 expect(p.state).toMatchObject({status:'complete',roundId:'new',letter:'A'})
})
it('dispose during loading prevents scheduling and preserves failures for export',async()=>{
 const p=await setup();p.cache!.load=vi.fn(async()=>{throw Error('bad drum hash')});await p.play(example(),'natural');expect(p.state.status).toBe('error');expect(p.logs.some(x=>x.kind==='bass_failed'&&x.message==='bad drum hash')).toBe(true)
 let resolve!:(b:AudioBuffer)=>void;const waiting=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn(()=>waiting);const playing=p.play(example(),'loop');await Promise.resolve();await Promise.resolve();p.dispose();resolve({} as AudioBuffer);await playing;expect(started).toHaveLength(0)
})
it('rejects any loop extending beyond the frozen A end or missing correction source before playback',async()=>{
 const p=await setup(),c=example();c.loop.applyEnd+=.01;await p.play(c,'loop');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
 const missing=example();delete missing.assets.aLoopDrum;await p.play(missing,'natural');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
})
it('rejects an unaligned drum buffer before any sources start',async()=>{
 const p=await setup(),load=p.cache!.load;p.cache!.load=vi.fn(async(a,s)=>{const buffer=await load(a,s);return a.url==='aDrum'?{...buffer,length:buffer.length-8} as AudioBuffer:buffer})
 await p.play(example(),'loop');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
})
it('does not report a first playing state when stopped during the scheduled lead',async()=>{
 const states:State[]=[],p=await setup(s=>states.push(s));await p.play(example(),'loop',{roundId:'round',letter:'B'})
 expect(p.state.status).toBe('loading');const onset=onsetEvent();p.stop();observe(onset)
 expect(states.some(s=>s.status==='playing')).toBe(false);expect(p.logs.some(x=>x.kind==='bass_render_started')).toBe(false)
})
it('only reports rendered onset of the replacement arm and ignores stale or duplicate observations',async()=>{
 const states:State[]=[],p=await setup(s=>states.push(s));await p.play(example(),'loop',{roundId:'round',letter:'B'});const stale=onsetEvent()
 await p.play(example(),'natural',{roundId:'round',letter:'A'});const current=onsetEvent();observe(stale)
 expect(states.some(s=>s.status==='playing')).toBe(false);expect(p.state.status).toBe('loading')
 observe(current);observe(current)
 expect(states.filter(s=>s.status==='playing')).toHaveLength(1);expect(p.state).toMatchObject({status:'playing',letter:'A',mode:'natural'})
 expect(p.logs.filter(x=>x.kind==='bass_render_started')).toHaveLength(1);expect(p.logs.find(x=>x.kind==='bass_render_started')).toMatchObject({roundId:'round',letter:'A'})
 expect(worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0].events).toHaveLength(6)
})
