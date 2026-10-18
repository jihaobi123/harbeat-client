import {afterEach,expect,it,vi} from 'vitest'
import {VocalBedPlayer,type VocalBedCase,type State} from './transport'
class Param{value=0;points:any[]=[];setValueAtTime(...x:any[]){this.points.push(x)}linearRampToValueAtTime(...x:any[]){this.points.push(x)}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;type='';targets:Node[]=[];connect(n:Node){this.targets.push(n)}disconnect(){}start(...args:any[]){started.push({args,node:this})}stop(){stopped.push(this)}}
const started:{args:any[];node:Node}[]=[],stopped:Node[]=[],filters:Node[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){const n=new Node();filters.push(n);return n}createBufferSource(){return new Node()}async resume(){}async close(){}}
const worklets:Worklet[]=[]
class Worklet extends Node{port:{postMessage:ReturnType<typeof vi.fn>;onmessage:null|((e:{data:any})=>void)}={postMessage:vi.fn(),onmessage:null};constructor(){super();worklets.push(this)}}
let player:VocalBedPlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;stopped.length=0;filters.length=0;worklets.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():VocalBedCase{
 const keys=['aMaster','aBass','aVocal','bEntryMaster','bEntryBass','bEntryVocal','bBodyMaster','bBodyBass','bBodyVocal','aEcho']
 const assets=Object.fromEntries(keys.map(key=>[key,{url:key,sha256:key,duration:key.startsWith('a')?12:8,bytes:1}]))
 return {id:'case',anchor:false,slot:{id:'rhythm',label:'rhythm'},aTitle:'a',bTitle:'b',pre:4,post:8,timing:{duckStart:2,swapStart:3.5,swapEnd:4},bpm:[120,120],planSha256:'frozen',assets,baselineBass:'stem',endpoint:{tailEnd:6.2,nextOnset:9.5,fadeStart:6.5,fadeEnd:6.7},evidence:{},fx:{sendStart:9.7,sendEnd:10.2,wetStart:9.95,wetEnd:10.99,taps:[{delaySeconds:.25,gain:.26},{delaySeconds:.5,gain:.117},{delaySeconds:.75,gain:.052}]},fxEvidence:{inputVocalSha256:'aVocal',wetSha256:'aEcho'},relay:{aVoiceEnd:16,bEntry:20,bEnd:28,aIntervals:[[10,16]],bIntervals:[]},plan:{id:'plan',start:10,end:18,duration:8,rate:1,window:{start:20,end:28},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}},sourceVerification:{},levels:{}} as unknown as VocalBedCase
}
async function setup(change:(s:State)=>void=()=>{}){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new VocalBedPlayer(new URL('https://example.test/'),change);await player.initialize();player.cache!.load=vi.fn(async asset=>({key:asset.url,duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as unknown as AudioBuffer));return player}
function onsetEvent(){const message=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0];return {...message.events.find((e:any)=>e.name==='试听开始'),observedFrame:4480,quantumStart:4352,quantumFrames:128,late:0}}
function observe(data:any){worklets.at(-1)!.port.onmessage!({data})}
it('decodes the same ten assets, freezes bass/cues/EQ and restores native B at the same takeover',async()=>{
 const p=await setup(),c=example(),before=JSON.stringify(c);await p.play(c,'natural');const first=p.logs.find(x=>x.kind==='bass_started')!;await p.play(c,'relay');const second=p.logs.filter(x=>x.kind==='bass_started').at(-1)!
 expect(first.plan).toEqual(c.plan);expect(first.plan).toEqual(second.plan);expect(first.eq).toEqual(second.eq);expect(first.frozenBass).toEqual(second.frozenBass);expect(first.treatment).toEqual(second.treatment);expect([first.wetGain,second.wetGain]).toEqual([0,1])
 expect(first.baselineBass).toBe('stem');expect(second.relay).toEqual(c.relay);expect(first.assets).toEqual(second.assets)
 expect(p.cache!.load).toHaveBeenCalledTimes(20);expect(started).toHaveLength(20)
 expect(started.slice(-10).filter(x=>x.args[0]===12.1)).toHaveLength(3)
 const outgoing=started.slice(-10).filter(x=>x.args[0]===.1);expect(outgoing).toHaveLength(4);expect(outgoing.every(x=>x.args[2]===12)).toBe(true)
 expect(filters).toHaveLength(42);expect(filters.slice(-9).every(n=>n.gain.points.length===1)).toBe(true);expect(filters.filter(x=>x.type==='lowshelf').every(x=>x.gain.points.some(p=>p[0]===-9||p[0]===-7))).toBe(true)
 expect(second.treatment.a.voice.at(-1)).toEqual([12,0]);expect(second.actualStartContext).toBe(.1)
 expect(JSON.stringify(c)).toBe(before)
})
it('aborts preparation on stop without scheduling obsolete sources or completion',async()=>{
 const p=await setup();let resolve!:(b:AudioBuffer)=>void;let signal:AbortSignal|undefined
 const waiting=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn((_asset,s)=>{signal=s;return waiting})
 const playing=p.play(example(),'relay');await Promise.resolve();await Promise.resolve();p.stop();expect(signal?.aborted).toBe(true);resolve({} as AudioBuffer);await playing
 expect(started).toHaveLength(0);expect(p.state.status).toBe('idle');expect(p.logs.some(x=>x.kind==='bass_finished')).toBe(false)
})
it('replacement stops every old source and completion retains immutable blind attribution once',async()=>{
 const p=await setup();await p.play(example(),'relay',{roundId:'old',letter:'B'});await p.play(example(),'natural',{roundId:'new',letter:'A'})
 expect(stopped).toHaveLength(10);expect(p.logs.find(x=>x.kind==='bass_stopped')?.roundId).toBe('old')
 observe(onsetEvent())
 ;(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(240)
 expect(p.logs.filter(x=>x.kind==='bass_finished')).toHaveLength(1);expect(p.logs.find(x=>x.kind==='bass_finished')).toMatchObject({roundId:'new',letter:'A',mode:'natural'})
 expect(p.state).toMatchObject({status:'complete',roundId:'new',letter:'A'})
})
it('dispose during loading prevents scheduling and preserves failures for export',async()=>{
 const p=await setup();p.cache!.load=vi.fn(async()=>{throw Error('bad vocal hash')});await p.play(example(),'natural');expect(p.state.status).toBe('error');expect(p.logs.some(x=>x.kind==='bass_failed'&&x.message==='bad vocal hash')).toBe(true)
 let resolve!:(b:AudioBuffer)=>void;const waiting=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn(()=>waiting);const playing=p.play(example(),'relay');await Promise.resolve();await Promise.resolve();p.dispose();resolve({} as AudioBuffer);await playing;expect(started).toHaveLength(0)
})
it('rejects any vocal extending beyond the frozen A end or missing correction source before playback',async()=>{
 const p=await setup(),c=example();c.relay.aVoiceEnd=18;await p.play(c,'relay');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
 const missing=example();delete missing.assets.aVocal;await p.play(missing,'natural');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
})
it('rejects an unaligned vocal buffer before any sources start',async()=>{
 const p=await setup(),load=p.cache!.load;p.cache!.load=vi.fn(async(a,s)=>{const buffer=await load(a,s);return a.url==='aVocal'?{...buffer,length:buffer.length-8} as AudioBuffer:buffer})
 await p.play(example(),'relay');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
})
it('does not report a first playing state when stopped during the scheduled lead',async()=>{
 const states:State[]=[],p=await setup(s=>states.push(s));await p.play(example(),'relay',{roundId:'round',letter:'B'})
 expect(p.state.status).toBe('loading');const onset=onsetEvent();p.stop();observe(onset)
 expect(states.some(s=>s.status==='playing')).toBe(false);expect(p.logs.some(x=>x.kind==='bass_render_started')).toBe(false)
})
it('only reports rendered onset of the replacement arm and ignores stale or duplicate observations',async()=>{
 const states:State[]=[],p=await setup(s=>states.push(s));await p.play(example(),'relay',{roundId:'round',letter:'B'});const stale=onsetEvent()
 await p.play(example(),'natural',{roundId:'round',letter:'A'});const current=onsetEvent();observe(stale)
 expect(states.some(s=>s.status==='playing')).toBe(false);expect(p.state.status).toBe('loading')
 observe(current);observe(current)
 expect(states.filter(s=>s.status==='playing')).toHaveLength(1);expect(p.state).toMatchObject({status:'playing',letter:'A',mode:'natural'})
 expect(p.logs.filter(x=>x.kind==='bass_render_started')).toHaveLength(1);expect(p.logs.find(x=>x.kind==='bass_render_started')).toMatchObject({roundId:'round',letter:'A'})
 expect(worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0].events).toHaveLength(8)
})

it('rejects unsafe detector endpoint before decoding any source',async()=>{const p=await setup(),c=example();c.endpoint.fadeStart=6;await p.play(c,'relay');expect(p.state.status).toBe('error');expect(p.cache!.load).not.toHaveBeenCalled();expect(started).toHaveLength(0)})
it('gives each replacement player a distinct durable log identity',async()=>{const p=await setup();const first=p.recordId;const replacement=new VocalBedPlayer(new URL('https://example.test/'),()=>{});expect(replacement.recordId).not.toBe(first);replacement.dispose()})
