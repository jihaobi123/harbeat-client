import {afterEach,expect,it,vi} from 'vitest'
import {VocalRetriggerPlayer,type VocalRetriggerCase,type State} from './transport'
class Param{value=0;points:any[]=[];setValueAtTime(...x:any[]){this.points.push(x)}linearRampToValueAtTime(...x:any[]){this.points.push(x)}exponentialRampToValueAtTime(...x:any[]){this.points.push(x)}cancelScheduledValues(){}setTargetAtTime(){}}
class Node{gain=new Param();frequency=new Param();Q=new Param();buffer:any;onended:any;type='';targets:Node[]=[];connect(n:Node){this.targets.push(n)}disconnect(){}start(...args:any[]){started.push({args,node:this})}stop(){stopped.push(this)}}
const started:{args:any[];node:Node}[]=[],stopped:Node[]=[],filters:Node[]=[]
class Context{currentTime=0;sampleRate=44100;state='running';destination=new Node();audioWorklet={addModule:async()=>{}};createGain(){return new Node()}createBiquadFilter(){const n=new Node();filters.push(n);return n}createBufferSource(){return new Node()}async resume(){}async close(){}}
const worklets:Worklet[]=[]
class Worklet extends Node{port:{postMessage:ReturnType<typeof vi.fn>;onmessage:null|((e:{data:any})=>void)}={postMessage:vi.fn(),onmessage:null};constructor(){super();worklets.push(this)}}
let player:VocalRetriggerPlayer|undefined
afterEach(()=>{player?.dispose();started.length=0;stopped.length=0;filters.length=0;worklets.length=0;vi.useRealTimers();vi.unstubAllGlobals()})
function example():VocalRetriggerCase{
 const keys=['aMaster','aVocal','bEntryMaster','bEntryVocal','bBodyMaster','bBodyVocal','aOneShot','aReviewContext']
 const assets=Object.fromEntries(keys.map(key=>[key,{url:key,sha256:key,duration:key==='aOneShot'?2:key==='aReviewContext'?3:key.startsWith('a')?8:key.startsWith('bEntry')?4:8,bytes:1}]))
 return {id:'case',aTitle:'a',bTitle:'b',pre:4,post:8,baselineBass:'reference',fx:{sourceStart:11,sourceEnd:13,sourceOrigin:6,duration:2,contextStart:10.5,contextEnd:13.5,trigger:8,replayEnd:10,count:1,edgeSeconds:.005,quietPadSeconds:.3,captureGainPolicy:'original-a-linear-at-source',status:'requires-human-cut-review',incomingSupport:[24,26],outgoingSupport:[14,16],outgoingCoverage:{start:5,end:20},incomingCoverage:{start:18,end:28}},bpm:[120,121],planSha256:'frozen',assets,captureEvidence:{inputVocalSha256:'aVocal',oneShotSha256:'aOneShot',contextSha256:'aReviewContext'},sourceVerification:{},plan:{id:'plan',start:10,end:14,duration:4,rate:1,window:{start:20,end:24,bars:2},v30Eq:{a:[{t:0,low:-9,mid:0,high:-1.4}],b:[{t:0,low:-7,mid:0,high:1.2}]}}} as unknown as VocalRetriggerCase
}
const playReady=(p:VocalRetriggerPlayer,c:VocalRetriggerCase,mode:'natural'|'relay',meta={roundId:'round',letter:'A'})=>p.play(c,mode,{...meta,cueReviewed:true})

async function setup(change:(s:State)=>void=()=>{}){vi.useFakeTimers();vi.stubGlobal('window',{setInterval,clearInterval});vi.stubGlobal('AudioContext',Context);vi.stubGlobal('AudioWorkletNode',Worklet);player=new VocalRetriggerPlayer(new URL('https://example.test/'),change);await player.initialize();player.cache!.load=vi.fn(async asset=>({key:asset.url,duration:asset.duration,length:asset.duration*44100,numberOfChannels:2} as unknown as AudioBuffer));return player}
function onsetEvent(){const message=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0];return {...message.events.find((e:any)=>e.name==='试听开始'),observedFrame:4480,quantumStart:4352,quantumFrames:128,late:0}}
function observe(data:any){worklets.at(-1)!.port.onmessage!({data})}
it('preserves original dry sources, EQ and gains, switching only one finite captured phrase',async()=>{
 const p=await setup(),c=example(),raw=JSON.stringify(c);await playReady(p,c,'natural',{roundId:'round',letter:'A'});expect(p.state.status,p.state.message).not.toBe('error');const a=p.logs.find(x=>x.kind==='vocal_retrigger_started');await playReady(p,c,'relay',{roundId:'round',letter:'B'});const b=p.logs.filter(x=>x.kind==='vocal_retrigger_started').at(-1)
 expect(a.assets).toEqual(b.assets);expect(a.plan).toEqual(b.plan);expect(a.eq).toEqual(b.eq);expect(a.treatment.a).toEqual(b.treatment.a);expect(a.treatment.b).toEqual(b.treatment.b);expect(a.treatment.shotGain).toBe(0);expect(b.treatment.shotGain).toBe(1)
 const keys=['aMaster','aVocal','aOneShot','bEntryMaster','bBodyMaster','bEntryVocal','bBodyVocal'];expect(started.slice(0,7).map(x=>(x.node.buffer as any).key)).toEqual(keys);expect(started.slice(-7).map(x=>(x.node.buffer as any).key)).toEqual(keys)
 expect(started).toHaveLength(14);expect(p.cache!.load).toHaveBeenCalledTimes(16);expect(started.slice(-7).filter(x=>x.args[0]===8.1)).toHaveLength(3);expect(filters).toHaveLength(24);expect(JSON.stringify(c)).toBe(raw)
})

it('cancels loading without scheduling sources or completion',async()=>{
 const p=await setup();let resolve!:(b:AudioBuffer)=>void;const wait=new Promise<AudioBuffer>(r=>resolve=r);p.cache!.load=vi.fn(()=>wait);const play=playReady(p,example(),'relay');await Promise.resolve();await Promise.resolve();p.stop();resolve({} as AudioBuffer);await play;expect(started).toHaveLength(0);expect(p.logs.some(x=>x.kind==='vocal_retrigger_finished')).toBe(false)
})
it('attributes rendered onset and one completion to the replacement arm',async()=>{
 const p=await setup();await playReady(p,example(),'relay',{roundId:'old',letter:'B'});const stale=onsetEvent();await playReady(p,example(),'natural',{roundId:'new',letter:'A'});observe(stale);expect(p.state.status).toBe('loading');observe(onsetEvent());expect(p.state.status).toBe('playing');const end=worklets.at(-1)!.port.postMessage.mock.calls.filter(([m])=>m.kind==='arm').at(-1)![0].events.find((e:any)=>e.name==='试听结束');observe({...end,observedFrame:end.frame});(p.ctx as unknown as Context).currentTime=21;vi.advanceTimersByTime(240);expect(p.logs.filter(x=>x.kind==='vocal_retrigger_finished')).toHaveLength(1);expect(p.logs.find(x=>x.kind==='vocal_retrigger_finished')).toMatchObject({roundId:'new',letter:'A'});expect(stopped).toHaveLength(14)
})
it('rejects added FX, shifted buffers and unsafe bridge bounds',async()=>{
 const p=await setup(),c=example();c.assets.aEcho={...c.assets.aVocal};await playReady(p,c,'relay');expect(p.state.status).toBe('error');expect(p.cache!.load).not.toHaveBeenCalled();const invalid=example();invalid.fx.trigger+=1;await playReady(p,invalid,'natural');expect(p.state.status).toBe('error');const load=p.cache!.load;p.cache!.load=vi.fn(async(a,s)=>({...await load(a,s),length:1} as AudioBuffer));await playReady(p,example(),'relay');expect(p.state.status).toBe('error');expect(started).toHaveLength(0)
})
it('preserves distinct durable player identities',async()=>{const p=await setup(),vocal=new VocalRetriggerPlayer(new URL('https://example.test/'),()=>{});expect(p.recordId).not.toBe(vocal.recordId);vocal.dispose()})
it('fails visibly when the audio clock never reports rendered onset, then permits retry',async()=>{
 const p=await setup();await playReady(p,example(),'relay',{roundId:'practice',letter:'B'});expect(p.state.status).toBe('loading');vi.advanceTimersByTime(5200);expect(p.state.status).toBe('error');expect(p.logs.find(x=>x.kind==='vocal_retrigger_failed')).toMatchObject({reason:'render-onset-timeout',audioContextState:'running'});expect(p.logs.some(x=>x.kind==='vocal_retrigger_finished')).toBe(false);expect(stopped).toHaveLength(7)
 await playReady(p,example(),'relay',{roundId:'practice',letter:'B'});observe(onsetEvent());expect(p.state.status).toBe('playing')
})
it('fails clearly if resumed context is not running before any sources are scheduled',async()=>{
 const p=await setup();(p.ctx as unknown as Context).state='suspended';await playReady(p,example(),'natural');expect(p.state.status).toBe('error');expect(started).toHaveLength(0);expect(p.logs.some(x=>x.kind==='vocal_retrigger_finished')).toBe(false)
})
it('does not mark heard from wall-clock progress if rendered end is missing',async()=>{
 const p=await setup();await playReady(p,example(),'natural',{roundId:'round',letter:'A'});observe(onsetEvent());(p.ctx as unknown as Context).currentTime=16.3;vi.advanceTimersByTime(80);expect(p.state.status).not.toBe('complete');expect(p.logs.some(x=>x.kind==='vocal_retrigger_finished')).toBe(false);(p.ctx as unknown as Context).currentTime=17;vi.advanceTimersByTime(80);expect(p.state.status).toBe('error');expect(p.logs.at(-1)).toMatchObject({kind:'vocal_retrigger_failed',reason:'render-end-timeout'})
})

it('refuses A/B loading without the human cue-review flag',async()=>{const p=await setup();await p.play(example(),'relay',{roundId:'formal',letter:'A'});expect(p.state.status).toBe('error');expect(p.cache!.load).not.toHaveBeenCalled();expect(started).toHaveLength(0)})
it('rejects a derived cue whose declared duration escapes the protected support',async()=>{const p=await setup(),c=example();c.assets.aOneShot.duration+=.1;await playReady(p,c,'relay');expect(p.state.status).toBe('error');expect(p.cache!.load).not.toHaveBeenCalled()})
